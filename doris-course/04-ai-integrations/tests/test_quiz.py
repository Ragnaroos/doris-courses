"""Offline checks of the module quizzes: they load, and they test their lessons' objectives."""

import json
import re
import unittest
from pathlib import Path

import yaml

from doris_course.quiz import CourseQuiz

ROOT = Path(__file__).resolve().parents[1]


def lesson_objectives(lesson):
    section = lesson.read_text().split("## Learning objectives", 1)[1].split("\n## ", 1)[0]
    items = re.findall(r"^\d+\. (.*?)(?=^\d+\. |\Z)", section, re.M | re.S)
    return [" ".join(item.split()) for item in items]


class QuizChecks:
    """The checks of one module's quiz; each subclass names the module."""

    number: int
    module: str
    quiz_name: str

    def setUp(self):
        directory = ROOT / "level1" / self.module
        self.quiz = directory / f"{self.quiz_name}.yaml"
        self.notebook = directory / f"{self.quiz_name}.ipynb"
        self.lesson = directory / "course.md"

    def test_quiz_loads_with_six_questions(self):
        quiz = CourseQuiz.from_yaml(self.quiz)
        self.assertEqual(len(quiz.questions), 6)

    def test_each_question_tests_one_lesson_objective(self):
        objectives = [" ".join(question["objective"].split())
                      for question in yaml.safe_load(self.quiz.read_text())["questions"]]
        self.assertEqual(objectives, lesson_objectives(self.lesson))

    def test_title_names_the_module(self):
        title = yaml.safe_load(self.quiz.read_text())["title"]
        heading = self.lesson.read_text().splitlines()[0]
        self.assertEqual(title, f"Module {self.number} Quiz: " + heading.removeprefix(f"# Module {self.number}: "))

    def test_notebook_loads_this_quiz(self):
        cells = json.loads(self.notebook.read_text())["cells"]
        code = [("".join(cell["source"])) for cell in cells if cell["cell_type"] == "code"]
        self.assertIn(f'"level1/{self.module}/{self.quiz_name}.yaml"', code[0])
        self.assertEqual(code[-1].strip(), "quiz.show();")
        self.assertTrue("".join(cells[-1]["source"]).startswith("## Next"))


class Quiz1Tests(QuizChecks, unittest.TestCase):
    number, module, quiz_name = 1, "module01-doris-mcp", "quiz01_doris_mcp"


class Quiz2Tests(QuizChecks, unittest.TestCase):
    number, module, quiz_name = 2, "module02-doris-ai-functions", "quiz02_doris_ai_functions"


if __name__ == "__main__":
    unittest.main()
