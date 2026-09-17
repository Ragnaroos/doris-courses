"""Offline checks for the evidence and background-job boundaries used in Lab 8."""

import unittest
from unittest.mock import patch

import pandas as pd

from doris_course.profiles import capture_query, scan_profile_excerpt, session_settings

from doris_course import DorisLab
import doris_course.doris_client as client


class FakeCursor:
    def __init__(self, lab):
        self.lab = lab
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        if sql.startswith("SHOW VARIABLES"):
            name = params[0]
            self.rows = ([{"Variable_name": name, "Value": self.lab.settings[name]}]
                         if name in self.lab.settings else [])
        elif sql.startswith("SET "):
            name = sql.split()[1]
            if params[0] == "fail":
                raise RuntimeError("setting failed")
            self.lab.settings[name] = params[0]
        else:
            raise RuntimeError("query failed")

    def fetchall(self):
        return self.rows


class FakeLab:
    def __init__(self):
        self.settings = {
            "enable_profile": "false", "profile_level": "1",
            "enable_sql_cache": "true", "enable_query_cache": "true",
            "enable_condition_cache": "true",
        }

    def _require_connection(self):
        return self

    def cursor(self):
        return FakeCursor(self)

    def _query_profiles(self):
        return []


class EvidenceTests(unittest.TestCase):
    def test_mv_queries_use_requested_objects_and_reject_unsafe_names(self):
        from unittest.mock import Mock

        lab = object.__new__(DorisLab)
        lab._metadata_rows = Mock(return_value=[
            {"TableName": "another_table", "RollupIndexName": "another_view"},
            {"TableName": "another_table", "RollupIndexName": "unrelated_view"},
        ])
        rows = lab.sync_mv_jobs("another_table", "another_view", database="another_db")
        self.assertEqual(len(rows), 1)
        lab._metadata_rows.assert_called_with("SHOW ALTER TABLE MATERIALIZED VIEW FROM `another_db`")
        lab.async_mv_tasks("async_view", database="another_db")
        statement = lab._metadata_rows.call_args.args[0]
        self.assertIn("MvDatabaseName = 'another_db'", statement)
        self.assertIn("MvName = 'async_view'", statement)
        with self.assertRaises(ValueError):
            lab.async_mv_tasks("view'; DROP TABLE t; --")

    def test_restore_after_partial_setup_and_failed_query(self):
        for failure in ("missing", "bad_value", "query"):
            lab = FakeLab()
            before = lab.settings.copy()
            with self.subTest(failure=failure), self.assertRaises(RuntimeError):
                if failure == "query":
                    capture_query(lab, "SELECT * FROM m08_events")
                else:
                    settings = {"enable_profile": "true"}
                    settings.update({"missing": "true"} if failure == "missing"
                                    else {"profile_level": "fail"})
                    with session_settings(lab, settings):
                        self.fail("Setup should fail before entering the body")
            self.assertEqual(lab.settings, before)

    def test_profile_scopes_and_absent_counters(self):
        profile = """MergedProfile:
  Fragment 0:
    Pipeline 1(instance_num=2):
      OLAP_SCAN_OPERATOR(table_name=a(a))(id=0):
        - ScanRows: sum 12, avg 6, max 9, min 3
      AGGREGATION_OPERATOR(id=1):
        - RowsProduced: sum 777
DetailProfile(query-id):
  Fragment 0:
    Pipeline 1(host=local):
      PipelineTask(index=0):
        OLAP_SCAN_OPERATOR(table_name=a(a))(id=0):
          - ScanRows: 9
          - RowsInvertedIndexFiltered: 99
      PipelineTask(index=1):
        OLAP_SCAN_OPERATOR(table_name=a(a))(id=0):
          - ScanRows: 3
"""
        merged = scan_profile_excerpt(profile)
        detail = scan_profile_excerpt(profile, detail=True)
        self.assertIn("sum 12, avg 6", merged)
        self.assertNotIn("777", merged)
        self.assertNotIn("RowsInvertedIndexFiltered", merged)
        self.assertNotIn("sum 12", detail)
        self.assertIn("host=local", detail)
        self.assertIn("PipelineTask(index=0)", detail)
        self.assertIn("PipelineTask(index=1)", detail)
        self.assertEqual(detail.count("RowsInvertedIndexFiltered"), 1)
        self.assertIn("not present", scan_profile_excerpt("no merged section"))

    def test_full_group_comparison_catches_equal_total_different_groups(self):
        left = pd.DataFrame([("a", 1), ("b", 2)], columns=["category", "n"])
        right = pd.DataFrame([("a", 2), ("b", 1)], columns=left.columns)
        with self.assertRaises(AssertionError):
            DorisLab.assert_same_rows(left, right)
        DorisLab.assert_same_rows(left, left.iloc[::-1])
        with self.assertRaises(AssertionError):
            DorisLab.assert_same_rows(left, pd.concat([left, left.iloc[:1]]))

    def test_old_success_cannot_satisfy_new_refresh(self):
        snapshots = [
            [{"TaskId": "old", "Status": "SUCCESS"}],
            [{"TaskId": "old", "Status": "SUCCESS"}, {"TaskId": "new", "Status": "RUNNING"}],
            [{"TaskId": "new", "Status": "SUCCESS"}],
        ]
        with patch.object(client.time, "sleep"), patch.object(client.time, "monotonic", return_value=0):
            row = DorisLab._wait_mv_job(lambda: snapshots.pop(0), lambda r: True,
                                "TaskId", "Status", {"old"}, "SUCCESS", {"FAILED"}, 10)
        self.assertEqual(row["TaskId"], "new")

    def test_failed_job_and_timeout_expose_state(self):
        with self.assertRaisesRegex(RuntimeError, "failure reason"):
            DorisLab._wait_mv_job(lambda: [{"id": "new", "state": "FAILED", "ErrorMsg": "failure reason"}],
                          lambda r: True, "id", "state", set(), "SUCCESS", {"FAILED"}, 10)
        with patch.object(client.time, "monotonic", side_effect=[0, 0, 11]), patch.object(client.time, "sleep"):
            with self.assertRaisesRegex(TimeoutError, "RUNNING"):
                DorisLab._wait_mv_job(lambda: [{"id": "new", "state": "RUNNING"}], lambda r: True,
                              "id", "state", set(), "SUCCESS", {"FAILED"}, 10)

    def test_candidate_name_is_not_selected_scan(self):
        class Evidence:
            plan = "TABLE: doris_course.m08_events(m08_events)\nCandidates: m08_sync_metrics"
        DorisLab.assert_scan(Evidence(), "m08_events")
        with self.assertRaises(AssertionError):
            DorisLab.assert_scan(Evidence(), "m08_events", "m08_sync_metrics")


if __name__ == "__main__":
    unittest.main()
