"""Offline checks for the observability runtime boundary."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from doris_course import DorisLab, ObservabilityLab, environment
from doris_course.doris_client import CHECKOUT_STACK, CORE_PORTS, EnvironmentNotReady


RUNNING = {
    "State": {"Status": "running", "Health": {"Status": "healthy"}},
}
STOPPED = {
    "State": {"Status": "exited", "Health": {"Status": "unhealthy"}},
}


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


if __name__ == "__main__":
    unittest.main()
