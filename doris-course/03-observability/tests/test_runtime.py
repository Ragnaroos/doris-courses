"""Offline checks for the observability runtime boundary."""

import base64
import io
import itertools
import json
import subprocess
import tempfile
import unittest
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from doris_course import DorisLab, ObservabilityLab, environment
from doris_course.doris_client import (
    CHECKOUT_STACK,
    CORE_PORTS,
    LITEFUSE_COMPOSE_FILE,
    LITEFUSE_PORTS,
    LOCAL_MODEL_COMPOSE_FILE,
    LOCAL_MODEL_PORTS,
    FLAGS_FILE,
    EnvironmentNotReady,
)


RUNNING = {
    "State": {"Status": "running", "Health": {"Status": "healthy"}},
}
STOPPED = {
    "State": {"Status": "exited", "Health": {"Status": "unhealthy"}},
}


def demo_frame(*rows):
    return pd.DataFrame(list(rows), columns=["container", "state", "restarts"])


class RuntimeTests(unittest.TestCase):
    def test_doris_lab_alias_is_available(self):
        self.assertIs(DorisLab, ObservabilityLab)

    def test_running_container_is_reused(self):
        lab = object.__new__(ObservabilityLab)
        with patch("doris_labkit.docker.shutil.which", return_value="/usr/local/bin/docker"), \
             patch("doris_labkit.docker.docker_preflight", return_value=(True, "ready")), \
             patch("doris_labkit.docker.container_inspect", return_value=RUNNING), \
             patch("doris_labkit.docker.wait_for_health") as wait, \
             patch("doris_labkit.docker.run") as run:
            state = lab.start_container()
        self.assertEqual(state["State"]["Status"], "running")
        wait.assert_called_once_with("doris-obs", timeout_seconds=300)
        run.assert_not_called()

    def test_stopped_container_is_started(self):
        lab = object.__new__(ObservabilityLab)
        start_result = subprocess.CompletedProcess(["docker", "start", "doris-obs"], 0, "doris-obs", "")
        with patch("doris_labkit.docker.shutil.which", return_value="/usr/local/bin/docker"), \
             patch("doris_labkit.docker.docker_preflight", return_value=(True, "ready")), \
             patch("doris_labkit.docker.container_inspect", side_effect=[STOPPED, RUNNING]), \
             patch("doris_labkit.docker.wait_for_health"), \
             patch("doris_labkit.docker.run", return_value=start_result) as run:
            lab.start_container()
        run.assert_called_once_with(["docker", "start", "doris-obs"], show=True)

    def test_compose_without_the_override_tag_stops_the_step(self):
        lab = object.__new__(ObservabilityLab)
        for output, returncode, supported in (("2.24.3", 0, False), ("2.24.4", 0, True), ("v2.40.3-desktop.1", 0, True),
                                              ("5.3.1", 0, True), ("", 1, False)):
            result = subprocess.CompletedProcess(["docker", "compose", "version"], returncode, output + "\n", "")
            with self.subTest(version=output or "missing"), \
                 patch("doris_course.doris_client.run", return_value=result):
                if supported:
                    lab._check_compose_version()
                else:
                    with self.assertRaises(EnvironmentNotReady):
                        lab._check_compose_version()

    def test_port_held_by_another_program_stops_the_step(self):
        lab = object.__new__(ObservabilityLab)
        with patch("doris_course.doris_client.container_inspect", return_value=None), \
             patch("doris_course.doris_client.port_in_use", side_effect=lambda port: port == environment.GRAFANA_PORT):
            with self.assertRaises(EnvironmentNotReady):
                lab._check_ports(CORE_PORTS, (environment.GRAFANA_CONTAINER,))

    def test_running_course_container_may_hold_its_port(self):
        lab = object.__new__(ObservabilityLab)
        running = {
            "State": {"Running": True},
            "HostConfig": {"PortBindings": {"3000/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(environment.GRAFANA_PORT)}]}},
        }
        with patch("doris_course.doris_client.container_inspect", return_value=running), \
             patch("doris_course.doris_client.port_in_use", side_effect=lambda port: port == environment.GRAFANA_PORT):
            lab._check_ports(CORE_PORTS, (environment.GRAFANA_CONTAINER,))

    def test_stopped_course_container_does_not_own_a_busy_port(self):
        lab = object.__new__(ObservabilityLab)
        stopped = {
            "State": {"Running": False},
            "HostConfig": {"PortBindings": {"3000/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(environment.GRAFANA_PORT)}]}},
        }
        with patch("doris_course.doris_client.container_inspect", return_value=stopped), \
             patch("doris_course.doris_client.port_in_use", side_effect=lambda port: port == environment.GRAFANA_PORT):
            with self.assertRaises(EnvironmentNotReady):
                lab._check_ports(CORE_PORTS, (environment.GRAFANA_CONTAINER,))

    def test_trace_collector_port_held_by_another_program_stops_the_step(self):
        lab = object.__new__(ObservabilityLab)
        busy = environment.TRACES_OTLP_HTTP_PORT
        with patch("doris_course.doris_client.container_inspect", return_value=None) as inspect, \
             patch("doris_course.doris_client.port_in_use", side_effect=lambda port: port == busy):
            with self.assertRaises(EnvironmentNotReady):
                lab.check_trace_collector_port()
        inspect.assert_called_once_with(environment.TRACE_COLLECTOR_CONTAINER)

    def test_rerunning_the_checkout_keeps_the_pinned_commit(self):
        with tempfile.TemporaryDirectory() as temp:
            upstream = Path(temp) / "upstream"
            course = Path(temp) / "course"
            course.mkdir()

            def git(*args, cwd=upstream):
                return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
                                      cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()

            subprocess.run(["git", "-c", "init.defaultBranch=main", "init", "-q", str(upstream)], check=True)
            git("commit", "-q", "--allow-empty", "-m", "pinned")
            pinned = git("rev-parse", "HEAD")
            git("commit", "-q", "--allow-empty", "-m", "newer")

            lab = object.__new__(ObservabilityLab)
            with patch.object(environment, "STACK_REPOSITORY", str(upstream)), \
                 patch.object(environment, "STACK_COMMIT", pinned):
                script = lab._compose_script(CHECKOUT_STACK)
            stack = course / ".runtime/ai-observe-stack"
            outputs = []
            for _ in range(2):
                result = subprocess.run(["bash", "-c", script], cwd=course, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                outputs.append(result.stdout)
                self.assertEqual(git("rev-parse", "HEAD", cwd=stack), pinned)
                git("commit", "-q", "--allow-empty", "-m", "upstream moves on")
            self.assertNotIn("Reusing", outputs[0])
            self.assertIn(f"Reusing the DOG stack at commit {pinned}", outputs[1])

    def test_teardown_removes_the_demo_and_litefuse_before_the_network_they_join(self):
        lab = object.__new__(ObservabilityLab)
        lab.lab_dir = Path.cwd()
        for keep_data, volumes in ((False, True), (True, False)):
            with patch("doris_course.doris_client.run_shell") as shell:
                lab.teardown(keep_data=keep_data)
            script = shell.call_args.args[0]
            demo = script.index(f"docker compose -p {environment.DEMO_PROJECT} down")
            litefuse = script.index(f"docker compose -p {environment.LITEFUSE_PROJECT} down")
            model = script.index(f"docker compose -p {environment.LOCAL_MODEL_PROJECT} down")
            containers = " ".join((*environment.MODULE2_COLLECTORS, environment.CPU_LOAD_CONTAINER))
            collectors = script.index(f"for name in {containers}; do")
            core = script.index(f"docker compose -p {environment.PROJECT} down")
            self.assertLess(demo, litefuse)
            self.assertLess(litefuse, model)
            self.assertLess(model, collectors)
            self.assertLess(collectors, core)
            # The demo's volumes are anonymous ones that no later start reuses: they go even with keep_data.
            self.assertIn("--volumes", script[demo:litefuse])
            self.assertEqual("--volumes" in script[litefuse:model], volumes)
            self.assertEqual("--volumes" in script[model:collectors], volumes)
            self.assertEqual("--volumes" in script[core:], volumes)
            # The log collector saves its read position when it stops; without the data, the position goes too.
            self.assertLess(script.index('docker stop -t 5 "$name"', collectors), script.index("docker rm -f", collectors))
            self.assertEqual("rm -rf .runtime/collector-state" in script[core:], volumes)
            # The flag page edits a file of the upstream checkout; teardown restores the pinned version.
            reset = f"git -C .runtime/ai-observe-stack checkout -- {FLAGS_FILE}"
            self.assertEqual(reset in script[core:], volumes)
            # Doris wrote its logs as root. Once it is gone, they go to the owner of their directory,
            # with the image that ran Doris, so that the learner can delete them on Linux too.
            handback = script.index("docker run --rm --entrypoint chown", core)
            self.assertIn(f"docker image inspect {environment.DORIS_IMAGE}", script[core:handback])
            self.assertIn(f'-v "$(pwd -P)/.runtime/doris-logs:/logs" {environment.DORIS_IMAGE} '
                          "-R --reference=/logs /logs", script[handback:])

    def test_stop_demo_removes_its_anonymous_volumes(self):
        lab = object.__new__(ObservabilityLab)
        lab.lab_dir = Path.cwd()
        with patch("doris_course.doris_client.run_shell") as shell:
            lab.stop_demo()
        # Images of the demo declare volumes that its Compose file does not name. Without --volumes,
        # every stop would leave them behind, and the next start would create new ones.
        self.assertEqual(shell.call_args.args[0], f"docker compose -p {environment.DEMO_PROJECT} down --volumes")

    def test_shell_runs_from_the_course_root(self):
        lab = object.__new__(ObservabilityLab)
        lab.lab_dir = Path.cwd()
        result = lab.shell(
            'printf "course-root=%s" "$(pwd -P)"',
            title="Run a shell command",
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn(f"course-root={Path.cwd()}", result.stdout)



class RowWaitProgressTests(unittest.TestCase):
    def test_wait_refreshes_in_place_then_finishes_with_the_actual_rows(self):
        lab = object.__new__(ObservabilityLab)
        empty = pd.DataFrame(columns=["id"])
        ready = pd.DataFrame([{"id": 1}])
        with patch.object(lab, "query", side_effect=[empty, empty, empty, ready]), \
             patch("doris_course.doris_client.time.monotonic", side_effect=[0, 0, 2, 10, 12]), \
             patch("doris_course.doris_client.time.sleep"), \
             patch("doris_course.doris_client.display") as display, \
             patch("doris_course.doris_client.show_sql"), \
             patch("doris_course.doris_client.show_frame"):
            result = lab.wait_for_rows("SELECT id FROM t", title="Rows <ready>", hint="Retry", timeout_seconds=30)
        self.assertIs(result, ready)
        display.assert_called_once()
        initial = display.call_args.args[0].data
        self.assertIn("Rows &lt;ready&gt;", initial)
        self.assertIn("30 seconds remaining", initial)
        updates = [call.args[0].data for call in display.return_value.update.call_args_list]
        self.assertEqual(len(updates), 2)  # no new card at the two-second poll
        self.assertIn("Elapsed 10 seconds", updates[0])
        self.assertIn("matching rows 0 / 1", updates[0])
        self.assertIn('doris-status success', updates[1])
        self.assertIn("matching rows 1 / 1", updates[1])

    def test_timeout_stops_the_progress_and_preserves_the_recovery_hint(self):
        lab = object.__new__(ObservabilityLab)
        with patch.object(lab, "query", return_value=pd.DataFrame()), \
             patch("doris_course.doris_client.time.monotonic", side_effect=[0, 0, 9, 10]), \
             patch("doris_course.doris_client.time.sleep") as sleep, \
             patch("doris_course.doris_client.display") as display, \
             patch("doris_course.doris_client.show_sql"), \
             patch("doris_course.doris_client.show_frame"), \
             patch.object(lab, "_failure") as failure:
            with self.assertRaises(EnvironmentNotReady):
                lab.wait_for_rows("SELECT 1 WHERE FALSE", title="Waiting", hint="Start the demo", timeout_seconds=10)
        failure.assert_called_once_with("No rows after 10 seconds", "Start the demo")
        self.assertEqual(sleep.call_args_list[-1].args, (1,))
        final = display.return_value.update.call_args.args[0].data
        self.assertIn('doris-status failure', final)
        self.assertIn("0 seconds remaining", final)

    def test_ready_rows_do_not_create_a_waiting_card(self):
        lab = object.__new__(ObservabilityLab)
        with patch.object(lab, "query", return_value=pd.DataFrame([{"id": 1}])), \
             patch("doris_course.doris_client.display") as display, \
             patch("doris_course.doris_client.show_sql"), \
             patch("doris_course.doris_client.show_frame"):
            lab.wait_for_rows("SELECT 1", title="Ready", hint="Retry")
        display.assert_not_called()

def rules_page(*instances, health="ok"):
    """Grafana's rules API with the rule Host CPU busy and the given (labels, state) instances."""
    alerts = [{"labels": {"alertname": "Host CPU busy", "grafana_folder": "Doris course", "team": "doris-course",
                          **labels},
               "state": state, "activeAt": "2026-10-20T09:04:10Z",
               "annotations": {"summary": f"CPU of {labels.get('host')} is 95.9% busy"}}
              for labels, state in instances]
    rule = {"name": "Host CPU busy", "labels": {"team": "doris-course"}, "health": health,
            "lastEvaluation": "2026-10-20T09:04:10Z", "alerts": alerts}
    return json.dumps({"status": "success", "data": {"groups": [{"name": "host-cpu", "rules": [rule]}]}})


def mailpit_page(*messages):
    return json.dumps({"messages": [
        {"ID": message_id, "Subject": subject, "Created": created,
         "From": {"Name": "Grafana (DOG course)", "Address": "grafana@example.com"},
         "To": [{"Name": "", "Address": "oncall@example.com"}]}
        for message_id, subject, created in messages
    ]})


class GrafanaAlertingTests(unittest.TestCase):
    def lab(self):
        return object.__new__(ObservabilityLab)

    def test_instances_are_named_by_the_labels_of_the_query_result(self):
        lab = self.lab()
        page = rules_page(({"host": "docker-desktop"}, "Normal"))
        with patch.object(ObservabilityLab, "_read", return_value=page) as read, \
             patch("doris_course.doris_client.show_sql") as statement, \
             patch("doris_course.doris_client.show_frame"):
            frame = lab.alert_instances("Host CPU busy")
        # Grafana's anonymous viewer may read the rules API; the learner sees the request.
        self.assertEqual(read.call_args.args[0], f"{lab.grafana_url}/api/prometheus/grafana/api/v1/rules")
        self.assertEqual(statement.call_args.args[1], f'curl -s "{lab.grafana_url}/api/prometheus/grafana/api/v1/rules"')
        # The labels that every instance of the rule has are left out.
        self.assertEqual(frame.to_dict("records"), [{
            "instance": "host=docker-desktop", "state": "Normal", "since_utc": "2026-10-20 09:04:10",
            "summary": "CPU of docker-desktop is 95.9% busy",
        }])

    def test_a_rule_that_was_not_evaluated_yet_has_no_instances(self):
        with patch.object(ObservabilityLab, "_read", return_value=rules_page()), \
             patch("doris_course.doris_client.show_sql"), \
             patch("doris_course.doris_client.show_frame") as shown, \
             patch("doris_course.doris_client.card") as card:
            frame = self.lab().alert_instances("Host CPU busy")
        self.assertTrue(frame.empty)
        shown.assert_not_called()
        self.assertEqual(card.call_args.args[1:], ("info", "No instances yet"))

    def test_a_missing_rule_stops_with_a_card(self):
        with patch.object(ObservabilityLab, "_read", return_value=rules_page()), \
             patch("doris_course.doris_client.show_sql"), \
             patch("doris_course.doris_client.card") as card:
            with self.assertRaises(EnvironmentNotReady) as raised:
                self.lab().alert_instances("Host CPU is busy")
        self.assertEqual(card.call_args.args[1:], ("fail", "Grafana has no alert rule named 'Host CPU is busy'"))
        self.assertEqual(raised.exception._render_traceback_(),
                         ["Stopped: Grafana has no alert rule named 'Host CPU is busy'."])

    def test_wait_shows_each_change_until_every_instance_is_in_the_state(self):
        pages = [rules_page(({"host": "h1"}, "Normal")), rules_page(({"host": "h1"}, "Pending")),
                 rules_page(({"host": "h1"}, "Pending")), rules_page(({"host": "h1"}, "Alerting"))]
        with patch.object(ObservabilityLab, "_read", side_effect=pages), \
             patch("doris_course.doris_client.time.sleep") as sleep, \
             patch("doris_course.doris_client.show_sql"), \
             patch("doris_course.doris_client.show_frame") as shown:
            frame = self.lab().wait_for_alert_state("Host CPU busy", "Alerting", hint="Start the load.")
        self.assertEqual(sleep.call_count, 3)
        self.assertEqual(frame["state"].tolist(), ["Alerting"])
        changes = shown.call_args_list[0].args[1]
        self.assertEqual(changes["instances"].tolist(), ["host=h1: Normal", "host=h1: Pending", "host=h1: Alerting"])

    def test_wait_needs_every_instance_in_the_state(self):
        # After the data stops, the host's instance stays Normal for two evaluations next to the NoData one.
        mixed = rules_page(({}, "NoData"), ({"host": "h1"}, "Normal"), health="nodata")
        clock = itertools.count(0, 100)
        with patch.object(ObservabilityLab, "_read", return_value=mixed), \
             patch("doris_course.doris_client.time.monotonic", side_effect=lambda: next(clock)), \
             patch("doris_course.doris_client.time.sleep"), \
             patch("doris_course.doris_client.show_sql"), \
             patch("doris_course.doris_client.show_frame"), \
             patch("doris_course.doris_client.card") as card:
            with self.assertRaises(EnvironmentNotReady):
                self.lab().wait_for_alert_state("Host CPU busy", "NoData", hint="Stop the Collector.",
                                                timeout_seconds=150)
        card.assert_called_once_with("Stop the Collector.", "fail", "Host CPU busy is not NoData after 150 seconds")

    def test_email_wait_skips_older_emails(self):
        lab = self.lab()
        listing = mailpit_page(("new", "[FIRING:1] Host CPU busy Doris course h1", "2026-10-20T09:04:20.241Z"),
                               ("old", "[FIRING:1] Host CPU busy Doris course h1", "2026-10-20T08:30:00.000Z"))
        after = datetime(2026, 10, 20, 9, 1, 45, tzinfo=timezone.utc)
        with patch.object(ObservabilityLab, "_read", side_effect=[mailpit_page(), listing,
                                                                  json.dumps({"Text": "Summary: CPU of h1"})]) as read, \
             patch("doris_course.doris_client.time.sleep"), \
             patch("doris_course.doris_client.show_sql"), \
             patch("doris_course.doris_client.show_frame") as shown, \
             patch("doris_course.doris_client.show_log") as log:
            email = lab.wait_for_email("[FIRING:1] Host CPU busy", after=after, hint="Check the policy.")
        self.assertEqual(email["id"], "new")
        self.assertEqual(read.call_args.args[0], f"{lab.mailpit_url}/api/v1/message/new")
        row = shown.call_args.args[1].to_dict("records")[0]
        self.assertEqual(row["from"], "Grafana (DOG course) <grafana@example.com>")
        self.assertEqual(row["received_utc"], "2026-10-20 09:04:20")
        self.assertEqual(log.call_args.args[1], "Summary: CPU of h1")

    def test_email_wait_stops_when_only_older_emails_match(self):
        listing = mailpit_page(("old", "[RESOLVED] Host CPU busy", "2026-10-20T08:30:00.000Z"))
        clock = itertools.count(0, 100)
        with patch.object(ObservabilityLab, "_read", return_value=listing), \
             patch("doris_course.doris_client.time.monotonic", side_effect=lambda: next(clock)), \
             patch("doris_course.doris_client.time.sleep"), \
             patch("doris_course.doris_client.show_sql"), \
             patch("doris_course.doris_client.card") as card:
            with self.assertRaises(EnvironmentNotReady):
                self.lab().wait_for_email("[RESOLVED] Host CPU busy", hint="Wait for the group interval.",
                                          after=datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc),
                                          timeout_seconds=120)
        self.assertEqual(card.call_args.args[1:], ("fail", "No email about '[RESOLVED] Host CPU busy' after 120 seconds"))

    def test_an_unreachable_service_stops_with_a_card(self):
        refused = urllib.error.URLError("Connection refused")
        with patch("doris_course.doris_client.urllib.request.urlopen", side_effect=refused), \
             patch("doris_course.doris_client.show_sql"), \
             patch("doris_course.doris_client.card") as card:
            with self.assertRaises(EnvironmentNotReady) as raised:
                self.lab().wait_for_email("TestAlert", hint="Press Test.")
        self.assertEqual(card.call_args.args[1:], ("fail", "Mailpit does not answer"))
        self.assertIn("lab.prepare_environment()", card.call_args.args[0])
        self.assertEqual(raised.exception._render_traceback_(), ["Stopped: Mailpit does not answer."])

    def test_export_finds_the_rule_by_its_title(self):
        lab = self.lab()
        listing = json.dumps([{"uid": "u1", "title": "Other rule"}, {"uid": "u2", "title": "Host CPU busy"}])
        with patch.object(ObservabilityLab, "_read", side_effect=[listing, "apiVersion: 1\n"]) as read, \
             patch("doris_course.doris_client.show_sql"), \
             patch("doris_course.doris_client.show_log") as log:
            text = lab.export_alert_rule("Host CPU busy")
        self.assertEqual(text, "apiVersion: 1\n")
        self.assertEqual(read.call_args.args[0],
                         f"{lab.grafana_url}/api/v1/provisioning/alert-rules/u2/export?format=yaml")
        self.assertEqual(log.call_args.kwargs, {"opened": True})


def flag_page(variant, value=0.5):
    """flagd's ResolveAll answer with paymentFailure at ``variant`` and one other flag."""
    return json.dumps({"flags": {
        "adFailure": {"reason": "STATIC", "variant": "off", "boolValue": False, "metadata": {}},
        "paymentFailure": {"reason": "STATIC", "variant": variant, "doubleValue": value, "metadata": {}},
    }}).encode()


class AlertRuleProvisioningTests(unittest.TestCase):
    RULE = {"uid": "failed-orders", "title": "Failed orders", "for": "1m",
            "labels": {"team": "doris-course", "severity": "critical"}}

    def provision(self, answers):
        """Run provision_alert_rule_group with Grafana's answers by (method, path); return the calls."""
        lab = object.__new__(ObservabilityLab)
        calls = []

        def send(method, url, body=None, *, auth, headers=None, missing_ok=False):
            path = url.replace(lab.grafana_url, "")
            calls.append((method, path, body, auth, headers))
            return answers.get((method, path))

        with patch.object(ObservabilityLab, "_send", side_effect=send), \
             patch("doris_course.doris_client.show_sql") as statement, \
             patch("doris_course.doris_client.show_frame") as shown:
            lab.provision_alert_rule_group("Doris course", "orders", [self.RULE], interval_seconds=30,
                                           admin_password="secret")
        return calls, statement, shown

    def test_a_new_rule_is_created_then_its_group_is_sent(self):
        group = json.dumps({"title": "orders", "interval": 30, "rules": [self.RULE]})
        calls, statement, shown = self.provision({
            ("GET", "/api/folders"): json.dumps([{"uid": "f1", "title": "Doris course"}]),
            ("GET", "/api/v1/provisioning/alert-rules/failed-orders"): None,  # 404: Grafana does not have it
            ("PUT", "/api/v1/provisioning/folder/f1/rule-groups/orders"): group,
        })
        self.assertEqual([(method, path) for method, path, *_ in calls], [
            ("GET", "/api/folders"),
            ("GET", "/api/v1/provisioning/alert-rules/failed-orders"),
            ("POST", "/api/v1/provisioning/alert-rules"),
            ("PUT", "/api/v1/provisioning/folder/f1/rule-groups/orders"),
        ])
        # A group's PUT only updates rules that exist, so the new rule is created in its folder and group first.
        self.assertEqual(calls[2][2], {**self.RULE, "folderUID": "f1", "ruleGroup": "orders"})
        self.assertEqual(calls[3][2], {"title": "orders", "interval": 30, "rules": [self.RULE]})
        # Every request signs in as admin; writes keep the rule editable in the web page.
        self.assertTrue(all(auth == ("admin", "secret") for *_, auth, _ in calls))
        self.assertEqual(calls[3][4], {"X-Disable-Provenance": "true"})
        # The learner sees the requests, without the password.
        self.assertNotIn("secret", statement.call_args.args[1])
        self.assertEqual(shown.call_args.args[1].to_dict("records"), [{
            "rule": "Failed orders", "uid": "failed-orders", "pending_period": "1m",
            "labels": "severity=critical, team=doris-course"}])

    def test_a_rerun_updates_the_rule_and_a_missing_folder_is_created(self):
        calls, _, _ = self.provision({
            ("GET", "/api/folders"): json.dumps([]),
            ("POST", "/api/folders"): json.dumps({"uid": "f2", "title": "Doris course"}),
            ("GET", "/api/v1/provisioning/alert-rules/failed-orders"): json.dumps(self.RULE),
            ("PUT", "/api/v1/provisioning/folder/f2/rule-groups/orders"): json.dumps({"rules": [self.RULE]}),
        })
        self.assertEqual([(method, path) for method, path, *_ in calls], [
            ("GET", "/api/folders"),
            ("POST", "/api/folders"),
            ("GET", "/api/v1/provisioning/alert-rules/failed-orders"),
            ("PUT", "/api/v1/provisioning/folder/f2/rule-groups/orders"),
        ])
        self.assertEqual(calls[1][2], {"title": "Doris course"})

    def test_a_wrong_password_stops_with_a_card(self):
        lab = object.__new__(ObservabilityLab)
        refused = urllib.error.HTTPError("http://grafana/api/folders", 401, "Unauthorized", {}, io.BytesIO(b"{}"))
        with patch("doris_course.doris_client.urllib.request.urlopen", side_effect=refused), \
             patch("doris_course.doris_client.card") as card:
            with self.assertRaises(EnvironmentNotReady):
                lab._send("GET", "http://grafana/api/folders", auth=("admin", "wrong"))
        self.assertEqual(card.call_args.args[2], "Grafana refused the admin password")
        self.assertIn("GRAFANA_ADMIN_PASSWORD", card.call_args.args[0])


class FeatureFlagTests(unittest.TestCase):
    def lab(self):
        return object.__new__(ObservabilityLab)

    def test_wait_asks_flagd_through_the_storefront_until_the_flag_has_the_variant(self):
        lab = self.lab()
        with patch("doris_course.doris_client.urllib.request.urlopen") as urlopen, \
             patch("doris_course.doris_client.time.sleep") as sleep, \
             patch("doris_course.doris_client.show_sql") as statement, \
             patch("doris_course.doris_client.show_frame"):
            urlopen.return_value.__enter__.return_value.read.side_effect = [flag_page("off", 0), flag_page("50%")]
            frame = lab.wait_for_feature_flag("paymentFailure", "50%")
        self.assertEqual(sleep.call_count, 1)
        self.assertEqual(frame.to_dict("records"), [{"flag": "paymentFailure", "variant": "50%", "value": 0.5}])
        request = urlopen.call_args.args[0]
        url = f"{lab.demo_url}/flagservice/flagd.evaluation.v1.Service/ResolveAll"
        self.assertEqual((request.full_url, request.get_method()), (url, "POST"))
        # The learner sees the same request as a curl command.
        self.assertIn(f'"{url}"', statement.call_args.args[1])
        self.assertTrue(statement.call_args.args[1].startswith("curl -s -X POST"))

    def test_a_flag_that_keeps_another_variant_stops_with_the_steps_of_the_flag_page(self):
        lab = self.lab()
        clock = itertools.count(0, 100)
        with patch("doris_course.doris_client.urllib.request.urlopen") as urlopen, \
             patch("doris_course.doris_client.time.monotonic", side_effect=lambda: next(clock)), \
             patch("doris_course.doris_client.time.sleep"), \
             patch("doris_course.doris_client.show_sql"), \
             patch("doris_course.doris_client.card") as card:
            urlopen.return_value.__enter__.return_value.read.return_value = flag_page("off", 0)
            with self.assertRaises(EnvironmentNotReady):
                lab.wait_for_feature_flag("paymentFailure", "50%", timeout_seconds=150)
        message, kind, title = card.call_args.args
        self.assertEqual((kind, title), ("fail", "paymentFailure is not 50%"))
        self.assertIn(f"{lab.demo_url}/feature", message)
        self.assertIn("paymentFailure is off", message)

    def test_an_unknown_flag_and_a_stopped_demo_stop_with_a_card(self):
        lab = self.lab()
        clock = itertools.count(0, 100)
        with patch("doris_course.doris_client.urllib.request.urlopen") as urlopen, \
             patch("doris_course.doris_client.time.monotonic", side_effect=lambda: next(clock)), \
             patch("doris_course.doris_client.time.sleep"), \
             patch("doris_course.doris_client.show_sql"), \
             patch("doris_course.doris_client.card") as card:
            urlopen.return_value.__enter__.return_value.read.return_value = flag_page("50%")
            with self.assertRaises(EnvironmentNotReady):
                lab.wait_for_feature_flag("paymentFailures", "50%", timeout_seconds=150)
        self.assertIn("no feature flag named paymentFailures", card.call_args.args[0])
        with patch("doris_course.doris_client.urllib.request.urlopen",
                   side_effect=urllib.error.URLError("Connection refused")), \
             patch("doris_course.doris_client.show_sql"), \
             patch("doris_course.doris_client.card") as card:
            with self.assertRaises(EnvironmentNotReady):
                lab.wait_for_feature_flag("paymentFailure", "50%")
        self.assertEqual(card.call_args.args[1:], ("fail", "The demo's flag service does not answer"))
        self.assertIn("lab.start_demo()", card.call_args.args[0])

    def test_the_flags_file_is_the_one_that_the_demo_mounts_for_flagd(self):
        upstream = Path(__file__).resolve().parents[1] / ".runtime/ai-observe-stack"
        compose = upstream / "doris-opentelemetry-demo/docker-compose.yml"
        if not compose.is_file():
            self.skipTest("the pinned DOG stack is not checked out in .runtime/")
        import yaml
        flagd = yaml.safe_load(compose.read_text())["services"]["flagd"]
        self.assertIn("./src/flagd:/etc/flagd", flagd["volumes"])
        self.assertTrue((upstream / FLAGS_FILE).is_file())


class GrafanaDashboardTests(unittest.TestCase):
    def test_the_dashboard_is_found_by_its_exact_title_and_listed_by_panel(self):
        lab = object.__new__(ObservabilityLab)
        found = json.dumps([{"uid": "u0", "title": "Payment incident (copy)"}, {"uid": "u1", "title": "Payment incident"}])
        dashboard = json.dumps({"dashboard": {"panels": [
            {"title": "Orders per minute", "type": "timeseries",
             "targets": [{"format": "time_series", "rawSql": "SELECT 1"}]},
            {"title": "Notes", "type": "text"},
        ]}})
        with patch.object(ObservabilityLab, "_read", side_effect=[found, dashboard]) as read, \
             patch("doris_course.doris_client.show_sql") as statement, \
             patch("doris_course.doris_client.show_frame"):
            frame = lab.grafana_dashboard("Payment incident")
        # Grafana's anonymous viewer may read dashboards; the learner sees the requests.
        self.assertEqual(read.call_args_list[0].args[0],
                         f"{lab.grafana_url}/api/search?type=dash-db&query=Payment%20incident")
        self.assertEqual(read.call_args_list[1].args[0], f"{lab.grafana_url}/api/dashboards/uid/u1")
        self.assertIn("curl -s", statement.call_args.args[1])
        self.assertEqual(frame.to_dict("records"), [
            {"panel": "Orders per minute", "visualization": "timeseries", "format": "time_series", "sql": "SELECT 1"},
            {"panel": "Notes", "visualization": "text", "format": None, "sql": ""},
        ])

    def test_a_dashboard_that_was_not_saved_stops_with_a_card(self):
        lab = object.__new__(ObservabilityLab)
        with patch.object(ObservabilityLab, "_read", return_value="[]"), \
             patch("doris_course.doris_client.show_sql"), \
             patch("doris_course.doris_client.card") as card:
            with self.assertRaises(EnvironmentNotReady):
                lab.grafana_dashboard("Payment incident")
        self.assertEqual(card.call_args.args[1:], ("fail", "Grafana has no dashboard named 'Payment incident'"))
        self.assertIn("Save dashboard", card.call_args.args[0])


class LitefuseTests(unittest.TestCase):
    def lab(self):
        lab = object.__new__(ObservabilityLab)
        lab.lab_dir = Path.cwd()
        return lab

    def test_start_needs_the_dog_stack(self):
        with patch.object(ObservabilityLab, "ensure_docker_ready"), \
             patch.object(ObservabilityLab, "_dog_stack_running", return_value=False), \
             patch("doris_course.doris_client.run_shell") as shell, \
             patch("doris_course.doris_client.card") as card:
            with self.assertRaises(EnvironmentNotReady):
                self.lab().start_litefuse()
        shell.assert_not_called()
        self.assertEqual(card.call_args.args[1:], ("fail", "The DOG stack is not running"))

    def test_start_gives_the_be_a_private_endpoint_before_the_containers_start(self):
        steps = []
        with patch.object(ObservabilityLab, "ensure_docker_ready"), \
             patch.object(ObservabilityLab, "_dog_stack_running", return_value=True), \
             patch.object(ObservabilityLab, "_check_compose_version"), \
             patch.object(ObservabilityLab, "_check_ports") as ports, \
             patch.object(ObservabilityLab, "_set_be_private_endpoint", side_effect=lambda: steps.append("endpoint")), \
             patch.object(ObservabilityLab, "shell", side_effect=lambda script, title: steps.append(script)), \
             patch.object(ObservabilityLab, "_wait_for_litefuse") as wait:
            self.lab().start_litefuse()
        ports.assert_called_once_with(LITEFUSE_PORTS, (environment.LITEFUSE_WEB_CONTAINER,))
        self.assertEqual(steps[0], "endpoint")
        self.assertIn(f"docker compose -p {environment.LITEFUSE_PROJECT} -f {LITEFUSE_COMPOSE_FILE} up -d", steps[1])
        wait.assert_called_once_with(180)

    def test_private_endpoint_keeps_the_tags_that_the_backend_has(self):
        expected = ('ALTER SYSTEM MODIFY BACKEND "127.0.0.1:9050"\n'
                    'SET ("tag.location" = "default",\n     "tag.private_endpoint" = "doris-obs:8040")')
        # MODIFY BACKEND replaces every tag, so the location is repeated, also when the cell runs again.
        for tags in ('{"location" : "default"}', '{"private_endpoint" : "doris-obs:8040", "location" : "default"}'):
            backends = pd.DataFrame([{"Host": "127.0.0.1", "HeartbeatPort": 9050, "Tag": tags}])
            with self.subTest(tags=tags), \
                 patch.object(ObservabilityLab, "query", return_value=backends), \
                 patch.object(ObservabilityLab, "execute") as execute:
                self.lab()._set_be_private_endpoint()
            self.assertEqual(execute.call_args.args[0], expected)

    def test_wait_checks_the_project_that_the_api_keys_belong_to(self):
        lab = self.lab()
        projects = json.dumps({"data": [{"id": "llm_app", "name": "LLM app",
                                         "organization": {"id": "doris_course", "name": "Doris course"}}]})
        with patch.object(ObservabilityLab, "_http_status", side_effect=[None, 502, 200]), \
             patch.object(ObservabilityLab, "_read", return_value=projects) as read, \
             patch("doris_course.doris_client.time.sleep") as sleep, \
             patch("doris_course.doris_client.show_sql") as statement, \
             patch("doris_course.doris_client.show_frame") as shown, \
             patch("doris_course.doris_client.card") as card:
            lab._wait_for_litefuse(180)
        self.assertEqual(sleep.call_count, 2)
        self.assertIn(f"curl -s -u pk-lf-doris-course:sk-lf-doris-course \"{lab.litefuse_url}/api/public/projects\"",
                      statement.call_args.args[1])
        self.assertEqual(read.call_args.args[0], f"{lab.litefuse_url}/api/public/projects")
        self.assertEqual(read.call_args.kwargs["auth"], (environment.LITEFUSE_PUBLIC_KEY, environment.LITEFUSE_SECRET_KEY))
        self.assertEqual(shown.call_args.args[1].to_dict("records"),
                         [{"organization": "Doris course", "project": "LLM app", "project_id": "llm_app"}])
        self.assertEqual(card.call_args.args[1:], ("ok", "Litefuse is running"))
        self.assertIn(environment.LITEFUSE_USER_EMAIL, card.call_args.args[0])
        self.assertIn(environment.LITEFUSE_USER_PASSWORD, card.call_args.args[0])

    def test_wait_stops_when_litefuse_does_not_answer(self):
        clock = itertools.count(0, 100)
        with patch.object(ObservabilityLab, "_http_status", return_value=None), \
             patch("doris_course.doris_client.time.monotonic", side_effect=lambda: next(clock)), \
             patch("doris_course.doris_client.time.sleep"), \
             patch("doris_course.doris_client.show_sql"), \
             patch("doris_course.doris_client.card") as card:
            with self.assertRaises(EnvironmentNotReady):
                self.lab()._wait_for_litefuse(180)
        self.assertEqual(card.call_args.args[1:], ("fail", "Litefuse does not answer"))
        self.assertIn(f"docker logs {environment.LITEFUSE_WEB_CONTAINER}", card.call_args.args[0])

    def test_wait_stops_when_the_keys_belong_to_another_project(self):
        other = json.dumps({"data": [{"id": "other", "name": "Other", "organization": {"name": "Org"}}]})
        with patch.object(ObservabilityLab, "_http_status", return_value=200), \
             patch.object(ObservabilityLab, "_read", return_value=other), \
             patch("doris_course.doris_client.show_sql"), \
             patch("doris_course.doris_client.card") as card:
            with self.assertRaises(EnvironmentNotReady):
                self.lab()._wait_for_litefuse(180)
        self.assertEqual(card.call_args.args[1:], ("fail", "The API keys do not belong to the course's project"))
        self.assertIn(f"docker compose -p {environment.LITEFUSE_PROJECT} down --volumes", card.call_args.args[0])

    def test_read_sends_the_keys_with_basic_authentication(self):
        with patch("doris_course.doris_client.urllib.request.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = b"{}"
            text = self.lab()._read("http://127.0.0.1:23100/api/public/projects", "Litefuse", "Start it.",
                                    auth=("pk", "sk"))
        self.assertEqual(text, "{}")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:23100/api/public/projects")
        self.assertEqual(request.get_header("Authorization"), "Basic " + base64.b64encode(b"pk:sk").decode())

    def test_trace_lists_its_observations_in_time_order(self):
        lab = self.lab()
        trace = json.dumps({"id": "t1", "name": "course-assistant", "latency": 0.23, "totalCost": 0.00079,
                            "observations": [
                                {"type": "GENERATION", "name": "llm-answer", "startTime": "2026-10-20T10:51:03.540Z",
                                 "latency": 0.174, "model": "simulated-llm",
                                 "usageDetails": {"input": 28, "output": 17, "total": 45},
                                 "costDetails": {"input": 0.00028, "output": 0.00051, "total": 0.00079}},
                                {"type": "SPAN", "name": "answer-question", "startTime": "2026-10-20T10:51:03.310Z",
                                 "latency": 0.23, "model": None, "usageDetails": {}, "costDetails": {}},
                            ]})
        with patch.object(ObservabilityLab, "_read", return_value=trace) as read, \
             patch("doris_course.doris_client.show_sql") as statement, \
             patch("doris_course.doris_client.show_frame") as shown:
            result = lab.litefuse_trace("t1")
        self.assertEqual(result["name"], "course-assistant")
        self.assertEqual(read.call_args.args[0], f"{lab.litefuse_url}/api/public/traces/t1")
        self.assertIn("-u pk-lf-doris-course:sk-lf-doris-course", statement.call_args.args[1])
        frame = shown.call_args.args[1]
        self.assertEqual(frame["name"].tolist(), ["answer-question", "llm-answer"])
        self.assertEqual(frame["start_time_utc"].tolist(), ["2026-10-20 10:51:03", "2026-10-20 10:51:03"])
        self.assertEqual(frame.loc[1, "cost_usd"], 0.00079)

    def test_stop_keeps_the_volumes(self):
        with patch("doris_course.doris_client.run_shell") as shell:
            self.lab().stop_litefuse()
        self.assertEqual(shell.call_args.args[0], f"docker compose -p {environment.LITEFUSE_PROJECT} down")


class LocalModelTests(unittest.TestCase):
    def lab(self):
        lab = object.__new__(ObservabilityLab)
        lab.lab_dir = Path.cwd()
        return lab

    def test_start_downloads_and_checks_the_model_before_the_server_starts(self):
        scripts = []
        with patch.object(ObservabilityLab, "ensure_docker_ready"), \
             patch.object(ObservabilityLab, "_check_compose_version"), \
             patch.object(ObservabilityLab, "_check_ports") as ports, \
             patch.object(ObservabilityLab, "shell", side_effect=lambda script, title: scripts.append(script)), \
             patch.object(ObservabilityLab, "_wait_for_local_model") as wait:
            self.lab().start_local_model()
        ports.assert_called_once_with(LOCAL_MODEL_PORTS, (environment.LOCAL_MODEL_CONTAINER,))
        script = scripts[0]
        compose = f"docker compose -p {environment.LOCAL_MODEL_PROJECT} -f {LOCAL_MODEL_COMPOSE_FILE}"
        download = script.index(f"{compose} run --rm --no-deps --entrypoint sh")
        self.assertLess(download, script.index(f"{compose} up -d"))
        self.assertIn(f"-e MODEL_FILE={environment.LOCAL_MODEL_FILE} -e MODEL_SHA256={environment.LOCAL_MODEL_SHA256}",
                      script)
        self.assertIn(environment.LOCAL_MODEL_URL, script)
        self.assertIn('sha256sum -c -', script)
        wait.assert_called_once_with(120)

    def test_wait_lists_the_models_of_the_server(self):
        lab = self.lab()
        models = json.dumps({"object": "list", "data": [{"id": "qwen2.5-0.5b-instruct"}]})
        with patch.object(ObservabilityLab, "_http_status", side_effect=[None, 503, 200]), \
             patch.object(ObservabilityLab, "_read", return_value=models) as read, \
             patch("doris_course.doris_client.time.sleep") as sleep, \
             patch("doris_course.doris_client.show_sql"), \
             patch("doris_course.doris_client.show_frame") as shown, \
             patch("doris_course.doris_client.card") as card:
            lab._wait_for_local_model(120)
        self.assertEqual(sleep.call_count, 2)
        self.assertEqual(read.call_args.args[0], f"{lab.local_model_url}/v1/models")
        self.assertEqual(shown.call_args.args[1]["model"].tolist(), ["qwen2.5-0.5b-instruct"])
        self.assertEqual(card.call_args.args[1:], ("ok", "The local model is running"))

    def test_wait_stops_when_the_server_does_not_answer(self):
        clock = itertools.count(0, 100)
        with patch.object(ObservabilityLab, "_http_status", return_value=None), \
             patch("doris_course.doris_client.time.monotonic", side_effect=lambda: next(clock)), \
             patch("doris_course.doris_client.time.sleep"), \
             patch("doris_course.doris_client.show_sql"), \
             patch("doris_course.doris_client.card") as card:
            with self.assertRaises(EnvironmentNotReady):
                self.lab()._wait_for_local_model(120)
        self.assertEqual(card.call_args.args[1:], ("fail", "The model server does not answer"))
        self.assertIn(f"docker logs {environment.LOCAL_MODEL_CONTAINER}", card.call_args.args[0])

    def test_openai_key_comes_from_the_environment_and_is_never_shown(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-course-test-key"}), \
             patch("doris_course.doris_client.card") as card:
            self.assertEqual(self.lab().openai_api_key(), "sk-course-test-key")
        card.assert_not_called()
        with patch.dict("os.environ", {"OPENAI_API_KEY": "  "}), \
             patch("doris_course.doris_client.card") as card:
            with self.assertRaises(EnvironmentNotReady):
                self.lab().openai_api_key()
        self.assertEqual(card.call_args.args[1:], ("fail", "OPENAI_API_KEY is not set"))

    def test_stop_keeps_the_downloaded_model(self):
        with patch("doris_course.doris_client.run_shell") as shell:
            self.lab().stop_local_model()
        self.assertEqual(shell.call_args.args[0], f"docker compose -p {environment.LOCAL_MODEL_PROJECT} down")


class DemoReadinessTests(unittest.TestCase):
    def test_demo_containers_come_from_the_compose_project(self):
        lab = object.__new__(ObservabilityLab)
        listed = subprocess.CompletedProcess([], 0, "id2\nid1\n", "")
        inspected = subprocess.CompletedProcess([], 0, json.dumps([
            {"Name": "/doris-obs-demo-kafka", "State": {"Status": "running"}, "RestartCount": 0},
            {"Name": "/doris-obs-demo-ad", "State": {"Status": "restarting"}, "RestartCount": 3},
        ]), "")
        with patch("doris_course.doris_client.run", side_effect=[listed, inspected]) as run:
            frame = lab._demo_containers()
        self.assertIn(f"label=com.docker.compose.project={environment.DEMO_PROJECT}", run.call_args_list[0].args[0])
        self.assertEqual(run.call_args_list[1].args[0], ["docker", "container", "inspect", "id2", "id1"])
        self.assertEqual(frame.to_dict("records"), [
            {"container": "doris-obs-demo-ad", "state": "restarting", "restarts": 3},
            {"container": "doris-obs-demo-kafka", "state": "running", "restarts": 0},
        ])

    def test_start_waits_until_every_container_runs_and_the_storefront_answers(self):
        lab = object.__new__(ObservabilityLab)
        starting = demo_frame(("doris-obs-demo-ad", "restarting", 1), ("doris-obs-demo-kafka", "running", 0))
        running = demo_frame(("doris-obs-demo-ad", "running", 1), ("doris-obs-demo-kafka", "running", 0))
        with patch.object(ObservabilityLab, "_demo_containers", side_effect=[starting, running, running]), \
             patch.object(ObservabilityLab, "_storefront_status", side_effect=[None, None, 200]), \
             patch("doris_course.doris_client.time.sleep") as sleep, \
             patch("doris_course.doris_client.show_frame") as shown, \
             patch("doris_course.doris_client.card") as card:
            lab._wait_for_demo(180)
        self.assertEqual(sleep.call_count, 2)
        # The container that restarted is listed before the demo is reported as running.
        self.assertEqual(shown.call_args.args[1]["container"].tolist(), ["doris-obs-demo-ad"])
        self.assertEqual(card.call_args.args[1:], ("ok", "The demo is running"))

    def test_container_that_is_not_running_stops_the_step(self):
        lab = object.__new__(ObservabilityLab)
        exited = demo_frame(("doris-obs-demo-ad", "exited", 0), ("doris-obs-demo-kafka", "running", 0))
        clock = itertools.count(0, 100)
        with patch.object(ObservabilityLab, "_demo_containers", return_value=exited), \
             patch.object(ObservabilityLab, "_storefront_status", return_value=200), \
             patch("doris_course.doris_client.time.monotonic", side_effect=lambda: next(clock)), \
             patch("doris_course.doris_client.time.sleep"), \
             patch("doris_course.doris_client.show_frame") as shown, \
             patch("doris_course.doris_client.card") as card:
            with self.assertRaises(EnvironmentNotReady):
                lab._wait_for_demo(180)
        self.assertEqual(shown.call_args.args[1]["container"].tolist(), ["doris-obs-demo-ad"])
        self.assertEqual(card.call_args.args[1:], ("fail", "The demo did not start"))

    def test_storefront_that_does_not_answer_stops_the_step(self):
        lab = object.__new__(ObservabilityLab)
        running = demo_frame(("doris-obs-demo-frontend-proxy", "running", 0))
        clock = itertools.count(0, 100)
        with patch.object(ObservabilityLab, "_demo_containers", return_value=running), \
             patch.object(ObservabilityLab, "_storefront_status", return_value=503), \
             patch("doris_course.doris_client.time.monotonic", side_effect=lambda: next(clock)), \
             patch("doris_course.doris_client.time.sleep"), \
             patch("doris_course.doris_client.card") as card:
            with self.assertRaises(EnvironmentNotReady):
                lab._wait_for_demo(180)
        message, kind, title = card.call_args.args
        self.assertEqual((kind, title), ("fail", "The storefront does not answer"))
        self.assertIn("HTTP 503", message)

    def test_storefront_status_reports_errors_and_timeouts(self):
        lab = object.__new__(ObservabilityLab)
        unavailable = urllib.error.HTTPError(lab.demo_url, 503, "Service Unavailable", {}, None)
        for outcome, expected in ((unavailable, 503), (TimeoutError("timed out"), None), (ConnectionRefusedError(), None)):
            with self.subTest(outcome=type(outcome).__name__), \
                 patch("doris_course.doris_client.urllib.request.urlopen", side_effect=outcome):
                self.assertEqual(lab._storefront_status(), expected)

    def test_storefront_status_asks_for_a_page(self):
        # Through an HTTP proxy, urllib sends the URL as written; the demo's Envoy answers 400 without a path.
        lab = object.__new__(ObservabilityLab)
        with patch.object(ObservabilityLab, "_http_status", return_value=200) as status:
            lab._storefront_status()
        self.assertEqual(status.call_args.args[0], f"{lab.demo_url}/")


if __name__ == "__main__":
    unittest.main()
