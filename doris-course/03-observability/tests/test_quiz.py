"""Offline checks for the observability course quizzes."""

from html import escape
import os
from pathlib import Path
import unittest

import nbformat

from doris_course.quiz import CourseQuiz


ROOT = Path(__file__).resolve().parents[1]


class QuizTests(unittest.TestCase):
    def test_all_modules_have_six_unique_questions(self):
        paths = sorted(ROOT.glob("level[12]/*/quiz*.yaml"))
        self.assertEqual(len(paths), 8)

        for path in paths:
            with self.subTest(quiz=path.name):
                quiz = CourseQuiz.from_yaml(path)
                self.assertEqual(len(quiz.questions), 6)
                self.assertEqual(
                    len({question.question_id for question in quiz.questions}),
                    6,
                )
                for question in quiz.questions:
                    self.assertTrue(question.objective)
                    self.assertTrue(question.prompt)
                    self.assertTrue(question.explanation)
                    self.assertGreaterEqual(len(question.options), 4)
                    self.assertIn(
                        question.answer,
                        {option.option_id for option in question.options},
                    )

    def test_correct_answer_positions_are_distributed(self):
        for path in sorted(ROOT.glob("level[12]/*/quiz*.yaml")):
            with self.subTest(quiz=path.name):
                quiz = CourseQuiz.from_yaml(path)
                positions = [
                    next(
                        index
                        for index, option in enumerate(question.options)
                        if option.option_id == question.answer
                    )
                    for question in quiz.questions
                ]
                self.assertGreaterEqual(len(set(positions)), 3)
                self.assertLessEqual(positions.count(0), 2)

    def test_navigation_revision_and_score(self):
        for path in sorted(ROOT.glob("level[12]/*/quiz*.yaml")):
            with self.subTest(quiz=path.name):
                quiz = CourseQuiz.from_yaml(path)
                quiz._render_question()
                for index, question in enumerate(quiz.questions):
                    content = quiz._root.children[0]
                    self.assertIn(
                        f"{index + 1}. {escape(question.prompt)}",
                        content.children[0].value,
                    )
                    choices, feedback = content.children[1:3]
                    previous, submit, advance = content.children[3].children
                    submit.click()
                    self.assertIn("Select one", feedback.value)
                    choices.value = next(
                        option.option_id
                        for option in question.options
                        if option.option_id != question.answer
                    )
                    submit.click()
                    self.assertIn("Not quite", feedback.value)
                    choices.value = question.answer
                    self.assertNotIn(question.question_id, quiz._answers)
                    self.assertFalse(submit.disabled)
                    submit.click()
                    if index:
                        previous.click()
                        self.assertEqual(quiz._current, index - 1)
                        quiz._root.children[0].children[3].children[2].click()
                    advance.click()
                self.assertIn("100%", quiz._root.children[0].children[0].value)
                self.assertIn(
                    "doris-quiz-result-description",
                    quiz._root.children[0].children[0].value,
                )
                self.assertIn(
                    "doris-quiz-review",
                    quiz._root.children[0].children[0].value,
                )
                quiz._root.children[0].children[1].children[0].click()
                self.assertEqual(quiz._current, len(quiz.questions) - 1)
                quiz._root.children[0].children[3].children[2].click()
                quiz._root.children[0].children[1].children[1].click()
                self.assertEqual(quiz._answers, {})

    def test_incorrect_review_answers_use_boxed_content(self):
        quiz = CourseQuiz.from_yaml(next(ROOT.glob("level1/*/quiz*.yaml")))
        quiz._answers = {
            question.question_id: next(
                option.option_id
                for option in question.options
                if option.option_id != question.answer
            )
            for question in quiz.questions
        }
        quiz._render_results()
        result_html = quiz._root.children[0].children[0].value

        self.assertEqual(
            result_html.count('class="doris-quiz-review-answer-label"'),
            len(quiz.questions) * 2,
        )
        self.assertEqual(
            result_html.count('class="doris-quiz-review-answer"'),
            len(quiz.questions) * 2,
        )
        self.assertEqual(
            result_html.count('class="doris-quiz-review-description-label"'),
            len(quiz.questions),
        )
        self.assertEqual(
            result_html.count('class="doris-quiz-review-description"'),
            len(quiz.questions),
        )
        self.assertIn('class="doris-quiz-review-title"', result_html)
        self.assertIn(
            f"1. {escape(quiz.questions[0].prompt)}",
            result_html,
        )
        self.assertIn("Your answer:", result_html)
        self.assertIn("Correct answer:", result_html)
        self.assertIn("Description:", result_html)

    def test_notebooks_load_from_root_and_module_directory(self):
        original = Path.cwd()
        try:
            paths = sorted(ROOT.glob("level[12]/*/quiz*.ipynb"))
            self.assertEqual(len(paths), 8)
            for path in paths:
                with self.subTest(notebook=path.name):
                    notebook = nbformat.read(path, 4)
                    nbformat.validate(notebook)
                    initialization = next(
                        cell.source
                        for cell in notebook.cells
                        if "from pathlib import Path" in cell.source
                    )
                    self.assertTrue(
                        any("quiz.show()" in cell.source for cell in notebook.cells)
                    )
                    for directory in (ROOT, path.parent):
                        os.chdir(directory)
                        namespace = {}
                        exec(initialization, namespace)
                        quiz = namespace["quiz"]
                        self.assertEqual(len(quiz.questions), 6)
        finally:
            os.chdir(original)

    def test_shared_quiz_typography_and_all_notebook_headers(self):
        quiz_source = (ROOT / "doris_course" / "quiz.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(".doris-quiz-kicker", quiz_source)
        self.assertIn(".doris-quiz-objective", quiz_source)
        self.assertIn(".doris-quiz-question", quiz_source)
        self.assertIn(".doris-quiz-feedback", quiz_source)
        self.assertIn(".doris-quiz-result-description", quiz_source)
        self.assertIn(".doris-quiz-review", quiz_source)
        self.assertIn(".doris-quiz-review-answer-label", quiz_source)
        self.assertIn(".doris-quiz-review-answer", quiz_source)
        self.assertIn(".doris-quiz-review-description-label", quiz_source)
        self.assertIn(".doris-quiz-review-description", quiz_source)
        self.assertIn(".doris-quiz-review-title", quiz_source)
        self.assertIn("color: #000000", quiz_source)
        self.assertIn("color: #115e59", quiz_source)
        self.assertIn("font-size: 14px", quiz_source)
        self.assertIn("font-size: 16px", quiz_source)
        self.assertIn("font-size: 19px", quiz_source)

        paths = sorted(ROOT.glob("level[12]/*/quiz*.ipynb"))
        for path in paths:
            with self.subTest(notebook=path.name):
                notebook = nbformat.read(path, 4)
                header = notebook.cells[0].source
                self.assertIn("color:#0f766e;font-size:30px", header)
                self.assertNotIn("#17212b", header)
                self.assertNotIn(".doris-quiz-root .doris-quiz-kicker", header)


if __name__ == "__main__":
    unittest.main()
