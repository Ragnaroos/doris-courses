"""Offline checks for running SQL, result frames, NULL display, and SQL error cards."""

import unittest
from unittest.mock import Mock, patch

import pandas as pd
import pymysql

from doris_labkit import db
from doris_labkit import results


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


def failing_cursor(message):
    cursor = Mock()
    cursor.execute.side_effect = pymysql.err.ProgrammingError(1105, message)
    return cursor


def rendered_html(display):
    return "".join(call.args[0].data for call in display.call_args_list)


class SqlResultTests(unittest.TestCase):
    def test_select_without_rows_returns_an_empty_frame_with_columns(self):
        cursor = result_cursor(["event_id", "event_time"], [])
        with patch.object(db, "show_frame") as show:
            frame = db.sql(connection_for(cursor), "SELECT event_id, event_time FROM events WHERE 1 = 0")
        self.assertIsInstance(frame, pd.DataFrame)
        self.assertTrue(frame.empty)
        self.assertEqual(list(frame.columns), ["event_id", "event_time"])
        show.assert_called_once()

    def test_quiet_execution_does_not_display_an_empty_result(self):
        cursor = result_cursor(["Job_Id"], [])
        with patch.object(db, "show_frame") as show, patch.object(db, "card") as card:
            frame = db.sql(
                connection_for(cursor), "ANALYZE TABLE events WITH SYNC",
                show_statement=False, quiet_success=True,
            )
        self.assertTrue(frame.empty)
        show.assert_not_called()
        card.assert_not_called()

    def test_statement_without_result_set_returns_affected_rows(self):
        cursor = result_cursor(None, [])
        cursor.rowcount = 3
        with patch.object(db, "card") as card:
            affected = db.sql(
                connection_for(cursor), "DELETE FROM events WHERE event_id < 4",
                show_statement=False,
            )
        self.assertEqual(affected, 3)
        card.assert_called_once()

    def test_trailing_semicolon_is_not_sent(self):
        cursor = result_cursor(["service_name"], [])
        with patch.object(db, "show_frame"), patch.object(db, "show_sql") as shown:
            db.sql(connection_for(cursor), "SELECT service_name FROM otel_logs;\n")
        cursor.execute.assert_called_once_with("SELECT service_name FROM otel_logs")
        self.assertEqual(shown.call_args.args[1], "SELECT service_name FROM otel_logs")

    def test_integer_column_with_null_keeps_integer_values(self):
        cursor = result_cursor(["product_id", "category"], [
            {"product_id": 10, "category": "phone"},
            {"product_id": None, "category": None},
        ])
        with patch.object(db, "show_frame"):
            frame = db.sql(connection_for(cursor), "SELECT product_id, category FROM products")
        self.assertEqual(str(frame["product_id"].dtype), "Int64")
        self.assertEqual(frame["product_id"].iloc[0], 10)
        self.assertTrue(pd.isna(frame["product_id"].iloc[1]))

    def test_large_bigint_values_keep_full_precision(self):
        frame = results.result_frame([(9007199254740993,), (None,)], ["tablet_id"])
        self.assertEqual(int(frame["tablet_id"].iloc[0]), 9007199254740993)


class ShowFrameTests(unittest.TestCase):
    def test_every_null_form_is_rendered_as_null(self):
        frame = results.result_frame(
            [(10, 1.5, "phone", pd.Timestamp("2020-03-01")), (None, None, None, None)],
            ["user_id", "price", "brand", "event_time"],
        )
        with patch.object(results, "display") as display:
            results.show_frame("NULL join keys", frame)
        rendered = rendered_html(display)
        self.assertEqual(rendered.count("<td>NULL</td>"), 4)
        self.assertIn("<td>10</td>", rendered)
        for raw in ("<td>nan</td>", "<td>NaT</td>", "&lt;NA&gt;", "<td>None</td>", "<td>10.0</td>"):
            self.assertNotIn(raw, rendered)

    def test_empty_result_says_that_no_rows_were_returned(self):
        with patch.object(results, "display") as display:
            results.show_frame("Expired rows", results.result_frame([], ["event_id", "event_time"]))
        rendered = rendered_html(display)
        self.assertIn('colspan="2">No rows returned.', rendered)
        self.assertIn("0 row(s)", rendered)


class SqlErrorTests(unittest.TestCase):
    def test_error_is_reported_as_a_card_with_a_one_line_traceback(self):
        cursor = failing_cursor("errCode = 2, detailMessage = Table [missing] does not exist")
        with patch.object(db, "card") as card, patch.object(db, "show_log") as log:
            with self.assertRaises(pymysql.err.ProgrammingError) as raised:
                db.sql(
                    connection_for(cursor), "SELECT * FROM missing",
                    title="Missing table", show_statement=False,
                )
        card.assert_called_once_with("Table [missing] does not exist", "fail", "Missing table failed")
        self.assertIn("SELECT * FROM missing", log.call_args.args[1])
        self.assertEqual(
            raised.exception._render_traceback_(),
            ["ProgrammingError: Table [missing] does not exist"],
        )

    def test_error_details_show_the_display_statement_and_mask_secrets(self):
        cursor = failing_cursor("errCode = 2, detailMessage = Access denied for key=AKIAEXAMPLE")
        with patch.object(db, "card") as card, patch.object(db, "show_log") as log:
            with self.assertRaises(pymysql.err.ProgrammingError):
                db.sql(
                    connection_for(cursor), "SELECT * FROM S3('key' = 'AKIAEXAMPLE')",
                    show_statement=False, display_statement="SELECT * FROM S3('key' = '{{KEY}}')",
                    secrets=("AKIAEXAMPLE",),
                )
        shown = card.call_args.args[0] + log.call_args.args[1]
        self.assertNotIn("AKIAEXAMPLE", shown)
        self.assertIn("{{KEY}}", log.call_args.args[1])

    def test_expected_errors_can_skip_the_card(self):
        cursor = failing_cursor("errCode = 2, detailMessage = Cannot drop the only partition")
        with patch.object(db, "card") as card, patch.object(db, "show_log") as log:
            with self.assertRaises(pymysql.err.ProgrammingError):
                db.sql(connection_for(cursor), "ALTER TABLE t DROP PARTITION p1",
                       show_statement=False, show_errors=False)
        card.assert_not_called()
        log.assert_not_called()


class ConnectTests(unittest.TestCase):
    def test_connect_waits_for_the_port_and_returns_dict_rows(self):
        with patch.object(db, "wait_for_port") as wait, patch.object(db.pymysql, "connect") as connect:
            db.connect_doris("127.0.0.1", 29030, connect_timeout=5)
        wait.assert_called_once_with("127.0.0.1", 29030)
        self.assertEqual(connect.call_args.kwargs["port"], 29030)
        self.assertEqual(connect.call_args.kwargs["connect_timeout"], 5)
        self.assertIs(connect.call_args.kwargs["cursorclass"], pymysql.cursors.DictCursor)
        self.assertTrue(connect.call_args.kwargs["autocommit"])


if __name__ == "__main__":
    unittest.main()
