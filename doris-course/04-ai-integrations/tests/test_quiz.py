"""Offline checks of the module quiz: it loads, and it tests the lesson's objectives."""

import json
import re
import unittest
from pathlib import Path

import yaml

from doris_course.quiz import CourseQuiz

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "level1/module01-doris-mcp"
QUIZ = MODULE / "quiz01_doris_mcp.yaml"
NOTEBOOK = MODULE / "quiz01_doris_mcp.ipynb"
LESSON = MODULE / "course.md"


def lesson_objectives():
    section = LESSON.read_text().split("## Learning objectives", 1)[1].split("\n## ", 1)[0]
    items = re.findall(r"^\d+\. (.*?)(?=^\d+\. |\Z)", section, re.M | re.S)
    return [" ".join(item.split()) for item in items]


class QuizTests(unittest.TestCase):
    def test_quiz_loads_with_six_questions(self):
        quiz = CourseQuiz.from_yaml(QUIZ)
        self.assertEqual(len(quiz.questions), 6)

    def test_each_question_tests_one_lesson_objective(self):
        objectives = [" ".join(question["objective"].split())
                      for question in yaml.safe_load(QUIZ.read_text())["questions"]]
        self.assertEqual(objectives, lesson_objectives())

    def test_title_names_the_module(self):
        title = yaml.safe_load(QUIZ.read_text())["title"]
        heading = LESSON.read_text().splitlines()[0]
        self.assertEqual(title, "Module 1 Quiz: " + heading.removeprefix("# Module 1: "))

    def test_notebook_loads_this_quiz(self):
        cells = json.loads(NOTEBOOK.read_text())["cells"]
        code = [("".join(cell["source"])) for cell in cells if cell["cell_type"] == "code"]
        self.assertIn('"level1/module01-doris-mcp/quiz01_doris_mcp.yaml"', code[0])
        self.assertEqual(code[-1].strip(), "quiz.show();")
        self.assertTrue("".join(cells[-1]["source"]).startswith("## Next"))


if __name__ == "__main__":
    unittest.main()
