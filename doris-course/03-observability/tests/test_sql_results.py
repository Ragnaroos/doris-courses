"""Offline checks for ObservabilityLab results, SQL error cards, and Query Profiles.

The shared behavior (empty results, NULL display, error cards, finding and
fetching profiles) is tested in doris-course/common/tests.
"""

import itertools
import unittest
import urllib.error
from unittest.mock import Mock, patch

import pandas as pd
import pymysql

from doris_course import ObservabilityLab
from doris_course.doris_client import EnvironmentNotReady
from doris_labkit import db

# A shortened Doris 4.1 profile of a query whose table scan ran as two instances.
PROFILE = """Summary:
   - Profile ID: a1-b2
   - Is Cached: No
MergedProfile:
           OLAP_SCAN_OPERATOR(nereids_id=66. table_name=otel_logs(otel_logs))(id=0):
                - RowsRead: sum 999, avg 999, max 999, min 999
DetailProfile(a1-b2):
          OLAP_SCAN_OPERATOR(nereids_id=66. table_name=otel_logs(otel_logs))(id=0):
               - RowsRead: 262
                 - PerScannerRowsRead: [0, 262, ]
                SegmentIterator:
                   - RowsInvertedIndexFiltered: 3.891K (3891)
                   - RowsStatsFiltered: 22.38K (22380)
                   - RowsVectorPredFiltered: 0
                   - RowsExprPredFiltered: 0
          OLAP_SCAN_OPERATOR(nereids_id=66. table_name=otel_logs(otel_logs))(id=0):
               - RowsRead: 14
                SegmentIterator:
                   - RowsInvertedIndexFiltered: 756
                   - RowsStatsFiltered: 1.673K (1673)
                   - RowsVectorPredFiltered: 0
                   - RowsExprPredFiltered: 12
"""
QUERY = "SELECT severity_text, COUNT(*) AS log_rows FROM otel_logs WHERE service_name = 'cart' GROUP BY severity_text"
PROFILE_ROW = {"Profile ID": "a1-b2", "Start Time": "2026-10-20 06:54:14", "Total": "11ms", "Sql Statement": QUERY}


def connection_for(cursor):
    """Return a connection whose ``cursor()`` context manager yields ``cursor``."""
    manager = Mock()
    manager.__enter__ = Mock(return_value=cursor)
    manager.__exit__ = Mock(return_value=False)
    connection = Mock()
    connection.cursor.return_value = manager
    return connection


def result_cursor(columns, rows):
    cursor = Mock()
    cursor.description = None if columns is None else [(name,) + (None,) * 6 for name in columns]
    cursor.fetchall.return_value = rows
    cursor.rowcount = len(rows)
    return cursor


def lab_with(cursor):
    lab = object.__new__(ObservabilityLab)
    lab.connection = connection_for(cursor)
    return lab


class LabQueryTests(unittest.TestCase):
    def test_integer_column_with_null_keeps_integer_values(self):
        lab = lab_with(result_cursor(["error_count"], [{"error_count": 7}, {"error_count": None}]))
        frame = lab.query("SELECT error_count FROM otel_logs_daily")
        self.assertEqual(str(frame["error_count"].dtype), "Int64")
        self.assertEqual(frame["error_count"].iloc[0], 7)


class LabErrorTests(unittest.TestCase):
    def test_error_is_reported_as_a_card_with_a_one_line_traceback(self):
        cursor = Mock()
        cursor.execute.side_effect = pymysql.err.ProgrammingError(
            1105, "errCode = 2, detailMessage = Unknown table 'otel_logs_missing'"
        )
        with patch.object(db, "card") as card, patch.object(db, "show_log") as log, \
             patch.object(db, "show_sql"):
            with self.assertRaises(pymysql.err.ProgrammingError) as raised:
                lab_with(cursor).sql("SELECT * FROM otel_logs_missing;", title="Error logs")
        card.assert_called_once_with("Unknown table 'otel_logs_missing'", "fail", "Error logs failed")
        self.assertIn("SELECT * FROM otel_logs_missing", log.call_args.args[1])
        self.assertEqual(
            raised.exception._render_traceback_(),
            ["ProgrammingError: Unknown table 'otel_logs_missing'"],
        )


