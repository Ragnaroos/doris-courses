"""Offline checks for the idempotent container restart and Docker readiness helpers."""

import subprocess
import unittest
from unittest.mock import patch

from doris_labkit import docker


RUNNING = {
    "State": {"Status": "running", "Health": {"Status": "healthy"}},
}
STOPPED = {
    "State": {"Status": "exited", "Health": {"Status": "unhealthy"}},
}


class StartContainerTests(unittest.TestCase):
    def test_running_container_is_reused(self):
        with patch.object(docker.shutil, "which", return_value="/usr/local/bin/docker"), \
             patch.object(docker, "docker_preflight", return_value=(True, "ready")), \
             patch.object(docker, "container_inspect", return_value=RUNNING), \
             patch.object(docker, "wait_for_health") as wait, \
             patch.object(docker, "run") as run:
            state = docker.start_container("doris")
        self.assertEqual(state["State"]["Status"], "running")
        wait.assert_called_once_with("doris", timeout_seconds=300)
        run.assert_not_called()

    def test_stopped_container_is_started(self):
        start_result = subprocess.CompletedProcess(["docker", "start", "doris"], 0, "doris", "")
        with patch.object(docker.shutil, "which", return_value="/usr/local/bin/docker"), \
             patch.object(docker, "docker_preflight", return_value=(True, "ready")), \
             patch.object(docker, "container_inspect", side_effect=[STOPPED, RUNNING]), \
             patch.object(docker, "wait_for_health"), \
             patch.object(docker, "run", return_value=start_result) as run:
            docker.start_container("doris")
        run.assert_called_once_with(["docker", "start", "doris"], show=True)

    def test_missing_container_names_the_preparation_step(self):
        with patch.object(docker.shutil, "which", return_value="/usr/local/bin/docker"), \
             patch.object(docker, "docker_preflight", return_value=(True, "ready")), \
             patch.object(docker, "container_inspect", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "does not exist. Run prepare_environment"):
                docker.start_container("doris", missing_hint="Run prepare_environment() first.")

    def test_container_name_must_be_simple(self):
        with self.assertRaises(ValueError):
            docker.start_container("doris; rm -rf /")


class DockerReadyTests(unittest.TestCase):
    def test_stopped_docker_desktop_is_opened_and_waited_for(self):
        open_result = subprocess.CompletedProcess(["open", "-a", "Docker"], 0, "", "")
        with patch.object(docker.shutil, "which", return_value="/usr/local/bin/docker"), \
             patch.object(docker.platform, "system", return_value="Darwin"), \
             patch.object(docker, "docker_preflight",
                          side_effect=[(False, "socket missing"), (False, "starting"), (True, "ready")]), \
             patch.object(docker, "run", return_value=open_result) as run, \
             patch.object(docker.time, "sleep"):
            docker.ensure_docker_ready()
        run.assert_called_once_with(["open", "-a", "Docker"], check=False)

    def test_stopped_engine_on_linux_explains_what_to_do(self):
        with patch.object(docker.shutil, "which", return_value="/usr/bin/docker"), \
             patch.object(docker.platform, "system", return_value="Linux"), \
             patch.object(docker, "docker_preflight", return_value=(False, "Cannot connect")):
            with self.assertRaisesRegex(RuntimeError, "Docker Engine is not running"):
                docker.ensure_docker_ready()


class PortTests(unittest.TestCase):
    def test_env_port_uses_the_default_and_shares_it_with_child_processes(self):
        with patch.dict(docker.os.environ, {}, clear=True):
            self.assertEqual(docker.env_port("COURSE_QUERY_PORT", 19030), 19030)
            self.assertEqual(docker.os.environ["COURSE_QUERY_PORT"], "19030")

    def test_env_port_reads_an_override(self):
        with patch.dict(docker.os.environ, {"COURSE_QUERY_PORT": " 29030 "}, clear=True):
            self.assertEqual(docker.env_port("COURSE_QUERY_PORT", 19030), 29030)

    def test_env_port_rejects_values_that_are_not_ports(self):
        for value in ("abc", "0", "70000", "-1"):
            with patch.dict(docker.os.environ, {"COURSE_QUERY_PORT": value}, clear=True):
                with self.assertRaisesRegex(ValueError, "COURSE_QUERY_PORT"):
                    docker.env_port("COURSE_QUERY_PORT", 19030)

    def test_port_in_use_detects_a_listener(self):
        import socket

        with socket.socket() as server:
            server.bind(("127.0.0.1", 0))
            server.listen(1)
            port = server.getsockname()[1]
            self.assertTrue(docker.port_in_use(port))
        self.assertFalse(docker.port_in_use(port))


class RunTests(unittest.TestCase):
    def test_run_uses_the_working_directory(self):
        result = docker.run(["pwd"], cwd="/")
        self.assertEqual(result.stdout.strip(), "/")

    def test_failed_command_raises_with_the_exit_code(self):
        with patch.object(docker, "show_log"):
            with self.assertRaisesRegex(RuntimeError, "exit code 3"):
                docker.run(["sh", "-c", "exit 3"])


if __name__ == "__main__":
    unittest.main()
