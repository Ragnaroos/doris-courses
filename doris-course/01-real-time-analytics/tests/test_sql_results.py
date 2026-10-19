"""Offline checks for SQL results, NULL display, and SQL error reporting."""

import unittest
from unittest.mock import Mock, patch

import pandas as pd
import pymysql

from doris_course import DorisLab
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


def failing_cursor(message):
    cursor = Mock()
    cursor.execute.side_effect = pymysql.err.ProgrammingError(1105, message)
    return cursor


def lab_with(cursor):
    lab = DorisLab.__new__(DorisLab)
    lab._redacted_tvf = ""
    lab.connection = connection_for(cursor)
    return lab


def rendered_html(display):
    return "".join(call.args[0].data for call in display.call_args_list)


class QueryResultTests(unittest.TestCase):
    def test_select_without_rows_returns_an_empty_frame_with_columns(self):
        cursor = result_cursor(["event_id", "event_time"], [])
        with patch.object(client, "show_frame") as show:
            frame = client.sql(
                connection_for(cursor), "SELECT event_id, event_time FROM events WHERE 1 = 0"
            )
        self.assertIsInstance(frame, pd.DataFrame)
        self.assertTrue(frame.empty)
        self.assertEqual(list(frame.columns), ["event_id", "event_time"])
        show.assert_called_once()

    def test_lab_sql_without_rows_supports_the_lab10_empty_check(self):
        lab = lab_with(result_cursor(["event_id"], []))
        with patch.object(client, "show_frame"):
            after_expiry = lab.sql("SELECT event_id FROM m10_marked_events")
        self.assertTrue(after_expiry.empty)
        self.assertEqual(after_expiry["event_id"].astype(int).tolist(), [])

    def test_quiet_execution_does_not_display_an_empty_result(self):
        cursor = result_cursor(["Job_Id"], [])
        with patch.object(client, "show_frame") as show, patch.object(client, "card") as card:
            frame = client.sql(
                connection_for(cursor), "ANALYZE TABLE events WITH SYNC",
                show_statement=False, quiet_success=True,
            )
        self.assertTrue(frame.empty)
        show.assert_not_called()
        card.assert_not_called()

    def test_statement_without_result_set_returns_affected_rows(self):
        cursor = result_cursor(None, [])
        cursor.rowcount = 3
        with patch.object(client, "card") as card:
            affected = client.sql(
                connection_for(cursor), "DELETE FROM events WHERE event_id < 4",
                show_statement=False,
            )
        self.assertEqual(affected, 3)
        card.assert_called_once()

    def test_integer_column_with_null_keeps_integer_values(self):
        cursor = result_cursor(["product_id", "category"], [
            {"product_id": 10, "category": "phone"},
            {"product_id": None, "category": None},
        ])
        with patch.object(client, "show_frame"):
            frame = client.sql(connection_for(cursor), "SELECT product_id, category FROM products")
        self.assertEqual(str(frame["product_id"].dtype), "Int64")
        self.assertEqual(frame["product_id"].iloc[0], 10)
        self.assertTrue(pd.isna(frame["product_id"].iloc[1]))

    def test_large_bigint_values_keep_full_precision(self):
        frame = client.result_frame([(9007199254740993,), (None,)], ["tablet_id"])
        self.assertEqual(int(frame["tablet_id"].iloc[0]), 9007199254740993)

    def test_lab_query_keeps_columns_and_nullable_integers(self):
        lab = lab_with(result_cursor(["event_id"], []))
        self.assertEqual(
            list(lab.query("SELECT event_id FROM events WHERE 1 = 0").columns), ["event_id"]
        )
        lab = lab_with(result_cursor(["event_id"], [{"event_id": 1}, {"event_id": None}]))
        self.assertEqual(str(lab.query("SELECT event_id FROM events").dtypes["event_id"]), "Int64")