class WaitForRowsTests(unittest.TestCase):
    def test_rows_are_shown_once_enough_arrive(self):
        lab = object.__new__(ObservabilityLab)
        empty, one, two = pd.DataFrame({"n": []}), pd.DataFrame({"n": [1]}), pd.DataFrame({"n": [1, 2]})
        with patch.object(ObservabilityLab, "query", side_effect=[empty, one, two]) as query, \
             patch("doris_course.doris_client.time.sleep") as sleep, \
             patch("doris_course.doris_client.show_sql") as statement, \
             patch("doris_course.doris_client.show_frame") as shown:
            frame = lab.wait_for_rows("SELECT n FROM t;", title="Rows", hint="Start it.", min_rows=2)
        self.assertIs(frame, two)
        query.assert_called_with("SELECT n FROM t")
        self.assertEqual(sleep.call_count, 2)
        # The learner sees the statement before the wait, and the rows once.
        self.assertEqual(statement.call_args.args[1], "SELECT n FROM t")
        shown.assert_called_once()
        self.assertIs(shown.call_args.args[1], two)

    def test_missing_rows_stop_with_the_hint(self):
        lab = object.__new__(ObservabilityLab)
        clock = itertools.count(0, 20)
        with patch.object(ObservabilityLab, "query", return_value=pd.DataFrame({"n": [1]})) as query, \
             patch("doris_course.doris_client.time.monotonic", side_effect=lambda: next(clock)), \
             patch("doris_course.doris_client.time.sleep"), \
             patch("doris_course.doris_client.show_sql"), \
             patch("doris_course.doris_client.show_frame"), \
             patch("doris_course.doris_client.card") as card:
            with self.assertRaises(EnvironmentNotReady) as raised:
                lab.wait_for_rows("SELECT n FROM t", title="Rows", hint="Start it.", min_rows=2, timeout_seconds=60)
        self.assertEqual(query.call_count, 3)
        card.assert_called_once_with("Start it.", "fail", "Only 1 of 2 rows after 60 seconds")
        self.assertEqual(raised.exception._render_traceback_(),
                         ["Stopped: Rows did not return 2 row(s) within 60 seconds."])


