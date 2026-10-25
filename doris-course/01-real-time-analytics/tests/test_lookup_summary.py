"""Lookup summaries retain task scopes and distinguish absent counters from zero."""

import unittest

import pandas as pd

from doris_course.profiles import QueryEvidence, lookup_scan_summary


def evidence(profile, profile_id="query-1", result_rows=1):
    return QueryEvidence(pd.DataFrame({"event_id": range(result_rows)}), "", profile_id, profile)


class LookupSummaryTests(unittest.TestCase):
    def test_detail_tasks_do_not_mix_with_merged_or_other_operator_counters(self):
        profile = """MergedProfile:
  Fragment 1:
    OLAP_SCAN_OPERATOR(table_name=events(events))(id=0):
      - ScanRows: sum 999, avg 999, max 999, min 999
DetailProfile(query-1):
  Fragment 1:
    Pipeline 2(host=TNetworkAddress(hostname:be-a, port:9050)):
      PipelineTask(index=0):
        OLAP_SCAN_OPERATOR(table_name=events(events))(id=0):
          - ScanRows: 9
          - RowsInvertedIndexFiltered: 0
        AGGREGATION_OPERATOR(id=1):
          - ScanRows: 777
      PipelineTask(index=1):
        OLAP_SCAN_OPERATOR(table_name=events(events))(id=0):
          - ScanRows: 3
"""
        frame = lookup_scan_summary({"Without index": evidence(profile, result_rows=2)})
        self.assertEqual(frame["ScanRows"].tolist(), ["9", "3"])
        self.assertEqual(frame["RowsInvertedIndexFiltered"].tolist(), ["0", "not shown"])
        self.assertEqual(frame["query result rows"].tolist(), [2, 2])
        self.assertEqual(frame["Profile ID"].tolist(), ["query-1", "query-1"])
        for index, scope in enumerate(frame["scan task"]):
            self.assertIn(f"Task {index}", scope)
            self.assertIn("be-a", scope)
            self.assertIn("Fragment 1", scope)
            self.assertIn("events(events)", scope)

    def test_missing_detail_does_not_substitute_merged_values_or_a_zero(self):
        frame = lookup_scan_summary({"Without index": evidence(
            "MergedProfile:\n OLAP_SCAN_OPERATOR(id=0):\n  - ScanRows: sum 12", result_rows=0,
        )})
        self.assertEqual(len(frame), 1)
        self.assertEqual(frame.iloc[0]["ScanRows"], "not shown")
        self.assertEqual(frame.iloc[0]["RowsInvertedIndexFiltered"], "not shown")
        self.assertEqual(frame.iloc[0]["query result rows"], 0)

    def test_comparison_keeps_query_identity_and_original_counter_units(self):
        profile = """DetailProfile(query-2):
  Fragment 1:
    Pipeline 2(host=TNetworkAddress(hostname:be-b, port:9050)):
      PipelineTask(index=2):
        OLAP_SCAN_OPERATOR(table_name=indexed(indexed))(id=3):
          - ScanRows: 1
          - RowsInvertedIndexFiltered: 75.259K (75259)
"""
        frame = lookup_scan_summary({
            "Without index": evidence("no detail", "query-1"),
            "With index": evidence(profile, "query-2"),
        })
        self.assertEqual(frame["query"].tolist(), ["Without index", "With index"])
        self.assertEqual(frame["Profile ID"].tolist(), ["query-1", "query-2"])
        self.assertEqual(frame["RowsInvertedIndexFiltered"].tolist(), ["not shown", "75.259K (75259)"])
        self.assertIn("scan 3", frame.iloc[1]["scan task"])

    def test_duplicate_counter_names_are_not_silently_overwritten(self):
        profile = """DetailProfile(query-1):
  Fragment 1:
    Pipeline 2(host=TNetworkAddress(hostname:be-a, port:9050)):
      PipelineTask(index=0):
        OLAP_SCAN_OPERATOR(table_name=events(events))(id=0):
          - ScanRows: 2
          - ScanRows: 3
"""
        frame = lookup_scan_summary({"lookup": evidence(profile)})
        self.assertEqual(frame.iloc[0]["ScanRows"], "multiple values; see detail")


if __name__ == "__main__":
    unittest.main()
