"""Offline checks that a helper shows the SQL it runs, so a learner can repeat it."""

import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from doris_course import DorisLab
from doris_course.profiles import capture_query
import doris_course.doris_client as client
import doris_course.profiles as profiles


ROOT = Path(__file__).resolve().parents[1]
PROFILE = """Summary:
   - Profile ID: q-1
MergedProfile:
  Fragment 0:
    Pipeline 0(instance_num=1):
      OLAP_SCAN_OPERATOR(nereids_id=1. table_name=events(events))(id=0):
        - ScanBytes: sum 1.00 MB
        - ScanRows: sum 12, avg 12, max 12, min 12
DetailProfile(q-1):
"""


def cells(relative_path):
    notebook = json.loads((ROOT / relative_path).read_text(encoding="utf-8"))
    return {cell.get("id"): "".join(cell["source"]) for cell in notebook["cells"]}


class FakeConnection:
    """Answers SHOW VARIABLES, SET, the course queries, and last_query_id()."""

    def __init__(self):
        self.settings = {
            "enable_profile": "false", "profile_level": "2", "enable_sql_cache": "true",
            "enable_query_cache": "false", "enable_condition_cache": "true",
        }
        self.executed = []

    def cursor(self):
        return FakeCursor(self)


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.rows = []
        self.description = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        self.connection.executed.append(sql)
        if sql.startswith("SHOW VARIABLES"):
            name = params[0]
            self.rows = [{"Variable_name": name, "Value": self.connection.settings[name]}]
        elif sql.startswith("SET "):
            self.connection.settings[sql.split()[1]] = params[0]
            self.rows = []
        elif sql.startswith("SELECT last_query_id()"):
            self.rows = [{"query_id": "q-1"}]
        elif sql.startswith("EXPLAIN"):
            self.rows = [{"Explain String": "TABLE: doris_course.events(events)"}]
        else:
            self.rows = [{"event_count": 1, "total_revenue": 2}]
            self.description = [("event_count",), ("total_revenue",)]

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


def lab_with(connection):
    lab = DorisLab.__new__(DorisLab)
    lab.connection = connection
    lab._profile_http_host = "127.0.0.1"
    lab._profile_http_port = 18030
    lab._profile_text = Mock(return_value=PROFILE)
    return lab


class VisibleSqlTests(unittest.TestCase):
    def test_design_summary_also_shows_the_raw_ddl(self):
        ddl = ("CREATE TABLE `events` (\n  `event_time` datetime NOT NULL\n) ENGINE=OLAP\n"
               "DUPLICATE KEY(`event_time`)\nDISTRIBUTED BY RANDOM BUCKETS AUTO\n"
               'PROPERTIES (\n"replication_allocation" = "tag.location.default: 1"\n);')
        lab = DorisLab.__new__(DorisLab)
        lab._metadata_rows = Mock(return_value=[{"Table": "events", "Create Table": ddl}])
        with patch.object(client, "show_frame"), patch.object(client, "show_log") as log:
            lab.table_design_summary("events")
        self.assertEqual(log.call_args.args, ("Complete SHOW CREATE TABLE events output", ddl))

    def test_profile_comparison_uses_last_query_id_and_lists_its_sql(self):
        connection = FakeConnection()
        lab = lab_with(connection)
        query = "SELECT COUNT(*) AS event_count, SUM(revenue) AS total_revenue FROM events"
        with patch.object(client, "show_frame") as frame, patch.object(client, "show_log") as log:
            lab.compare_profiles([("events", query)])
        lab._profile_text.assert_called_once_with("q-1")
        self.assertIn("SELECT last_query_id() AS query_id", connection.executed)
        panels = {call.args[0]: call.args[1] for call in log.call_args_list}
        statements = next(text for title, text in panels.items() if title.startswith("SQL run by"))
        for expected in ("SET enable_profile = true;", "SET enable_sql_cache = false;",
                         query + ";", "SELECT last_query_id();"):
            self.assertIn(expected, statements)
        commands = panels["Commands that print each Query Profile"]
        self.assertIn('curl -u root: "http://127.0.0.1:18030/api/profile/text?query_id=q-1"', commands)
        self.assertEqual(frame.call_args.args[1]["scan_rows"].tolist(), ["12"])
        self.assertEqual(connection.settings["enable_profile"], "false")

    def test_a_captured_query_shows_the_statements_with_its_result(self):
        connection = FakeConnection()
        lab = lab_with(connection)
        evidence = capture_query(lab, "SELECT region FROM m08_events")
        self.assertIn("SELECT region FROM m08_events", connection.executed)
        self.assertNotIn("course_profile_", " ".join(connection.executed))
        with patch.object(profiles, "show_frame"), patch.object(profiles, "show_log") as log:
            evidence.show_result("Direct query")
        title, text = log.call_args.args
        self.assertTrue(title.startswith("Direct query: SQL run"))
        for expected in ("SET enable_profile = true;", "EXPLAIN SELECT region FROM m08_events;",
                         "SELECT last_query_id();", "/api/profile/text?query_id=q-1"):
            self.assertIn(expected, text)


class NotebookSqlTests(unittest.TestCase):
    def test_lab2_captures_one_profile_by_hand_before_the_comparison(self):
        lab2 = cells("level1/module02-architecture/lab02_scan_less_data.ipynb")
        order = list(lab2)
        run, read = lab2["profile-by-hand-run"], lab2["profile-by-hand-read"]
        for statement in ("SET enable_profile = true", "SELECT last_query_id()", "SHOW QUERY PROFILE"):
            self.assertIn(statement, run)
        self.assertIn("/api/profile/text?query_id=", read)
        self.assertIn("UNSET VARIABLE enable_profile", read)
        self.assertLess(order.index("profile-by-hand-read"), order.index("1a51d978"))

    def test_lab9_names_the_sql_behind_its_own_replica_tables(self):
        lab9 = cells("level3/module09-sharding-replication/lab09_observe_sharding_and_replication.ipynb")
        for cell_id in ("020c49cc", "2498d98a"):
            self.assertIn(
                'lab.show_statements("SHOW REPLICA DISTRIBUTION FROM m09_events", "SHOW BACKENDS")',
                lab9[cell_id],
            )


if __name__ == "__main__":
    unittest.main()