class QueryProfileTests(unittest.TestCase):
    def lab(self):
        lab = object.__new__(ObservabilityLab)
        lab.connection = Mock()
        return lab

    def profile_query(self, *, row=PROFILE_ROW, text=PROFILE, error=None):
        """Run profile_query with the profile lookups replaced; return the mocks that it called."""
        lab = self.lab()
        fetch = {"side_effect": error} if error else {"return_value": text}
        with patch.object(ObservabilityLab, "sql") as run_query, \
             patch("doris_course.doris_client.last_query_id", return_value="a1-b2") as last_id, \
             patch("doris_course.doris_client.find_profile", return_value=row) as find, \
             patch("doris_course.doris_client.fetch_profile_text", **fetch) as fetch_text, \
             patch("doris_course.doris_client.show_sql") as statement, \
             patch("doris_course.doris_client.show_frame"), \
             patch("doris_course.doris_client.show_log") as log, \
             patch("doris_course.doris_client.card") as card:
            calls = {"lab": lab, "run_query": run_query, "last_id": last_id, "find": find, "fetch": fetch_text,
                     "statement": statement, "log": log, "card": card}
            try:
                calls["text"] = lab.profile_query(QUERY, title="Log rows of cart")
            except EnvironmentNotReady as stopped:
                calls["stopped"] = stopped
        return calls

    def test_query_runs_and_its_own_profile_is_fetched_and_shown(self):
        calls = self.profile_query()
        lab = calls["lab"]
        self.assertEqual(calls["text"], PROFILE)
        calls["run_query"].assert_called_once_with(QUERY, title="Log rows of cart")
        # The profile is looked up by the ID of this run, not by its SQL: earlier runs share the SQL.
        self.assertEqual(calls["find"].call_args.args[1], "a1-b2")
        self.assertEqual(calls["fetch"].call_args.args[:2], (lab.fe_http_url, "a1-b2"))
        # The learner sees each step, so that it can be repeated in a MySQL client and a terminal.
        shown = [call.args[1] for call in calls["statement"].call_args_list]
        self.assertEqual(shown, [
            "SELECT last_query_id()",
            "SHOW QUERY PROFILE",
            f'curl -u root: "{lab.fe_http_url}/api/profile/text?query_id=a1-b2"',
        ])
        calls["log"].assert_called_once_with("Query Profile a1-b2", PROFILE)
        # The text is fetched again until the BEs have reported the scan.
        ready = calls["fetch"].call_args.kwargs["ready"]
        self.assertFalse(ready("Summary:\nMergedProfile:\n  OLAP_SCAN_OPERATOR(id=0):\n"))
        self.assertTrue(ready(PROFILE))

    def test_query_without_a_profile_stops_with_a_card(self):
        calls = self.profile_query(row=None)
        self.assertIn("stopped", calls)
        calls["fetch"].assert_not_called()
        self.assertEqual(calls["card"].call_args.args[2], "SHOW QUERY PROFILE does not list the query")
        self.assertIn("enable_profile = true", calls["card"].call_args.args[0])

    def test_profile_without_a_scan_stops_with_a_card(self):
        cases = (
            ("Summary:\n   - Is Cached: Yes\n   - Total Instances Num: 0\n", "The result came from the SQL cache"),
            ("Summary:\n   - Is Cached: No\n", "The profile has no table scan"),
        )
        for text, title in cases:
            with self.subTest(title=title):
                calls = self.profile_query(text=text)
                self.assertIn("stopped", calls)
                self.assertEqual(calls["card"].call_args.args[2], title)
                calls["log"].assert_not_called()

    def test_unreachable_fe_stops_with_a_card(self):
        calls = self.profile_query(error=urllib.error.URLError("Connection refused"))
        self.assertEqual(calls["card"].call_args.args[2], "The FE HTTP API does not answer")
        self.assertEqual(calls["stopped"]._render_traceback_(), ["Stopped: the FE HTTP API does not answer."])

    def test_scan_filters_add_up_the_scan_instances(self):
        with patch("doris_course.doris_client.show_frame") as shown:
            totals = self.lab().scan_filters(PROFILE)
        # Only DetailProfile is counted: MergedProfile repeats the totals in another format.
        self.assertEqual(totals.to_dict(), {
            "RowsStatsFiltered": 24053,
            "RowsInvertedIndexFiltered": 4647,
            "RowsVectorPredFiltered": 0,
            "RowsExprPredFiltered": 12,
            "RowsRead": 276,
        })
        frame = shown.call_args.args[1]
        self.assertEqual(list(frame["counter"]), list(totals.index))
        self.assertEqual(list(frame["rows"]), list(totals))

    def test_scan_filters_stop_when_the_profile_level_hides_counters(self):
        # At profile_level 1, the scan reports only its inverted-index counters.
        level1 = "DetailProfile(a1-b2):\n  OLAP_SCAN_OPERATOR(id=0):\n    - RowsInvertedIndexFiltered: 756\n"
        with patch("doris_course.doris_client.show_frame") as shown, \
             patch("doris_course.doris_client.card") as card:
            with self.assertRaises(EnvironmentNotReady):
                self.lab().scan_filters(level1)
        shown.assert_not_called()
        self.assertIn("RowsStatsFiltered, RowsVectorPredFiltered, RowsExprPredFiltered, RowsRead",
                      card.call_args.args[0])
        self.assertIn("profile_level 2", card.call_args.args[0])


# A shortened EXPLAIN plan of Doris 4.1.3: a scan that a materialized view answers,
# and a second view that Doris could not use.
PLAN = """PLAN FRAGMENT 0
  0:VOlapScanNode(192)
     TABLE: otel.otel_traces(server_minutes_mv), PREAGGREGATION: ON
     PREDICATES: (service_mv[#1] = 'payment')
     partitions=1/5 (p20261020)
     tablets=10/10, tabletList=1792538591526,1792538591528 ...
     cardinality=2553, avgRowSize=0.0, numNodes=1

========== MATERIALIZATIONS ==========

MaterializedView
MaterializedViewRewriteSuccessAndChose:
 CBO.internal.otel.otel_traces.server_minutes_mv chose

MaterializedViewRewriteSuccessButNotChose:

MaterializedViewRewriteFail:
 CBO.internal.otel.otel_traces.other_mv fail
  FailInfo: View struct info is invalid, View dimensions doesn't not cover the query dimensions

========== STATISTICS ==========
TABLE: not a scan
"""


