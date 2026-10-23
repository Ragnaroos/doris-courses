"""Run tools/check_notebook_outputs.py on small notebooks and check its verdicts."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "check_notebook_outputs.py"


def notebook(cell_changes=None, metadata=None):
    cell = {"cell_type": "code", "id": "lab-step", "metadata": {}, "execution_count": None,
            "outputs": [], "source": ["lab.sql('SELECT 1')"]}
    cell.update(cell_changes or {})
    return {"cells": [cell], "metadata": metadata or {"kernelspec": {"name": "python3"}},
            "nbformat": 4, "nbformat_minor": 5}


def run(document, *args):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "lab01_example.ipynb"
        path.write_text(json.dumps(document), encoding="utf-8")
        return subprocess.run([sys.executable, str(TOOL), *args, str(path)], capture_output=True, text=True)


STREAM = {"output_type": "stream", "name": "stdout", "text": ["1\n"]}


class NotebookOutputCheckTests(unittest.TestCase):
    def test_a_clean_notebook_passes_strict(self):
        self.assertEqual(run(notebook(), "--strict").returncode, 0)

    def test_run_state_fails_only_with_strict(self):
        cases = {
            "1 output(s)": notebook({"outputs": [STREAM]}),
            "1 execution count(s)": notebook({"execution_count": 3}),
            "1 run timestamp(s)": notebook({"metadata": {"ExecuteTime": {"start_time": "2026-09-30T02:00:00Z"}}}),
            "saved widget state": notebook(metadata={"widgets": {"state": {}}}),
        }
        for message, document in cases.items():
            with self.subTest(message=message):
                relaxed = run(document)
                self.assertEqual(relaxed.returncode, 0)
                self.assertIn(message, relaxed.stdout)
                self.assertEqual(run(document, "--strict").returncode, 1)

    def test_errors_and_local_paths_always_fail(self):
        error = {"output_type": "error", "ename": "OperationalError", "evalue": "", "traceback": []}
        local = dict(STREAM, text=["saved to /Users/someone/doris-courses/out.csv\n"])
        for message, output in (("ERROR", error), ("PATH", local)):
            with self.subTest(message=message):
                result = run(notebook({"outputs": [output]}))
                self.assertEqual(result.returncode, 1)
                self.assertIn(message, result.stdout)


if __name__ == "__main__":
    unittest.main()
