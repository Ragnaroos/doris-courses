"""Offline checks for ObservabilityLab results and SQL error cards.

The shared behavior (empty results, NULL display, error cards) is tested in
doris-course/common/tests.
"""

import unittest
from unittest.mock import Mock, patch

import pymysql

from doris_course import ObservabilityLab
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


if __name__ == "__main__":
    unittest.main()
