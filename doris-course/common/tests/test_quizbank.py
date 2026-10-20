"""Offline checks for quiz files: structure, and the fixed shuffled order."""

import tempfile
import unittest
from collections import Counter
from pathlib import Path

import yaml

from doris_labkit.quizbank import QuizFormatError, display_order, load_quiz, parse_quiz, structure_problems

QUIZ_YAML = """\
title: "Module 1 Quiz: Example"
description: Two questions about an example module.
questions:
  - id: pick_olap
    objective: Distinguish OLAP from OLTP
    prompt: Which request is analytical?
    options:
      - id: update_one
        text: Update one order
      - id: sum_by_day
        text: Sum revenue by day
      - id: reserve_stock
        text: Reserve one product unit
      - id: read_token
        text: Read one payment token
    answer: sum_by_day
    explanation: Summing many rows by day is analytical.
  - id: pick_fe
    objective: Name the FE's role
    prompt: Which node plans a query?
    options:
      - id: fe
        text: Frontend (FE)
      - id: be
        text: Backend (BE)
      - id: client
        text: The SQL client
    answer: fe
    explanation: FE parses and plans the query.
"""


def document(text=QUIZ_YAML):
    return yaml.safe_load(text)


def six_question_quiz(title="Module 2 Quiz: Positions"):
    """Six questions whose answers are all written first in the file."""
    questions = [
        {
            "id": f"question_{number}",
            "objective": f"Objective {number}",
            "prompt": f"Prompt {number}?",
            "options": [{"id": f"option_{number}_{index}", "text": f"Option {number}.{index}"} for index in range(4)],
            "answer": f"option_{number}_0",
            "explanation": f"Explanation {number}.",
        }
        for number in range(1, 7)
    ]
    return parse_quiz({"title": title, "description": "Six questions.", "questions": questions})


def positions(quiz):
    return [
        [option.option_id for option in question.options].index(question.answer)
        for question in quiz.questions
    ]


class StructureTests(unittest.TestCase):
    def assertProblem(self, text, fragment):
        problems = structure_problems(document(text))
        self.assertTrue(any(fragment in problem for problem in problems), problems)

    def test_a_valid_quiz_has_no_problems(self):
        self.assertEqual(structure_problems(document()), [])

    def test_each_rule_is_reported(self):
        cases = {
            "missing 'description'": QUIZ_YAML.replace("description: Two questions about an example module.\n", ""),
            "unknown key 'alignment'": QUIZ_YAML.replace(
                "    answer: fe\n", "    answer: fe\n    alignment:\n      course: '1.2'\n"),
            "Module N Quiz": QUIZ_YAML.replace('"Module 1 Quiz: Example"', '"Example quiz"'),
            "not a slug": QUIZ_YAML.replace("id: pick_fe", "id: Pick-FE"),
            "also used by Q1": QUIZ_YAML.replace("id: pick_fe", "id: pick_olap"),
            "single letter": QUIZ_YAML.replace("- id: client", "- id: c").replace("answer: fe", "answer: fe"),
            "letter prefix": QUIZ_YAML.replace("text: Backend (BE)", "text: B. Backend (BE)"),
            "repeats option 1": QUIZ_YAML.replace("text: Backend (BE)", "text: Frontend (FE)"),
            "is not one of the option ids": QUIZ_YAML.replace("answer: fe", "answer: dba"),
            "must be text": QUIZ_YAML.replace("- id: client", "- id: no"),
            "'prompt' must be non-empty text": QUIZ_YAML.replace("prompt: Which node plans a query?", "prompt: ''"),
            "at least two options": QUIZ_YAML.replace(
                "      - id: be\n        text: Backend (BE)\n      - id: client\n        text: The SQL client\n", ""),
        }
        for fragment, text in cases.items():
            with self.subTest(fragment=fragment):
                self.assertProblem(text, fragment)

    def test_explanations_must_not_name_options_by_letter(self):
        for explanation in ("B: Correct. FE plans the query.", "As option A says, FE plans the query.",
                            "Answer C is wrong; FE plans the query."):
            with self.subTest(explanation=explanation):
                self.assertProblem(
                    QUIZ_YAML.replace("explanation: FE parses and plans the query.", f'explanation: "{explanation}"'),
                    "refers to an option by letter",
                )
        # Letters that name things in the scenario are fine.
        text = QUIZ_YAML.replace("explanation: FE parses and plans the query.",
                                 "explanation: Store A totals 60, and table B keeps three replicas.")
        self.assertEqual(structure_problems(document(text)), [])

    def test_loading_lists_every_problem(self):
        text = QUIZ_YAML.replace("- id: client", "- id: c").replace("answer: fe", "answer: dba")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "quiz01_example.yaml"
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(QuizFormatError) as raised:
                load_quiz(path)
        message = str(raised.exception)
        self.assertIn("quiz01_example.yaml does not follow the quiz structure", message)
        self.assertIn("single letter", message)
        self.assertIn("is not one of the option ids", message)
        self.assertIsInstance(raised.exception, ValueError)


class DisplayOrderTests(unittest.TestCase):
    def test_order_is_fixed_and_keeps_options_and_answers(self):
        quiz = parse_quiz(document())
        shown = display_order(quiz)
        self.assertEqual(shown, display_order(parse_quiz(document())))
        for written, displayed in zip(quiz.questions, shown.questions):
            self.assertEqual(sorted(displayed.options, key=lambda o: o.option_id),
                             sorted(written.options, key=lambda o: o.option_id))
            self.assertEqual(displayed.answer, written.answer)
            self.assertEqual(displayed.option_text(displayed.answer), written.option_text(written.answer))
        self.assertEqual((shown.title, shown.description), (quiz.title, quiz.description))
        self.assertEqual([q.question_id for q in shown.questions], [q.question_id for q in quiz.questions])

    def test_order_does_not_follow_the_file(self):
        reversed_options = QUIZ_YAML.replace(
            "      - id: update_one\n        text: Update one order\n"
            "      - id: sum_by_day\n        text: Sum revenue by day\n",
            "      - id: sum_by_day\n        text: Sum revenue by day\n"
            "      - id: update_one\n        text: Update one order\n",
        )
        self.assertNotEqual(document(reversed_options), document())
        self.assertEqual(display_order(parse_quiz(document(reversed_options))),
                         display_order(parse_quiz(document())))

    def test_answers_are_spread_over_the_positions(self):
        for title in ("Module 2 Quiz: Positions", "Module 3 Quiz: Other positions", "Module 4 Quiz: More"):
            with self.subTest(title=title):
                counts = Counter(positions(display_order(six_question_quiz(title))))
                self.assertEqual(sorted(counts.values()), [1, 1, 2, 2])

    def test_the_order_depends_on_the_quiz(self):
        orders = {
            tuple(tuple(o.option_id for o in q.options) for q in display_order(six_question_quiz(title)).questions)
            for title in ("Module 2 Quiz: Positions", "Module 3 Quiz: Other positions", "Module 4 Quiz: More")
        }
        self.assertEqual(len(orders), 3)

    def test_order_is_pinned(self):
        # The order is part of the learner experience; change it only on purpose.
        shown = display_order(parse_quiz(document()))
        self.assertEqual(
            [[option.option_id for option in question.options] for question in shown.questions],
            [["update_one", "sum_by_day", "read_token", "reserve_stock"], ["fe", "be", "client"]],
        )


if __name__ == "__main__":
    unittest.main()
