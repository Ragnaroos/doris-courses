"""Offline checks for cards, styles, step panels, and Query Profiles."""

import io
import unittest
from unittest.mock import MagicMock, patch

from doris_labkit import profiles, ui


def rendered(display):
    return "".join(call.args[0].data for call in display.call_args_list)


class UiTests(unittest.TestCase):
    def test_card_kinds_map_to_status_styles(self):
        with patch.object(ui, "display") as display:
            ui.card("All rows loaded", "ok", "Load complete")
            ui.card("Rerun after 02:00", "info")
        html = rendered(display)
        self.assertIn('class="doris-status success"', html)
        self.assertIn('<div class="doris-status-title">Load complete</div>', html)
        self.assertIn('<span class="doris-chip">All rows loaded</span>', html)
        self.assertIn('class="doris-status running"', html)

    def test_course_styles_are_added_to_the_shared_styles(self):
        with patch.object(ui, "display") as display:
            ui.install_styles(".course-only {color:red}")
        html = rendered(display)
        self.assertIn(".doris-status {", html)
        self.assertIn(".course-only {color:red}", html)

    def test_workflow_panel_marks_finished_running_and_pending_steps(self):
        steps = {1: "Check Docker", 2: "Start Doris", 3: "Connect"}
        html = ui.workflow_html("Prepare", steps, 2, "running", "Pulling image").data
        self.assertIn("Step 2 of 3", html)
        self.assertEqual(html.count("doris-workflow-item success"), 1)
        self.assertEqual(html.count("doris-workflow-item running"), 1)
        self.assertEqual(html.count("doris-workflow-item pending"), 1)
        self.assertIn("Pulling image", html)

    def test_return_later_renders_as_one_line(self):
        error = ui.ReturnLater("rerun this cell at 02:00")
        self.assertEqual(error._render_traceback_(), ["Stopped on purpose: rerun this cell at 02:00"])
        self.assertIsInstance(error, RuntimeError)


class ProfileTests(unittest.TestCase):
    PROFILE = """
      MergedProfile:
        - ScanRows: sum 1.234K (1234)
        - ScanBytes: 2.00 MB
      DetailProfile:
        - RowsRead: 1.000K (1000)
        - RowsRead: 234
    """

    def test_statements_match_regardless_of_case_spacing_and_semicolon(self):
        self.assertEqual(
            profiles.normalize_statement("SELECT  *\nFROM events;"),
            profiles.normalize_statement("select * from events"),
        )

    def test_metric_and_row_sum(self):
        self.assertEqual(profiles.profile_metric(self.PROFILE, "ScanBytes"), "2.00 MB")
        self.assertEqual(profiles.profile_metric(self.PROFILE, "ScanRows"), "1.234K (1234)")
        self.assertEqual(profiles.profile_row_sum(self.PROFILE, "RowsRead"), 1234)
        self.assertEqual(profiles.profile_metric(self.PROFILE, "Missing"), "not shown")

    @staticmethod
    def connection_listing(*listings):
        """A connection whose SHOW QUERY PROFILE returns each listing in turn."""
        cursor = MagicMock()
        cursor.fetchall.side_effect = list(listings)
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        return connection, cursor

    def test_last_query_id_reads_the_session_function(self):
        connection, cursor = self.connection_listing()
        cursor.fetchone.return_value = {"query_id": "a1-b2"}
        self.assertEqual(profiles.last_query_id(connection), "a1-b2")
        cursor.execute.assert_called_once_with("SELECT last_query_id() AS query_id")

    def test_find_profile_returns_the_row_of_the_query(self):
        connection, cursor = self.connection_listing([
            {"Profile ID": "id-3", "Sql Statement": "SELECT last_query_id() AS query_id"},
            {"Profile ID": "id-2", "Sql Statement": "SELECT severity_text FROM otel_logs"},
            {"Profile ID": "id-1", "Sql Statement": "SELECT severity_text FROM otel_logs"},
        ])
        # An earlier run of the same SQL has its own ID.
        self.assertEqual(profiles.find_profile(connection, "id-1")["Profile ID"], "id-1")
        cursor.execute.assert_called_once_with("SHOW QUERY PROFILE")

    def test_find_profile_waits_for_the_query_and_then_gives_up(self):
        connection, _ = self.connection_listing([], [{"Profile ID": "id-1", "Sql Statement": "SELECT 1"}])
        with patch.object(profiles.time, "sleep") as sleep:
            self.assertEqual(profiles.find_profile(connection, "id-1")["Profile ID"], "id-1")
        sleep.assert_called_once_with(0.5)

        # A query that ran without enable_profile = true never appears.
        connection, cursor = self.connection_listing([], [], [])
        with patch.object(profiles.time, "monotonic", side_effect=[0, 4, 8, 12]), \
             patch.object(profiles.time, "sleep"):
            self.assertIsNone(profiles.find_profile(connection, "id-1", timeout_seconds=10))
        self.assertEqual(cursor.execute.call_count, 3)

    def test_fetch_profile_text_until_it_is_ready(self):
        answers = [io.BytesIO(b"Summary:\n"), io.BytesIO(b"Summary:\nDetailProfile(a-b):\n  OLAP_SCAN_OPERATOR")]
        with patch.object(profiles.urllib.request, "urlopen", side_effect=answers) as urlopen, \
             patch.object(profiles.time, "sleep"):
            text = profiles.fetch_profile_text(
                "http://127.0.0.1:28030", "a-b", ready=lambda text: "OLAP_SCAN_OPERATOR" in text,
            )
        self.assertTrue(text.endswith("OLAP_SCAN_OPERATOR"))
        self.assertEqual(urlopen.call_count, 2)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:28030/api/profile/text?query_id=a-b")
        self.assertEqual(request.get_header("Authorization"), "Basic cm9vdDo=")  # root, no password

    def test_fetch_profile_text_returns_the_last_text_when_time_is_up(self):
        with patch.object(profiles.urllib.request, "urlopen", side_effect=lambda *_, **__: io.BytesIO(b"Summary:\n")), \
             patch.object(profiles.time, "monotonic", side_effect=[0, 15, 25]), \
             patch.object(profiles.time, "sleep"):
            text = profiles.fetch_profile_text("http://fe", "a-b", ready=lambda text: False, timeout_seconds=20)
        self.assertEqual(text, "Summary:\n")


if __name__ == "__main__":
    unittest.main()
