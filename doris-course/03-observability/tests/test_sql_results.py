"""Offline checks for SQL results, NULL display, and SQL error reporting."""

import unittest
from unittest.mock import Mock, patch

import pandas as pd
import pymysql

from doris_course import ObservabilityLab
import doris_course.doris_client as client


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


class QueryResultTests(unittest.TestCase):
    def test_select_without_rows_returns_an_empty_frame_with_columns(self):
        cursor = result_cursor(["service_name", "span_count"], [])
        with patch.object(client, "show_frame") as show:
            frame = client.sql(connection_for(cursor), "SELECT service_name, span_count FROM t")
        self.assertTrue(frame.empty)
        self.assertEqual(list(frame.columns), ["service_name", "span_count"])
        show.assert_called_once()

    def test_integer_column_with_null_keeps_integer_values(self):
        lab = lab_with(result_cursor(["error_count"], [{"error_count": 7}, {"error_count": None}]))
        frame = lab.query("SELECT error_count FROM otel_logs_daily")
        self.assertEqual(str(frame["error_count"].dtype), "Int64")
        self.assertEqual(frame["error_count"].iloc[0], 7)


class ShowFrameTests(unittest.TestCase):
    def test_every_null_form_is_rendered_as_null(self):
        frame = client.result_frame(
            [(7, 0.98, "checkout"), (None, None, None)],
            ["error_count", "cpu_utilization", "service_name"],
        )
        with patch.object(client, "display") as display:
            client.show_frame("Service errors", frame)
        rendered = "".join(call.args[0].data for call in display.call_args_list)
        self.assertEqual(rendered.count("<td>NULL</td>"), 3)
        self.assertIn("<td>7</td>", rendered)
        for raw in ("<td>nan</td>", "&lt;NA&gt;", "<td>None</td>", "<td>7.0</td>"):
            self.assertNotIn(raw, rendered)


class SqlErrorTests(unittest.TestCase):
    def test_error_is_reported_as_a_card_with_a_one_line_traceback(self):
        cursor = Mock()
        cursor.execute.side_effect = pymysql.err.ProgrammingError(
            1105, "errCode = 2, detailMessage = Unknown table 'otel_logs_missing'"
        )
        with patch.object(client, "card") as card, patch.object(client, "show_log") as log:
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
