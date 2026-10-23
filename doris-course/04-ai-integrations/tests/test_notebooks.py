"""Offline checks of the notebooks' structure and of the lab methods they call."""

import json
import re
import unittest
from pathlib import Path

from doris_course.lab import AiIntegrationsLab

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "level1/module01-doris-mcp"
LAB = MODULE / "lab01_connect_agent_to_doris.ipynb"


def cells(path):
    return json.loads(path.read_text())["cells"]


def source(cell):
    return "".join(cell["source"])


class LabNotebookTests(unittest.TestCase):
    def setUp(self):
        self.cells = cells(LAB)

    def test_header_links_the_lesson(self):
        header = source(self.cells[0])
        self.assertTrue(header.startswith("# "))
        self.assertIn("**Module 1: Connect AI Agents to Apache Doris with MCP** · [Lesson](course.md)", header)

    def test_first_code_cell_initializes_the_lab(self):
        first_code = next(cell for cell in self.cells if cell["cell_type"] == "code")
        self.assertEqual(first_code["id"], "init")
        self.assertIn("from doris_course import DorisLab", source(first_code))

    def test_last_cell_is_next(self):
        self.assertTrue(source(self.cells[-1]).startswith("## Next"))

    def test_cell_ids_are_unique(self):
        ids = [cell["id"] for cell in self.cells]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_step_states_its_expected_result(self):
        # Cells that are not steps: setup, the learner's exercise cell, and the stop cell
        # whose result is described together with the start cell after it.
        no_result = {"init", "exercise", "exercise-solution", "stop"}
        for index, cell in enumerate(self.cells):
            if cell["cell_type"] != "code" or cell["id"] in no_result:
                continue
            following = next((other for other in self.cells[index + 1:] if other["cell_type"] == "markdown"), None)
            with self.subTest(cell=cell["id"]):
                self.assertIsNotNone(following)
                self.assertTrue(source(following).startswith("**Expected result**"), source(following)[:60])

    def test_exercise_has_an_empty_cell_and_a_hidden_executable_solution(self):
        by_id = {cell["id"]: cell for cell in self.cells}
        self.assertEqual(source(by_id["exercise"]).strip(), "# Your code here")
        solution = by_id["exercise-solution"]
        self.assertEqual(solution["cell_type"], "code")
        self.assertTrue(solution["metadata"]["jupyter"]["source_hidden"])
        self.assertIn("lab.update_env_file(DORIS_PASSWORD=correct)", source(solution))

    def test_teardown_needs_an_explicit_choice(self):
        teardown = next(cell for cell in self.cells if cell["id"] == "teardown")
        self.assertIn("REMOVE_EVERYTHING = False", source(teardown))

    def test_lab_methods_exist(self):
        called = set()
        for cell in self.cells:
            if cell["cell_type"] == "code":
                called.update(re.findall(r"\blab\.(\w+)", source(cell)))
            else:
                called.update(re.findall(r"`lab\.(\w+)\(", source(cell)))
        self.assertTrue(called)
        for name in sorted(called):
            with self.subTest(method=name):
                self.assertTrue(hasattr(AiIntegrationsLab, name), f"lab.{name} does not exist")


if __name__ == "__main__":
    unittest.main()
