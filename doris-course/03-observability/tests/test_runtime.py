"""Offline checks for the observability runtime boundary."""

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
from doris_course.doris_client import CHECKOUT_STACK, CORE_PORTS, EnvironmentNotReady


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

    def test_teardown_removes_the_demo_before_the_network_it_joins(self):
        lab = object.__new__(ObservabilityLab)
        lab.lab_dir = Path.cwd()
        for keep_data, volumes in ((False, True), (True, False)):
            with patch("doris_course.doris_client.run_shell") as shell:
                lab.teardown(keep_data=keep_data)
            script = shell.call_args.args[0]
            demo = script.index(f"docker compose -p {environment.DEMO_PROJECT} down")
            containers = " ".join((*environment.MODULE2_COLLECTORS, environment.CPU_LOAD_CONTAINER))
            collectors = script.index(f"for name in {containers}; do")
            core = script.index(f"docker compose -p {environment.PROJECT} down")
            self.assertLess(demo, collectors)
            self.assertLess(collectors, core)
            self.assertEqual("--volumes" in script[core:], volumes)

    def test_shell_runs_from_the_course_root(self):
        lab = object.__new__(ObservabilityLab)
        lab.lab_dir = Path.cwd()
        result = lab.shell(
            'printf "course-root=%s" "$(pwd -P)"',
            title="Run a shell command",
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn(f"course-root={Path.cwd()}", result.stdout)


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


if __name__ == "__main__":
    unittest.main()
