"""Offline checks that a Lab stops with a readable reason and a next step."""

import ast
import json
import subprocess
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch

from doris_course import DorisLab
import doris_course.doris_client as client


ROOT = Path(__file__).resolve().parents[1]
LABS = {
    number: next(ROOT.glob(f"level*/module{number:02d}-*/lab{number:02d}_*.ipynb"))
    for number in range(1, 11)
}


def code_cells(path):
    notebook = json.loads(path.read_text(encoding="utf-8"))
    return {cell["id"]: "".join(cell["source"]) for cell in notebook["cells"] if cell["cell_type"] == "code"}


def first_connect_cell(number):
    return next(source for source in code_cells(LABS[number]).values() if "lab.connect()" in source)


class StopTests(unittest.TestCase):
    def test_an_unreachable_doris_stops_with_one_line(self):
        lab = DorisLab.__new__(DorisLab)
        lab.connection = None
        lab._connection_host = "127.0.0.1"
        lab._connection_port = client.env.QUERY_PORT
        with patch.object(client.socket, "create_connection", side_effect=ConnectionRefusedError()), \
             patch.object(client, "card") as card:
            with self.assertRaises(client.EnvironmentNotReady) as raised:
                lab.query("SELECT 1")
        self.assertEqual(card.call_args.args[1:], ("fail", "Doris is not reachable"))
        self.assertIn("docker start doris-rta", card.call_args.args[0])
        self.assertEqual(raised.exception._render_traceback_(),
                         [f"Stopped: Doris is not reachable on 127.0.0.1:{client.env.QUERY_PORT}."])

    def test_connect_names_a_missing_or_stopped_container(self):
        for state, problem in ((None, "does not exist"), ({"State": {"Status": "exited"}}, "is exited")):
            lab = DorisLab.__new__(DorisLab)
            lab.connection = None
            with self.subTest(problem=problem), patch.object(client, "container_inspect", return_value=state), \
                 patch.object(client, "card") as card:
                with self.assertRaises(client.EnvironmentNotReady):
                    lab.connect()
                self.assertIn(f"Container doris-rta {problem}", card.call_args.args[0])

    def test_start_container_names_lab1_when_the_sandbox_is_missing(self):
        lab = DorisLab.__new__(DorisLab)
        with patch("doris_labkit.docker.shutil.which", return_value="/usr/local/bin/docker"), \
             patch("doris_labkit.docker.docker_preflight", return_value=(True, "ready")), \
             patch("doris_labkit.docker.container_inspect", return_value=None), \
             patch.object(client, "card") as card:
            with self.assertRaises(client.EnvironmentNotReady):
                lab.start_container()
        self.assertEqual(card.call_args.args[1:], ("fail", "The container is missing"))
        self.assertIn("Lab 1, Section 2", card.call_args.args[0])

    def test_missing_prerequisite_names_the_lab_to_complete(self):
        lab = DorisLab.__new__(DorisLab)
        lab._metadata_rows = Mock(side_effect=lambda statement: [] if statement.startswith("SHOW TABLES") else None)
        with patch.object(client, "card") as card, patch.object(client, "show_frame") as frame:
            with self.assertRaises(client.EnvironmentNotReady):
                lab.check_prerequisites(5)
        self.assertIn("Lab 4 (Model Data for Analytical Workloads)", card.call_args.args[0])
        self.assertEqual(frame.call_args.args[1]["rows"].tolist(), ["missing"])

    def test_complete_prerequisites_pass_with_a_green_check(self):
        lab = DorisLab.__new__(DorisLab)
        lab._metadata_rows = Mock(side_effect=lambda statement: (
            [{"Tables_in_doris_course": "t"}] if statement.startswith("SHOW TABLES")
            else [{"row_count": 10_158_080 if "events_modelled" in statement else 204_231}]
        ))
        with patch.object(client, "card") as card, patch.object(client, "show_log"):
            lab.check_prerequisites(8)
        self.assertEqual(card.call_args.args[1], "ok")
        self.assertIn("dim_products (204,231 rows)", card.call_args.args[0])

    def test_a_running_module9_cluster_stops_lab10(self):
        lab = DorisLab.__new__(DorisLab)
        running = subprocess.CompletedProcess([], 0, "doris-rta-m09-fe-1-1\ndoris-rta-m09-be-1-1\n", "")
        with patch.object(client, "run", return_value=running), patch.object(client, "card") as card:
            with self.assertRaises(client.EnvironmentNotReady):
                lab.check_module9_stopped()
        self.assertIn("compose.multinode.yml stop", card.call_args.args[0])

    def test_a_timed_out_cluster_wait_shows_the_last_rows_instead_of_a_dict(self):
        lab = DorisLab.__new__(DorisLab)
        rows = [{"BackendId": "1", "Host": "172.31.91.50", "Alive": "true"},
                {"BackendId": "2", "Host": "172.31.91.51", "Alive": "false"}]
        lab._metadata_rows = Mock(return_value=rows)
        with patch.object(client.time, "monotonic", side_effect=[0, 0, 200]), patch.object(client.time, "sleep"), \
             patch.object(client, "card") as card, patch.object(client, "show_frame") as frame:
            with self.assertRaises(client.WaitTimedOut) as raised:
                lab.wait_for_node_state("SHOW BACKENDS", expected_total=2, expected_alive=2, timeout_seconds=120)
        self.assertNotIn("{", str(raised.exception))
        self.assertIn("2 of 2 alive", card.call_args.args[0])
        self.assertEqual(frame.call_args.args[1]["Alive"].tolist(), ["true", "false"])
        self.assertTrue(raised.exception._render_traceback_()[0].startswith("Timed out:"))

    def test_a_failed_shell_step_stops_with_one_line(self):
        lab = DorisLab.__new__(DorisLab)
        lab.lab_dir = ROOT
        with patch.object(client, "run_shell", side_effect=RuntimeError("Prepare failed with exit status 9.")):
            with self.assertRaises(client.EnvironmentNotReady) as raised:
                lab.shell("exit 9", title="Prepare the Kafka source")
        self.assertEqual(raised.exception._render_traceback_(),
                         ["Stopped: Prepare the Kafka source failed; the log above shows why."])

    def test_scheduler_time_is_shown_in_the_session_time_zone(self):
        self.assertEqual(
            DorisLab._session_time("2026-10-21 16:57:12", "UTC", "Asia/Shanghai"),
            "2026-10-22 00:57:12 Asia/Shanghai (the FE reports 2026-10-21 16:57:12 in its system time zone, UTC)",
        )
        self.assertEqual(DorisLab._session_time("2026-10-21 16:57:12", "UTC", "UTC"), "2026-10-21 16:57:12 (UTC)")

    def test_a_failed_download_names_the_address_and_the_network(self):
        with tempfile.TemporaryDirectory() as directory:
            lab = DorisLab.__new__(DorisLab)
            lab.lab_dir = Path(directory)
            url = "https://doris-courses-public-dataset.s3.us-east-1.amazonaws.com/doris-course/lab3/v2/x.csv"
            with patch.object(client.urllib.request, "urlopen", side_effect=urllib.error.URLError("timed out")), \
                 patch.object(client, "card") as card:
                with self.assertRaises(client.EnvironmentNotReady):
                    lab.fetch_fixtures([("Sample", url, "downloads/x.csv", "stream_malformed_csv")])
            self.assertIn(url, card.call_args.args[0])
            self.assertIn("proxy, VPN, or firewall", card.call_args.args[0])
            self.assertFalse((Path(directory) / "downloads/x.csv.part").exists())


