"""Offline checks for DorisLab results, error cards, and expected errors.

The shared behavior (empty results, NULL display, error cards) is tested in
doris-course/common/tests.
"""

import unittest
from unittest.mock import Mock, patch

import pymysql

from doris_course import DorisLab
import doris_course.doris_client as client
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


def failing_cursor(message):
    cursor = Mock()
    cursor.execute.side_effect = pymysql.err.ProgrammingError(1105, message)
    return cursor


def lab_with(cursor):
    lab = DorisLab.__new__(DorisLab)
    lab.connection = connection_for(cursor)
    return lab


class LabQueryTests(unittest.TestCase):
    def test_lab_sql_without_rows_supports_the_lab10_empty_check(self):
        lab = lab_with(result_cursor(["event_id"], []))
        with patch.object(db, "show_frame"):
            after_expiry = lab.sql("SELECT event_id FROM m10_marked_events")
        self.assertTrue(after_expiry.empty)
        self.assertEqual(after_expiry["event_id"].astype(int).tolist(), [])

    def test_lab_query_keeps_columns_and_nullable_integers(self):
        lab = lab_with(result_cursor(["event_id"], []))
        self.assertEqual(
            list(lab.query("SELECT event_id FROM events WHERE 1 = 0").columns), ["event_id"]
        )
        lab = lab_with(result_cursor(["event_id"], [{"event_id": 1}, {"event_id": None}]))
        self.assertEqual(str(lab.query("SELECT event_id FROM events").dtypes["event_id"]), "Int64")


class LabErrorTests(unittest.TestCase):
    def test_s3_statements_run_as_written_and_errors_show_them(self):
        cursor = failing_cursor("errCode = 2, detailMessage = Access Denied")
        lab = lab_with(cursor)
        statement = f"SELECT COUNT(*) FROM {client.s3_tvf(DorisLab.S3_CONFIG)}"
        with patch.object(db, "card") as card, patch.object(db, "show_log") as log:
            with self.assertRaises(pymysql.err.ProgrammingError):
                lab.sql(statement, title="Remote preview")
        card.assert_called_once_with("Access Denied", "fail", "Remote preview failed")
        self.assertIn('"s3.credentials_provider_type" = "ANONYMOUS"', log.call_args.args[1])
        self.assertEqual(cursor.execute.call_args.args[0], statement)

    def test_lab_query_errors_are_reported(self):
        lab = lab_with(failing_cursor("errCode = 2, detailMessage = Unknown column 'x'"))
        with patch.object(db, "card") as card, patch.object(db, "show_log"):
            with self.assertRaises(pymysql.err.ProgrammingError):
                lab.query("SELECT x FROM events")
        card.assert_called_once_with("Unknown column 'x'", "fail", "SQL statement failed")

    def test_expected_statement_errors_do_not_show_a_failure_card(self):
        lab = lab_with(failing_cursor(
            "errCode = 2, detailMessage = Cannot drop a partition of a temporary table"
        ))
        with patch.object(client, "card") as card, patch.object(db, "card") as failure_card, \
             patch.object(db, "show_log") as log:
            lab.expect_statement_error(
                "ALTER TABLE t DROP PARTITION p1",
                contains="temporary table",
                title="Rejected as expected",
            )
        self.assertEqual([call.args[1] for call in card.call_args_list], ["ok"])
        failure_card.assert_not_called()
        log.assert_not_called()


if __name__ == "__main__":
    unittest.main()
