"""Offline checks for the Data Warehousing Level 2 learner materials."""

import ast
import unittest
from pathlib import Path

import nbformat
import yaml

ROOT = Path(__file__).resolve().parents[1]
LEVEL2 = ROOT / "level2"


class Level2MaterialsTest(unittest.TestCase):
    modules = {
        "module08-views-materialized-views": "views_and_materialized_views",
        "module09-modeling-and-joins": "modeling_and_joins",
        "module10-metric-processing": "metric_processing",
        "module11-bi-and-ai": "bi_and_ai",
    }

    def test_each_module_has_guide_lab_and_quiz(self):
        for module, slug in self.modules.items():
            path = LEVEL2 / module
            self.assertTrue((path / "course.md").is_file(), module)
            number = module[6:8]
            self.assertTrue((path / f"lab{number}_{slug if number != '11' else 'bi_and_ai_delivery'}.ipynb").is_file(), module)
            quiz = next(path.glob("quiz*.yaml"))
            self.assertTrue((path / quiz.name.replace(".yaml", ".ipynb")).is_file(), module)
            payload = yaml.safe_load(quiz.read_text())
            self.assertEqual(len(payload["questions"]), 6, quiz)
            self.assertEqual([len(q["options"]) for q in payload["questions"]], [4] * 6)
            # test_lessons.py checks the objectives, and test_course.py the options and explanations.
            self.assertEqual(len({q["objective"] for q in payload["questions"]}), 6, quiz)

    def test_new_notebooks_are_source_only_and_valid(self):
        notebooks = sorted(LEVEL2.glob("module*/*.ipynb"))
        self.assertEqual(len(notebooks), 8)
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

    def test_level2_labs_do_not_mutate_level1_tables(self):
        for path in sorted(LEVEL2.glob("module*/*.ipynb")):
            notebook = nbformat.read(path, as_version=4)
            source = "\n".join(cell.source for cell in notebook.cells if cell.cell_type == "code")
            for forbidden in ("DROP TABLE orders_imported", "TRUNCATE TABLE orders_imported", "DROP TABLE customers",
                              "DROP TABLE IF EXISTS orders_current", "DROP TABLE IF EXISTS order_events",
                              "TRUNCATE TABLE orders_current", "TRUNCATE TABLE order_events"):
                self.assertNotIn(forbidden, source, path)

    def test_level2_labs_use_the_scoped_sandbox_connection(self):
        for path in sorted(LEVEL2.glob("module*/lab*.ipynb")):
            notebook = nbformat.read(path, as_version=4)
            source = "\n".join(cell.source for cell in notebook.cells if cell.cell_type == "code")
            self.assertIn("from dw_course.docker_runtime import connect_sandbox", source, path)
            self.assertRegex(source, r"lab = connect_sandbox\((module=\d+)?\)", path)
            self.assertNotIn("lab = WarehouseLab()", source, path)


if __name__ == "__main__":
    unittest.main()