class ShowFrameTests(unittest.TestCase):
    def test_every_null_form_is_rendered_as_null(self):
        frame = client.result_frame(
            [(10, 1.5, "phone", pd.Timestamp("2020-03-01")), (None, None, None, None)],
            ["user_id", "price", "brand", "event_time"],
        )
        with patch.object(client, "display") as display:
            client.show_frame("NULL join keys", frame)
        rendered = rendered_html(display)
        self.assertEqual(rendered.count("<td>NULL</td>"), 4)
        self.assertIn("<td>10</td>", rendered)
        for raw in ("<td>nan</td>", "<td>NaT</td>", "&lt;NA&gt;", "<td>None</td>", "<td>10.0</td>"):
            self.assertNotIn(raw, rendered)

    def test_empty_result_says_that_no_rows_were_returned(self):
        with patch.object(client, "display") as display:
            client.show_frame("Expired rows", client.result_frame([], ["event_id", "event_time"]))
        rendered = rendered_html(display)
        self.assertIn('colspan="2">No rows returned.', rendered)
        self.assertIn("0 row(s)", rendered)


class SqlErrorTests(unittest.TestCase):
    def test_error_is_reported_as_a_card_with_a_one_line_traceback(self):
        cursor = failing_cursor("errCode = 2, detailMessage = Table [missing] does not exist")
        with patch.object(client, "card") as card, patch.object(client, "show_log") as log:
            with self.assertRaises(pymysql.err.ProgrammingError) as raised:
                client.sql(
                    connection_for(cursor), "SELECT * FROM missing",
                    title="Missing table", show_statement=False,
                )
        card.assert_called_once_with("Table [missing] does not exist", "fail", "Missing table failed")
        self.assertIn("SELECT * FROM missing", log.call_args.args[1])
        self.assertEqual(
            raised.exception._render_traceback_(),
            ["ProgrammingError: Table [missing] does not exist"],
        )

    def test_lab_errors_show_the_redacted_statement_and_mask_credentials(self):
        cursor = failing_cursor(
            "errCode = 2, detailMessage = Access denied for s3.access_key=AKIAEXAMPLEACCESS"
        )
        lab = lab_with(cursor)
        lab._s3_access_key = "AKIAEXAMPLEACCESS"
        lab._s3_secret_key = "example-secret-value"
        lab._source_tvf = client.s3_tvf(
            DorisLab.S3_CONFIG, lab._s3_access_key, lab._s3_secret_key
        )
        lab._redacted_tvf = client.s3_tvf(
            DorisLab.S3_CONFIG, "{{S3_READ_ONLY_ACCESS_KEY}}", "{{S3_READ_ONLY_SECRET_KEY}}"
        )
        with patch.object(client, "card") as card, patch.object(client, "show_log") as log:
            with self.assertRaises(pymysql.err.ProgrammingError):
                lab.sql("SELECT COUNT(*) FROM {{COURSE_S3}}", title="Remote preview")
        shown = card.call_args.args[0] + log.call_args.args[1]
        self.assertNotIn("AKIAEXAMPLEACCESS", shown)
        self.assertNotIn("example-secret-value", shown)
        self.assertIn("{{S3_READ_ONLY_SECRET_KEY}}", log.call_args.args[1])
        self.assertIn("example-secret-value", cursor.execute.call_args.args[0])

    def test_lab_query_errors_are_reported(self):
        lab = lab_with(failing_cursor("errCode = 2, detailMessage = Unknown column 'x'"))
        with patch.object(client, "card") as card, patch.object(client, "show_log"):
            with self.assertRaises(pymysql.err.ProgrammingError):
                lab.query("SELECT x FROM events")
        card.assert_called_once_with("Unknown column 'x'", "fail", "SQL statement failed")

    def test_expected_statement_errors_do_not_show_a_failure_card(self):
        lab = lab_with(failing_cursor(
            "errCode = 2, detailMessage = Cannot drop a partition of a temporary table"
        ))
        with patch.object(client, "card") as card, patch.object(client, "show_log") as log:
            lab.expect_statement_error(
                "ALTER TABLE t DROP PARTITION p1",
                contains="temporary table",
                title="Rejected as expected",
            )
        self.assertEqual([call.args[1] for call in card.call_args_list], ["ok"])
        log.assert_not_called()


if __name__ == "__main__":
    unittest.main()
