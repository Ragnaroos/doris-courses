"""Offline checks for ObservabilityLab results and SQL error cards.

The shared behavior (empty results, NULL display, error cards) is tested in
doris-course/common/tests.
"""

import itertools
import unittest
from unittest.mock import Mock, patch

import pandas as pd
import pymysql

from doris_course import ObservabilityLab
from doris_course.doris_client import EnvironmentNotReady
from doris_labkit import db


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


if __name__ == "__main__":
    unittest.main()
