"""Offline checks for the observability runtime boundary."""

import itertools
import json
import subprocess
import tempfile
import unittest
import urllib.error
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
            collectors = script.index(f"for name in {' '.join(environment.MODULE2_COLLECTORS)}; do")
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
