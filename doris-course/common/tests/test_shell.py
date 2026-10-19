"""Offline checks for learner-visible Bash with live progress."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from doris_labkit import shell


class RunShellTests(unittest.TestCase):
    def test_plain_script_runs_in_the_given_directory(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(shell, "card"), patch.object(shell, "show_log"):
            result = shell.run_shell('printf "cwd=%s" "$(pwd -P)"', title="Run a command", cwd=Path(directory))
        self.assertEqual(result.returncode, 0)
        self.assertIn(f"cwd={Path(directory).resolve()}", result.stdout)

    def test_failure_shows_the_log_and_raises(self):
        with patch.object(shell, "card") as card, patch.object(shell, "show_log") as log:
            with self.assertRaisesRegex(RuntimeError, "Broken step failed with exit status 4"):
                shell.run_shell('echo "about to fail"; exit 4', title="Broken step", cwd=Path.cwd())
        self.assertEqual(card.call_args.args[1:], ("fail", "Failed: Broken step"))
        self.assertIn("about to fail", log.call_args.args[1])

    def test_numbered_steps_drive_the_workflow_panel(self):
        script = 'echo "[1/2] Prepare"\necho "Pulling apache/doris"\necho "noise"\necho "[2/2] Finish"'
        handle = Mock()
        with patch.object(shell, "display", return_value=handle), \
             patch.object(shell, "card") as card, patch.object(shell, "show_log"):
            result = shell.run_shell(script, title="Two steps", cwd=Path.cwd())
        self.assertIn("[2/2] Finish", result.stdout)
        final_panel = handle.update.call_args.args[0].data
        self.assertIn("Completed", final_panel)
        self.assertEqual(final_panel.count("doris-workflow-item success"), 2)
        self.assertEqual(card.call_args.args[2], "Passed: Two steps")

    def test_failed_step_marks_the_current_step(self):
        script = 'echo "[1/2] Prepare"\necho "[2/2] Break"\nexit 1'
        handle = Mock()
        with patch.object(shell, "display", return_value=handle), \
             patch.object(shell, "card"), patch.object(shell, "show_log"):
            with self.assertRaises(RuntimeError):
                shell.run_shell(script, title="Two steps", cwd=Path.cwd())
        failed_panel = handle.update.call_args.args[0].data
        self.assertIn("Failed", failed_panel)
        self.assertIn("doris-workflow-item failure", failed_panel)


if __name__ == "__main__":
    unittest.main()
