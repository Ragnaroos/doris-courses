"""Run tools/check_sensitive_info.py on a small Git work tree and check its findings."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "check_sensitive_info.py"
# Built at run time, so this file does not itself contain anything that looks like a secret.
FAKE_KEY = "AKIA" + "Z" * 16
FAKE_TOKEN = "gh" + "p_" + "x" * 36
HOME = "/Us" + "ers/someone/"


def scan(files, untracked=None):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for name, text in {**files, **(untracked or {})}.items():
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text(text, encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "add", *files], check=True)
        return subprocess.run([sys.executable, str(TOOL), str(root)], capture_output=True, text=True)


class SensitiveInfoTests(unittest.TestCase):
    def test_clean_files_pass(self):
        result = scan({"doris-course/README.md": "Sign in as learner@example.com or ops@course.test.\n"})
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_each_rule_reports_file_and_line(self):
        cases = {
            "AWS access key": f"key = '{FAKE_KEY}'\n",
            "GitHub token": f"token: {FAKE_TOKEN}\n",
            "local path": f"Open {HOME}doris-courses/lab.ipynb\n",
            "email address": "Contact jane.doe@gmail.com\n",
            "private key": "-----BEGIN RSA " + "PRIVATE KEY-----\n",
        }
        for rule, text in cases.items():
            with self.subTest(rule=rule):
                result = scan({"doris-course/notes.md": "first line\n" + text})
                self.assertEqual(result.returncode, 1)
                self.assertIn(f"doris-course/notes.md:2: {rule}", result.stdout)

    def test_tools_and_untracked_files_are_skipped(self):
        secret = f"key = '{FAKE_KEY}'\n"
        result = scan({"tools/rules.py": secret, "README.md": "ok\n"}, untracked={"scratch.md": secret})
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_maintainer_notes_are_scanned(self):
        result = scan({"maintenance/notes.md": f"key = '{FAKE_KEY}'\n"})
        self.assertEqual(result.returncode, 1)
        self.assertIn("maintenance/notes.md:1: AWS access key", result.stdout)


if __name__ == "__main__":
    unittest.main()
