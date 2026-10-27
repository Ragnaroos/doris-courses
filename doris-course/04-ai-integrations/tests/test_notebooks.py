"""Offline checks of the notebooks' structure and of the lab methods they call."""

import json
import re
import unittest
from pathlib import Path

from doris_course.ai_functions import AiFunctionsLab
from doris_course.lab import AiIntegrationsLab

ROOT = Path(__file__).resolve().parents[1]


def cells(path):
    return json.loads(path.read_text())["cells"]


def source(cell):
    return "".join(cell["source"])


class LabNotebookChecks:
    """The structure that every Lab of the course has; each subclass names one Lab."""

    lab_path: Path
    module_line: str
    init_import: str
    lab_class: type
    solution_text: str

    def setUp(self):
        self.cells = cells(self.lab_path)

    def test_header_links_the_lesson(self):
        header = source(self.cells[0])
        self.assertTrue(header.startswith("# "))
        self.assertIn(self.module_line + " · [Lesson](course.md)", header)

    def test_first_code_cell_initializes_the_lab(self):
        first_code = next(cell for cell in self.cells if cell["cell_type"] == "code")
        self.assertEqual(first_code["id"], "init")
        self.assertIn(self.init_import, source(first_code))

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
        self.assertIn("reference-solution", solution["metadata"]["tags"])
        self.assertIn(self.solution_text, source(solution))

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
                self.assertTrue(hasattr(self.lab_class, name), f"lab.{name} does not exist")


class Lab1NotebookTests(LabNotebookChecks, unittest.TestCase):
    lab_path = ROOT / "level1/module01-doris-mcp/lab01_connect_agent_to_doris.ipynb"
    module_line = "**Module 1: Connect AI Agents to Apache Doris with MCP**"
    init_import = "from doris_course import DorisLab"
    lab_class = AiIntegrationsLab
    solution_text = "lab.update_env_file(DORIS_PASSWORD=correct)"


class Lab2NotebookTests(LabNotebookChecks, unittest.TestCase):
    lab_path = ROOT / "level1/module02-doris-ai-functions/lab02_doris_ai_functions.ipynb"
    module_line = "**Module 2: Call Language Models from SQL with AI Functions**"
    init_import = "from doris_course import AiFunctionsLab"
    lab_class = AiFunctionsLab
    solution_text = "REGEXP_EXTRACT(topic_raw"

    def code(self, cell_id):
        return next(source(cell) for cell in self.cells if cell["id"] == cell_id)

    def test_optional_functions_are_off_by_default(self):
        self.assertIn("TRY_THE_OTHER_FUNCTIONS = False", self.code("gallery"))

    def test_one_row_per_request_is_set_before_the_tickets_are_labeled(self):
        ids = [cell["id"] for cell in self.cells]
        self.assertIn("lab.set_session(ai_context_window_size=1)", self.code("batch-one"))
        self.assertLess(ids.index("batch-one"), ids.index("enrich"))

    def test_enrichment_runs_per_ticket_and_skips_stored_tickets(self):
        enrich = self.code("enrich")
        self.assertIn("LEFT ANTI JOIN ai_course.ticket_enrichment", enrich)
        self.assertIn("WHERE t.ticket_id = {ticket_id}", enrich)
        self.assertIn("each=pending", enrich)
        self.assertEqual(self.code("enrich-again").strip(), "\n".join(enrich.strip().splitlines()[-3:]))

    def test_every_call_names_the_course_resource(self):
        for cell in self.cells:
            if cell["cell_type"] != "code":
                continue
            for call in re.findall(r"\bAI_[A-Z]+\((.*?)[,)]", source(cell)):
                with self.subTest(cell=cell["id"], call=call):
                    self.assertEqual(call, "'ai_course_llm'")


if __name__ == "__main__":
    unittest.main()