class NotebookTests(unittest.TestCase):
    def test_labs_2_to_8_start_the_sandbox_before_connecting(self):
        for number in range(2, 9):
            with self.subTest(lab=number):
                source = first_connect_cell(number)
                self.assertLess(source.index("lab.start_container()"), source.index("lab.connect()"))

    def test_labs_that_read_earlier_tables_check_them_first(self):
        for number in client.PREREQUISITES:
            with self.subTest(lab=number):
                source = first_connect_cell(number)
                self.assertIn(f"lab.check_prerequisites({number})", source)
                self.assertLess(source.index("lab.connect()"), source.index("lab.check_prerequisites"))
                self.assertNotIn("assert ", source)

    def test_lab10_refuses_to_run_beside_the_module9_cluster(self):
        source = first_connect_cell(10)
        self.assertTrue(source.startswith("lab.check_module9_stopped()"))

    def test_lab3_checks_the_kafka_port_and_explains_a_failed_start(self):
        kafka = next(source for source in code_cells(LABS[3]).values() if "compose.kafka.yml up -d" in source)
        self.assertIn("DORIS_RTA_KAFKA_PORT:-19092", kafka)
        self.assertIn("is already in use by another program", kafka)
        self.assertIn("docker pull apache/kafka:3.9.1", kafka)

    def test_lab7_shows_only_the_tablet_version(self):
        deletion = next(source for source in code_cells(LABS[7]).values() if "SHOW TABLETS FROM order_deletions" in source)
        self.assertEqual(deletion.count('columns=["TabletId", "Version"]'), 2)
        self.assertNotIn("VersionCount", deletion)

    def test_labs_reuse_an_image_that_docker_already_has(self):
        # A rerun must not need Docker Hub: it can be slow, blocked, or offline.
        pulls = 0
        for path in sorted(ROOT.glob("level*/module*/*.ipynb")):
            for cell_id, source in code_cells(path).items():
                for line in source.splitlines():
                    command = line.strip()
                    if "docker pull" not in command or command.startswith("echo"):
                        continue
                    pulls += 1
                    with self.subTest(notebook=path.name, cell=cell_id):
                        image = command.split("docker pull", 1)[1].strip()
                        self.assertIn(f"docker image inspect {image} >/dev/null 2>&1 || docker pull {image}", command)
        self.assertGreaterEqual(pulls, 4)

    def test_cells_do_not_show_a_returned_value_twice(self):
        for path in sorted(ROOT.glob("level*/module*/*.ipynb")):
            for cell_id, source in code_cells(path).items():
                body = ast.parse(source).body
                last = body[-1] if body else None
                if isinstance(last, ast.Expr) and isinstance(last.value, ast.Call):
                    with self.subTest(notebook=path.name, cell=cell_id):
                        self.assertTrue(source.rstrip().endswith(";"), source.rstrip().splitlines()[-1])


if __name__ == "__main__":
    unittest.main()
