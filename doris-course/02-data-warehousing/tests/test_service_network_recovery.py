"""Keep optional services reachable when the course container is recreated."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dw_course import docker_runtime as docker
from dw_course.onboarding import SetupRequired


class ServiceNetworkRecoveryTest(unittest.TestCase):
    def test_inspection_scopes_container_and_networks_to_this_course(self):
        networks = {
            "doris-warehousing-course_default": {"Aliases": ["doris"]},
            "doris-warehousing-bi_default": {"Aliases": ["course-doris", "saved-alias"]},
            "unrelated_default": {"Aliases": ["other"]},
        }
        with patch.object(docker, "_docker_output", side_effect=["old-container", json.dumps(networks)]) as output:
            container, saved = docker._course_networks()
        self.assertEqual(container, "old-container")
        self.assertEqual(set(saved), {"doris-warehousing-bi_default"})
        self.assertEqual(output.call_args_list[0], call(docker.compose_command("ps", "--all", "--quiet", "doris")))

    def test_first_start_has_no_attachments_to_restore(self):
        with patch.object(docker, "_docker_output", return_value=""):
            self.assertEqual(docker._course_networks(), ("", {}))
        with patch.object(docker, "_course_networks") as inspect, patch.object(docker, "_run") as run:
            docker._restore_course_networks({}, Mock())
        inspect.assert_not_called()
        run.assert_not_called()

    def test_restore_aliases_on_new_container_but_skip_attached_or_deleted_networks(self):
        saved = {
            "doris-warehousing-bi_default": {"Aliases": ["course-doris", "saved-alias", "saved-alias"]},
            "doris-warehousing-lake_default": {"Aliases": ["course-doris"]},
            "doris-warehousing-backup_default": {"Aliases": ["course-doris"]},
        }
        progress = Mock()
        with patch.object(docker, "_course_networks", return_value=("new-container", {"doris-warehousing-lake_default": {}})), patch.object(
            docker, "_docker_output", return_value="doris-warehousing-bi_default\ndoris-warehousing-lake_default"
        ), patch.object(docker, "_run") as run:
            docker._restore_course_networks(saved, progress)
        run.assert_called_once_with([
            "docker", "network", "connect", "--alias", "course-doris", "--alias", "saved-alias",
            "doris-warehousing-bi_default", "new-container"], progress)

    def test_prepare_restores_after_up_before_verifying_sql_in_both_modes(self):
        for streaming in (False, True):
            events = []
            saved = {"doris-warehousing-bi_default": {"Aliases": ["course-doris"]}}
            def run(command, *args, **kwargs):
                if "up" in command:
                    events.append("up")
            with patch.object(docker, "_run", side_effect=run), patch.object(docker, "check_host_ports"), patch.object(
                docker, "_course_networks", return_value=("old-container", saved)
            ), patch.object(docker, "_restore_course_networks", side_effect=lambda previous, progress: events.append(("restore", previous))), patch.object(
                docker, "_verify_sql", side_effect=lambda settings: events.append("sql")
            ), patch("dw_course.streaming.check_resources"):
                docker.prepare_environment(start=True, streaming=streaming)
            self.assertEqual(events, ["up", ("restore", saved), "sql"])

    def test_failed_restore_does_not_claim_success(self):
        import subprocess
        with patch.object(docker, "_course_networks", return_value=("new", {})), patch.object(
            docker, "_docker_output", return_value="doris-warehousing-bi_default"
        ), patch.object(docker, "_run", side_effect=subprocess.CalledProcessError(1, "connect", output="endpoint failed")):
            with self.assertRaisesRegex(SetupRequired, "could not restore"):
                docker._restore_course_networks({"doris-warehousing-bi_default": {}}, Mock())


if __name__ == "__main__":
    unittest.main()
