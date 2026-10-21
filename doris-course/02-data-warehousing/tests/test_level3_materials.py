"""Offline checks for the Data Warehousing Level 3 learner materials."""

import ast
import re
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit

import nbformat
import yaml

ROOT = Path(__file__).resolve().parents[1]
LEVEL3 = ROOT / "level3"


class Level3MaterialsTest(unittest.TestCase):
    modules = {
        "module12-publishing-permissions-audit": "publishing_permissions_audit",
        "module13-storage-lifecycle": "storage_and_lifecycle",
        "module14-resource-isolation": "resource_isolation",
    }

    def test_each_module_has_guide_lab_and_quiz(self):
        for module, slug in self.modules.items():
            path = LEVEL3 / module
            self.assertTrue((path / "course.md").is_file(), module)
            number = int(module[6:8])
            self.assertTrue((path / f"lab{number}_{slug}.ipynb").is_file(), module)
            quiz = next(path.glob("quiz*.yaml"))
            self.assertTrue((path / quiz.name.replace(".yaml", ".ipynb")).is_file(), module)
            payload = yaml.safe_load(quiz.read_text())
            self.assertEqual(len(payload["questions"]), 6, quiz)
            self.assertEqual([len(q["options"]) for q in payload["questions"]], [4] * 6)
            # test_lessons.py checks the objectives, and test_course.py the options and explanations.
            self.assertEqual(len({q["objective"] for q in payload["questions"]}), 6, quiz)

    def test_new_notebooks_are_source_only_and_valid(self):
        notebooks = sorted(LEVEL3.glob("module*/*.ipynb"))
        self.assertEqual(len(notebooks), 6)
        for path in notebooks:
            notebook = nbformat.read(path, as_version=4)
            nbformat.validate(notebook)
            ids = [cell["id"] for cell in notebook.cells]
            self.assertEqual(len(ids), len(set(ids)), path)
            for cell in notebook.cells:
                if cell.cell_type == "code":
                    ast.parse(cell.source, filename=str(path))
                    self.assertFalse(cell.get("outputs"), path)
                    self.assertIsNone(cell.get("execution_count"), path)

    def test_labs_use_the_scoped_sandbox_connection(self):
        for path in sorted(LEVEL3.glob("module*/lab*.ipynb")):
            notebook = nbformat.read(path, as_version=4)
            source = "\n".join(cell.source for cell in notebook.cells if cell.cell_type == "code")
            self.assertIn("from dw_course.docker_runtime import connect_sandbox", source, path)
            self.assertRegex(source, r"lab = connect_sandbox\((module=\d+)?\)", path)

    def test_operational_labs_keep_scope_explicit(self):
        for path in sorted(LEVEL3.glob("module*/*.ipynb")):
            notebook = nbformat.read(path, as_version=4)
            source = "\n".join(cell.source for cell in notebook.cells if cell.cell_type == "code")
            self.assertIn("l3", source, path)
            self.assertNotIn("DROP TABLE orders_imported", source, path)
            self.assertNotIn("TRUNCATE TABLE orders_imported", source, path)

    def test_resource_lab_keeps_cluster_objects_scoped(self):
        # Workload Groups, roles and SQL block rules are cluster-wide: Lab 14 must not touch
        # accounts or the normal group, and its global rule may only live inside one cell.
        path = LEVEL3 / "module14-resource-isolation/lab14_resource_isolation.ipynb"
        notebook = nbformat.read(path, as_version=4)
        code = [cell.source for cell in notebook.cells if cell.cell_type == "code"]
        for forbidden in ("CREATE USER", "WORKLOAD GROUP normal", "SET GLOBAL", "SET PROPERTY '", "SET PROPERTY FOR 'root'"):
            self.assertNotIn(forbidden, "\n".join(code))
        # The one account property that the Lab sets is the temporary user's default group,
        # and it is set back to normal in a finally block, so that the groups can be dropped.
        properties = [source for source in code if "SET PROPERTY" in source]
        self.assertEqual(len(properties), 1)
        self.assertIn("with temporary_user(", properties[0])
        resets = ["\n".join(ast.unparse(statement) for statement in node.finalbody)
                  for node in ast.walk(ast.parse(properties[0])) if isinstance(node, ast.Try)]
        self.assertTrue(any("'default_workload_group' = 'normal'" in reset for reset in resets))

        rule_cells = [source for source in code if "CREATE SQL_BLOCK_RULE" in source]
        self.assertEqual(len(rule_cells), 1)
        cleanups = [
            "\n".join(ast.unparse(statement) for statement in node.finalbody)
            for node in ast.walk(ast.parse(rule_cells[0]))
            if isinstance(node, ast.Try)
        ]
        self.assertTrue(any("DROP SQL_BLOCK_RULE IF EXISTS course_scan_guard_l3" in c for c in cleanups))

        # A leftover global rule would block the setup's full scan, and dropping the role
        # removes stale grants before the groups are recreated.
        setup = next(source for source in code if "DROP TABLE IF EXISTS orders_monthly_l3" in source)
        order = [
            "DROP SQL_BLOCK_RULE IF EXISTS course_scan_guard_l3",
            "DROP ROLE IF EXISTS course_dashboard_reader_l3",
            "DROP WORKLOAD GROUP IF EXISTS course_dashboard_l3",
            "DROP TABLE IF EXISTS orders_monthly_l3",
        ]
        self.assertEqual([setup.index(statement) for statement in order],
                         sorted(setup.index(statement) for statement in order))
        self.assertLess(code.index(setup), code.index(rule_cells[0]))

    def test_level3_local_links_resolve(self):
        for path in sorted(LEVEL3.rglob("*")):
            if path.suffix not in {".md", ".ipynb"} or ".ipynb_checkpoints" in path.parts:
                continue
            for target in re.findall(r"\]\(([^\s)]+)\)", path.read_text()):
                url = urlsplit(target)
                if url.scheme or url.netloc or not url.path:
                    continue
                with self.subTest(source=str(path.relative_to(LEVEL3)), target=target):
                    self.assertTrue((path.parent / unquote(url.path)).exists())


if __name__ == "__main__":
    unittest.main()
