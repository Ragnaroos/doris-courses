"""Offline checks for the bounded lifecycle helpers used by Lab 10."""

import unittest
import json
import os
from pathlib import Path
from unittest.mock import Mock, patch

from doris_course import DorisLab
import doris_course.doris_client as client


ROOT = Path(__file__).resolve().parents[1]


class LifecycleHelperTests(unittest.TestCase):
    def test_lab10_initializes_from_root_and_module_directory(self):
        path = ROOT / "level3/module10-managing-data/lab10_manage_data.ipynb"
        notebook = json.loads(path.read_text())
        initialization = next(
            "".join(cell["source"])
            for cell in notebook["cells"]
            if cell["cell_type"] == "code"
            and "from pathlib import Path" in "".join(cell["source"])
        )
        original = Path.cwd()
        try:
            for directory in (ROOT, path.parent):
                os.chdir(directory)
                namespace = {}
                exec(initialization, namespace)
                self.assertEqual(namespace["COURSE_ROOT"], ROOT)
                self.assertIsInstance(namespace["lab"], DorisLab)
        finally:
            os.chdir(original)

    def test_storage_wait_rejects_missing_table_without_polling(self):
        lab = DorisLab.__new__(DorisLab)
        lab._metadata_rows = Mock(return_value=[])
        with self.assertRaisesRegex(RuntimeError, "Create and load"):
            lab.wait_for_storage_reports(["missing"], expected_rows=10)
        lab._metadata_rows.assert_called_once_with("SHOW TABLES LIKE 'missing'")

    def test_partition_wait_is_bounded_and_reports_last_names(self):
        lab = DorisLab.__new__(DorisLab)
        lab._metadata_rows = Mock(side_effect=[
            [{"table": "events"}],
            [{"PartitionName": "p1"}],
        ])
        with patch.object(client.time, "monotonic", side_effect=[0, 0, 61]), \
             patch.object(client.time, "sleep"):
            with self.assertRaisesRegex(TimeoutError, "p1"):
                lab.wait_for_partition_count(
                    "events", expected_count=2, timeout_seconds=60
                )

    def test_temporary_frontend_config_restores_after_body_failure(self):
        lab = DorisLab.__new__(DorisLab)
        lab._metadata_rows = Mock(return_value=[{
            "Key": "dynamic_partition_check_interval_seconds",
            "Value": "600",
            "IsMutable": "true",
        }])
        lab.execute = Mock()
        with self.assertRaisesRegex(RuntimeError, "body failed"):
            with lab.temporary_frontend_config({
                "dynamic_partition_check_interval_seconds": 5,
            }) as original:
                self.assertEqual(
                    original["dynamic_partition_check_interval_seconds"], "600"
                )
                raise RuntimeError("body failed")
        self.assertEqual(lab.execute.call_count, 2)
        self.assertIn("= '5'", lab.execute.call_args_list[0].args[0])
        self.assertIn("= '600'", lab.execute.call_args_list[1].args[0])

    def test_hourly_expiry_before_the_boundary_says_when_to_return(self):
        lab = DorisLab.__new__(DorisLab)
        lab._metadata_rows = Mock(side_effect=[
            [{"Tables_in_doris_course": "m10_retained_events"}],
            [{"event_time": "2026-10-19 22:06:05"}],
            [{"server_now": "2026-10-20 01:06:06", "time_zone": "Asia/Shanghai"}],
        ])
        lab.wait_for_partition_removal = Mock()
        with patch.object(client, "card") as card:
            with self.assertRaises(client.ReturnLater) as raised:
                lab.wait_for_hourly_partition_expiry(
                    "m10_retained_events", event_id=1001, start_offset=-3
                )
        self.assertEqual(card.call_args.args[1], "info")
        self.assertIn("2026-10-20 02:00:00", card.call_args.args[0])
        self.assertIn("54 minute(s)", card.call_args.args[0])
        self.assertIsInstance(raised.exception, RuntimeError)
        self.assertEqual(raised.exception._render_traceback_(), [
            "Stopped on purpose: rerun this cell at or after 2026-10-20 02:00 (Asia/Shanghai)."
        ])
        lab.wait_for_partition_removal.assert_not_called()

    def test_hourly_expiry_waits_for_the_partition_holding_the_event(self):
        lab = DorisLab.__new__(DorisLab)
        lab._metadata_rows = Mock(side_effect=[
            [{"Tables_in_doris_course": "m10_retained_events"}],
            [{"event_time": "2026-10-19 22:06:05"}],
            [{"server_now": "2026-10-20 02:00:30", "time_zone": "Asia/Shanghai"}],
            [
                {"PartitionName": "p2026101922",
                 "Range": "[types: [DATETIMEV2]; keys: [2026-10-19 22:00:00]; "
                          "..types: [DATETIMEV2]; keys: [2026-10-19 23:00:00]; )"},
                {"PartitionName": "p2026101923",
                 "Range": "[types: [DATETIMEV2]; keys: [2026-10-19 23:00:00]; "
                          "..types: [DATETIMEV2]; keys: [2026-10-20 00:00:00]; )"},
            ],
        ])
        lab.wait_for_partition_removal = Mock()
        lab.wait_for_hourly_partition_expiry(
            "m10_retained_events", event_id=1001, start_offset=-3, timeout_seconds=900
        )
        lab.wait_for_partition_removal.assert_called_once_with(
            "m10_retained_events", "p2026101922", timeout_seconds=900
        )

    def test_hourly_expiry_already_applied_does_not_wait(self):
        lab = DorisLab.__new__(DorisLab)
        lab._metadata_rows = Mock(side_effect=[
            [{"Tables_in_doris_course": "m10_retained_events"}],
            [],
        ])
        lab.wait_for_partition_removal = Mock()
        with patch.object(client, "card") as card:
            lab.wait_for_hourly_partition_expiry(
                "m10_retained_events", event_id=1001, start_offset=-3
            )
        self.assertEqual(card.call_args.args[1:], ("ok", "Hourly expiry already applied"))
        lab.wait_for_partition_removal.assert_not_called()

    def test_partition_holding_event_names_the_hour_and_its_sql(self):
        lab = DorisLab.__new__(DorisLab)
        lab._metadata_rows = Mock(side_effect=[
            [{"event_time": "2026-10-21 22:40:44"}],
            [
                {"PartitionName": "p2026102122",
                 "Range": "[types: [DATETIMEV2]; keys: [2026-10-21 22:00:00]; "
                          "..types: [DATETIMEV2]; keys: [2026-10-21 23:00:00]; )"},
                {"PartitionName": "p2026102123",
                 "Range": "[types: [DATETIMEV2]; keys: [2026-10-21 23:00:00]; "
                          "..types: [DATETIMEV2]; keys: [2026-10-22 00:00:00]; )"},
            ],
        ])
        with patch.object(client, "card") as card, patch.object(client, "show_log") as log:
            partition = lab.partition_holding_event("m10_retained_events", event_id=1001)
        self.assertEqual(partition, "p2026102122")
        self.assertIn("p2026102122", card.call_args.args[0])
        self.assertIn("SELECT event_time FROM m10_retained_events WHERE event_id = 1001;", log.call_args.args[1])

    def test_partition_holding_a_missing_event_is_none(self):
        lab = DorisLab.__new__(DorisLab)
        lab._metadata_rows = Mock(return_value=[])
        with patch.object(client, "card") as card:
            self.assertIsNone(lab.partition_holding_event("m10_retained_events", event_id=1001))
        self.assertEqual(card.call_args.args[1:], ("skip", "The event is already gone"))

    def test_lab10_moves_the_window_and_restores_the_interval(self):
        path = ROOT / "level3/module10-managing-data/lab10_manage_data.ipynb"
        cells = {cell["id"]: "".join(cell["source"]) for cell in json.loads(path.read_text())["cells"]}
        fast = cells["b1132789"]
        self.assertIn('"dynamic_partition.start" = "-2"', fast)
        self.assertIn("'dynamic_partition_check_interval_seconds' = '10'", fast)
        restore = fast.index("finally:")
        self.assertIn("{original_interval}", fast[restore:])
        self.assertNotIn("DROP PARTITION", fast)
        clock = cells["m10-real-clock-wait"]
        self.assertIn("WAIT_FOR_REAL_HOUR = False", clock)
        self.assertIn("lab.wait_for_hourly_partition_expiry(", clock)
        self.assertNotIn("Do not use Run All", "".join(cells.values()))

    def test_recycle_summary_selects_exact_partition_id(self):
        lab = DorisLab.__new__(DorisLab)
        lab._metadata_rows = Mock(return_value=[
            {"Type": "Partition", "Name": "p_restore", "PartitionId": "10",
             "DropTime": "now"},
            {"Type": "Partition", "Name": "p_restore", "PartitionId": "11",
             "DropTime": "later"},
        ])
        with patch.object(client, "show_frame"):
            frame = lab.recycle_partition_summary("p_restore", partition_id=11)
        self.assertEqual(frame["PartitionId"].tolist(), ["11"])


if __name__ == "__main__":
    unittest.main()
