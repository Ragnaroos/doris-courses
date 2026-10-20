"""Checks for the course 02 maintenance documents.

The course tests live in doris-course/02-data-warehousing/tests and do not
read this directory. These tests cover only the maintenance documents and
are removed together with them. Run from the repository root:

    doris-course/02-data-warehousing/.venv/bin/python -m unittest discover -s maintenance/02-data-warehousing/tests -v
"""

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
MAINTENANCE_ROOT = REPO_ROOT / "maintenance/02-data-warehousing"


class MaintenanceDocsTest(unittest.TestCase):
    def test_local_markdown_links(self):
        for path in MAINTENANCE_ROOT.rglob("*.md"):
            for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
                if target.startswith(("https://", "http://", "#")):
                    continue
                self.assertTrue((path.parent / target.split("#")[0]).exists(), f"{path}: {target}")

    def test_backlog_distinguishes_optional_integrations(self):
        text = (MAINTENANCE_ROOT / "integration-backlog.md").read_text()
        self.assertNotRegex(text,r'\bD0[1-7]\b')
        for label in ('Module 5.6', 'Module 5.7', 'Module 5.8', 'Module 5.9', '不是当前结课门槛', 'Lab 5A / 5B 均选做'):
            self.assertIn(label,text)
        self.assertNotIn("仍需交付的持续集成实验", text)
        self.assertNotIn("不能因主线与扩展全部通过而宣布完整 Level 1 已结课验收", text)

    def test_jupyter_config_hides_generated_files_without_hiding_course(self):
        from traitlets.config import Config
        config = Config()
        path = REPO_ROOT / "maintenance/jupyter_lab_config.py"
        namespace = {"__file__": str(path), "get_config": lambda: config}
        exec(compile(path.read_text(), str(path), "exec"), namespace)
        self.assertEqual(config.ServerApp.root_dir, str(REPO_ROOT))
        self.assertIn("*.egg-info", config.ContentsManager.hide_globs)
        self.assertNotIn("dw_course", config.ContentsManager.hide_globs)
        self.assertNotIn("maintenance", config.ContentsManager.hide_globs)


if __name__ == "__main__":
    unittest.main()
