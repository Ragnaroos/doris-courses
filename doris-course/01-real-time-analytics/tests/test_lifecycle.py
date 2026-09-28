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
