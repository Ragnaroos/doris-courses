"""Offline checks for cards, styles, step panels, and Profile parsing."""

import unittest
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
