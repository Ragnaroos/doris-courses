"""Offline checks for the knowledge-check widget."""

import tempfile
import unittest
from html import escape
from pathlib import Path

from doris_labkit import quiz as quiz_module
from doris_labkit.quiz import CourseQuiz

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


def load(text=QUIZ_YAML):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "quiz01_example.yaml"
        path.write_text(text, encoding="utf-8")
        return CourseQuiz.from_yaml(path)


class QuizTests(unittest.TestCase):
    def test_navigation_revision_and_score(self):
        quiz = load()
        quiz._render_question()
        for index, question in enumerate(quiz.questions):
            content = quiz._root.children[0]
            self.assertIn(f"{index + 1}. {escape(question.prompt)}", content.children[0].value)
            choices, feedback = content.children[1:3]
            previous, submit, advance = content.children[3].children
            submit.click()
            self.assertIn("Select one", feedback.value)
            choices.value = next(o.option_id for o in question.options if o.option_id != question.answer)
            submit.click()
            self.assertIn("Not quite", feedback.value)
            choices.value = question.answer
            self.assertNotIn(question.question_id, quiz._answers)
            submit.click()
            if index:
                previous.click()
                self.assertEqual(quiz._current, index - 1)
                quiz._root.children[0].children[3].children[2].click()
            quiz._root.children[0].children[3].children[2].click()
        self.assertIn("100%", quiz._root.children[0].children[0].value)
        quiz._root.children[0].children[1].children[1].click()
        self.assertEqual(quiz._answers, {})

    def test_missed_questions_are_reviewed_in_labelled_boxes(self):
        quiz = load()
        quiz._answers = {
            question.question_id: next(o.option_id for o in question.options if o.option_id != question.answer)
            for question in quiz.questions
        }
        quiz._render_results()
        result_html = quiz._root.children[0].children[0].value
        self.assertEqual(result_html.count('class="doris-quiz-review-answer"'), 2 * len(quiz.questions))
        self.assertEqual(result_html.count('class="doris-quiz-review-description"'), len(quiz.questions))
        self.assertIn('class="doris-quiz-review-title"', result_html)
        self.assertIn(f"1. {escape(quiz.questions[0].prompt)}", result_html)
        for label in ("Your answer:", "Correct answer:", "Description:"):
            self.assertIn(label, result_html)

    def test_answer_must_match_an_option(self):
        with self.assertRaisesRegex(ValueError, "answer does not match an option"):
            load(QUIZ_YAML.replace("answer: fe", "answer: dba"))

    def test_styles_cover_every_quiz_element(self):
        source = Path(quiz_module.__file__).read_text(encoding="utf-8")
        for selector in (".doris-quiz-kicker", ".doris-quiz-objective", ".doris-quiz-question",
                         ".doris-quiz-feedback", ".doris-quiz-result-description", ".doris-quiz-review",
                         ".doris-quiz-review-answer-label", ".doris-quiz-review-answer",
                         ".doris-quiz-review-description-label", ".doris-quiz-review-description",
                         ".doris-quiz-review-title"):
            self.assertIn(selector, source)


if __name__ == "__main__":
    unittest.main()
