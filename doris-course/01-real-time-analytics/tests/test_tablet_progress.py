"""Tablet report progress must preserve completeness and timeout checks."""

import unittest
from unittest.mock import Mock, patch

from doris_course import DorisLab
import doris_course.doris_client as client


class TabletProgressTests(unittest.TestCase):
    def lab(self):
        lab = DorisLab.__new__(DorisLab)
        lab.show_statements = Mock()
        return lab

    def test_progress_waits_for_both_reports_and_deduplicates_replicas(self):
        lab = self.lab()
        lab._metadata_rows = Mock(side_effect=[
            [{"table": "events"}], [{"row_count": 10}],
            [{"TabletId": 1, "RowCount": 5}, {"TabletId": 1, "RowCount": 4},
             {"TabletId": 2, "RowCount": 0}], [{"RowCount": 0}],
            [{"TabletId": 1, "RowCount": 5}, {"TabletId": 1, "RowCount": 5},
             {"TabletId": 2, "RowCount": 5}, {"TabletId": 2, "RowCount": 5}],
            [{"RowCount": 10}],
        ])
        handle = Mock()
        with patch.object(client, "display", return_value=handle) as display, \
             patch.object(client, "card") as card, \
             patch.object(client.time, "monotonic", return_value=0), \
             patch.object(client.time, "sleep") as sleep:
            lab.wait_for_tablet_rows("events", expected_rows=10)
        initial = display.call_args.args[0].data
        self.assertIn("expected 10 committed rows", initial)
        self.assertIn("not yet polled", initial)
        updates = [call.args[0].data for call in handle.update.call_args_list]
        self.assertIn("Tablet rows 5", updates[0])
        self.assertIn("Partition rows 0", updates[0])
        self.assertIn("Tablet rows 10", updates[1])
        self.assertEqual(updates[-1], "")
        sleep.assert_called_once_with(2)
        self.assertIn("2 tablets", card.call_args.args[0])
        lab.show_statements.assert_called_once()

    def test_timeout_exposes_both_late_counts_and_stops_progress(self):
        lab = self.lab()
        def metadata(sql):
            if sql.startswith("SHOW TABLES"):
                return [{"table": "events"}]
            if sql.startswith("SELECT"):
                return [{"row_count": 10}]
            if sql.startswith("SHOW TABLETS"):
                return [{"TabletId": 1, "RowCount": 10}]
            return [{"RowCount": 0}]
        lab._metadata_rows = Mock(side_effect=metadata)
        clock = [0]
        handle = Mock()
        with patch.object(client, "display", return_value=handle), \
             patch.object(client, "card"), \
             patch.object(client.time, "monotonic", side_effect=lambda: clock[0]), \
             patch.object(client.time, "sleep", side_effect=lambda n: clock.__setitem__(0, clock[0] + n)):
            with self.assertRaisesRegex(TimeoutError, "tablets report 10 rows.*partitions report 0"):
                lab.wait_for_tablet_rows("events", expected_rows=10, timeout_seconds=4)
        self.assertEqual(clock[0], 4)
        self.assertIn('doris-status failure', handle.update.call_args.args[0].data)
        lab.show_statements.assert_not_called()

    def test_incomplete_insert_fails_before_displaying_a_wait(self):
        lab = self.lab()
        lab._metadata_rows = Mock(side_effect=[[{"table": "events"}], [{"row_count": 9}]])
        with patch.object(client, "display") as display:
            with self.assertRaisesRegex(AssertionError, "Complete the preceding insert"):
                lab.wait_for_tablet_rows("events", expected_rows=10)
        display.assert_not_called()

    def test_metadata_error_stops_progress_and_keeps_the_original_error(self):
        lab = self.lab()
        lab._metadata_rows = Mock(side_effect=[
            [{"table": "events"}], [{"row_count": 10}], RuntimeError("metadata unavailable"),
        ])
        handle = Mock()
        with patch.object(client, "display", return_value=handle):
            with self.assertRaisesRegex(RuntimeError, "metadata unavailable"):
                lab.wait_for_tablet_rows("events", expected_rows=10)
        self.assertIn('doris-status failure', handle.update.call_args.args[0].data)

    def test_report_check_also_works_without_a_notebook_display_handle(self):
        lab = self.lab()
        lab._metadata_rows = Mock(side_effect=[
            [{"table": "events"}], [{"row_count": 10}],
            [{"TabletId": 1, "RowCount": 10}], [{"RowCount": 10}],
        ])
        with patch.object(client, "display", return_value=None), patch.object(client, "card"):
            lab.wait_for_tablet_rows("events", expected_rows=10)


if __name__ == "__main__":
    unittest.main()