class PlanTests(unittest.TestCase):
    def explain(self, plan):
        lab = object.__new__(ObservabilityLab)
        frame = pd.DataFrame({"Explain String(Nereids Planner)": plan.splitlines()})
        with patch.object(ObservabilityLab, "query", return_value=frame) as query, \
             patch("doris_course.doris_client.show_sql") as statement, \
             patch("doris_course.doris_client.show_frame") as shown, \
             patch("doris_course.doris_client.show_log") as log, \
             patch("doris_course.doris_client.card") as card:
            scans = lab.explain_scan("SELECT 1;", title="The plan")
        return scans, query, statement, shown, log, card

    def test_scans_and_materialized_views_are_read_from_the_plan(self):
        scans, query, statement, shown, log, card = self.explain(PLAN)
        query.assert_called_once_with("EXPLAIN SELECT 1")
        statement.assert_called_once_with("The plan", "EXPLAIN SELECT 1")
        self.assertEqual(scans.to_dict("records"), [{
            "table": "otel.otel_traces", "reads": "server_minutes_mv", "partitions": "1/5 (p20261020)",
            "tablets": "10/10", "predicates": "(service_mv[#1] = 'payment')",
        }])
        views = shown.call_args_list[1].args[1]
        self.assertEqual(views.to_dict("records"), [
            {"materialized_view": "server_minutes_mv", "result": "chosen", "reason": ""},
            {"materialized_view": "other_mv", "result": "not usable",
             "reason": "View struct info is invalid, View dimensions doesn't not cover the query dimensions"},
        ])
        log.assert_called_once_with("The whole plan", PLAN.rstrip("\n"))
        card.assert_not_called()

    def test_a_plan_without_a_scan_is_reported_with_a_card(self):
        # A filter that selects only empty partitions: Doris plans an empty set.
        scans, _, _, shown, _, card = self.explain("PLAN FRAGMENT 0\n  0:VEMPTYSET(115)\n========== STATISTICS ==========\n")
        self.assertTrue(scans.empty)
        shown.assert_not_called()
        self.assertEqual(card.call_args.args[2], "No table scan")

    def test_create_table_statement_is_shown_as_text(self):
        lab = object.__new__(ObservabilityLab)
        ddl = "CREATE TABLE `otel_logs` (\n  `timestamp` datetime(6) NULL\n) ENGINE=OLAP"
        answer = pd.DataFrame({"Table": ["otel_logs"], "Create Table": [ddl]})
        with patch.object(ObservabilityLab, "query", return_value=answer) as query, \
             patch("doris_course.doris_client.show_sql") as statement:
            self.assertEqual(lab.show_create_table("otel_logs"), ddl)
        query.assert_called_once_with("SHOW CREATE TABLE otel_logs")
        statement.assert_called_once_with("SHOW CREATE TABLE otel_logs returns", ddl)

    def test_tablet_rows_counts_each_tablet_of_the_partitions_with_data(self):
        lab = object.__new__(ObservabilityLab)
        answers = {
            "SHOW PARTITIONS FROM t": pd.DataFrame({"PartitionName": ["p1", "p2"], "VisibleVersion": ["1", "3"]}),
            "SHOW TABLETS FROM t PARTITION (p2)": pd.DataFrame({"TabletId": ["11", "12"]}),
            "SELECT COUNT(*) AS row_count FROM t TABLET(11)": pd.DataFrame({"row_count": [30]}),
            "SELECT COUNT(*) AS row_count FROM t TABLET(12)": pd.DataFrame({"row_count": [10]}),
        }
        with patch.object(ObservabilityLab, "query", side_effect=lambda statement: answers[statement]) as query, \
             patch("doris_course.doris_client.show_sql") as statement, \
             patch("doris_course.doris_client.show_frame"):
            frame = lab.tablet_rows("t")
        # Version 1 is an empty partition: its tablets are not counted.
        self.assertNotIn("SHOW TABLETS FROM t PARTITION (p1)", [call.args[0] for call in query.call_args_list])
        self.assertEqual(frame.to_dict("records"), [
            {"partition": "p2", "tablet": "11", "rows": 30, "percent_of_partition": 75.0},
            {"partition": "p2", "tablet": "12", "rows": 10, "percent_of_partition": 25.0},
        ])
        self.assertIn("SELECT COUNT(*) FROM t TABLET(<tablet id>)", statement.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
