"""Run tools/check_links.py on small Markdown and notebook trees and check its verdicts."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "check_links.py"


def check(files):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for name, text in files.items():
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text(text, encoding="utf-8")
        return subprocess.run([sys.executable, str(TOOL), str(root)], capture_output=True, text=True)


def notebook(markdown):
    return json.dumps({"cells": [{"cell_type": "markdown", "metadata": {}, "source": [markdown]}],
                       "metadata": {}, "nbformat": 4, "nbformat_minor": 5})


class LinkCheckTests(unittest.TestCase):
    def test_existing_targets_pass(self):
        result = check({
            "course.md": "[Lab](lab01.ipynb) · [Section](#goal) · [Docs](https://doris.apache.org/)\n"
                         "`[not a link](missing.md)`\n",
            "lab01.ipynb": notebook('<img src="images/step.png"> [Lesson](course.md#goal)'),
            "images/step.png": "",
        })
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_missing_targets_fail(self):
        for name, text in (("course.md", "[Quiz](quiz01.ipynb)\n"),
                           ("lab01.ipynb", notebook('<img src="images/gone.png">'))):
            with self.subTest(file=name):
                result = check({name: text})
                self.assertEqual(result.returncode, 1)
                self.assertIn("BROKEN", result.stdout)


if __name__ == "__main__":
    unittest.main()
