"""Offline checks for the idempotent sandbox restart boundary."""

import subprocess
import unittest
from unittest.mock import patch

from doris_course import DorisLab


RUNNING = {
    "State": {"Status": "running", "Health": {"Status": "healthy"}},
}
STOPPED = {
    "State": {"Status": "exited", "Health": {"Status": "unhealthy"}},
}


class RestartTests(unittest.TestCase):
    def test_running_container_is_reused(self):
        lab = object.__new__(DorisLab)
        with patch("doris_course.doris_client.shutil.which", return_value="/usr/local/bin/docker"), \
             patch("doris_course.doris_client.docker_preflight", return_value=(True, "ready")), \
             patch("doris_course.doris_client.container_inspect", return_value=RUNNING), \
             patch("doris_course.doris_client.wait_for_health") as wait, \
             patch("doris_course.doris_client.run") as run:
            state = lab.start_container("doris")
        self.assertEqual(state["State"]["Status"], "running")
        wait.assert_called_once_with("doris", timeout_seconds=300)
        run.assert_not_called()

    def test_stopped_container_is_started(self):
        lab = object.__new__(DorisLab)
        start_result = subprocess.CompletedProcess(["docker", "start", "doris"], 0, "doris", "")
        with patch("doris_course.doris_client.shutil.which", return_value="/usr/local/bin/docker"), \
             patch("doris_course.doris_client.docker_preflight", return_value=(True, "ready")), \
             patch("doris_course.doris_client.container_inspect", side_effect=[STOPPED, RUNNING]), \
             patch("doris_course.doris_client.wait_for_health"), \
             patch("doris_course.doris_client.run", return_value=start_result) as run:
            lab.start_container("doris")
        run.assert_called_once_with(["docker", "start", "doris"], show=True)

    def test_stopped_docker_desktop_is_opened_and_waited_for(self):
        lab = object.__new__(DorisLab)
        open_result = subprocess.CompletedProcess(["open", "-a", "Docker"], 0, "", "")
        with patch("doris_course.doris_client.shutil.which", return_value="/usr/local/bin/docker"), \
             patch("doris_course.doris_client.platform.system", return_value="Darwin"), \
             patch("doris_course.doris_client.docker_preflight",
                   side_effect=[(False, "socket missing"), (False, "starting"), (True, "ready")]), \
             patch("doris_course.doris_client.run", return_value=open_result) as run, \
             patch("doris_course.doris_client.time.sleep"):
            lab.ensure_docker_ready()
        run.assert_called_once_with(["open", "-a", "Docker"], check=False)


if __name__ == "__main__":
    unittest.main()
