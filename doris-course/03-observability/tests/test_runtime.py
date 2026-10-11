"""Offline checks for the observability runtime boundary."""

import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from doris_course import DorisLab, ObservabilityLab


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
        lab.DORIS_CONTAINER = "doris"
        with patch("doris_course.doris_client.shutil.which", return_value="/usr/local/bin/docker"), \
             patch("doris_course.doris_client.docker_preflight", return_value=(True, "ready")), \
             patch("doris_course.doris_client.container_inspect", return_value=RUNNING), \
             patch("doris_course.doris_client.wait_for_health") as wait, \
             patch("doris_course.doris_client.run") as run:
            state = lab.start_container()
        self.assertEqual(state["State"]["Status"], "running")
        wait.assert_called_once_with("doris", timeout_seconds=300)
        run.assert_not_called()

    def test_stopped_container_is_started(self):
        lab = object.__new__(ObservabilityLab)
        lab.DORIS_CONTAINER = "doris"
        start_result = subprocess.CompletedProcess(["docker", "start", "doris"], 0, "doris", "")
        with patch("doris_course.doris_client.shutil.which", return_value="/usr/local/bin/docker"), \
             patch("doris_course.doris_client.docker_preflight", return_value=(True, "ready")), \
             patch("doris_course.doris_client.container_inspect", side_effect=[STOPPED, RUNNING]), \
             patch("doris_course.doris_client.wait_for_health"), \
             patch("doris_course.doris_client.run", return_value=start_result) as run:
            lab.start_container()
        run.assert_called_once_with(["docker", "start", "doris"], show=True)

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
