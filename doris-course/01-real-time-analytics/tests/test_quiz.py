"""Run with: python -m unittest discover -s tests -p 'test_quiz.py'."""
import json
import os
from pathlib import Path
import unittest

import nbformat
from doris_course.quiz import CourseQuiz

ROOT = Path(__file__).resolve().parents[1]


class QuizTests(unittest.TestCase):
    def test_navigation_revision_and_score(self):
        for path in sorted(ROOT.glob('level[123]/*/quiz*.yaml')):
            with self.subTest(quiz=path.name):
                quiz = CourseQuiz.from_yaml(path)
                quiz._render_question()
                for index, question in enumerate(quiz.questions):
                    content = quiz._root.children[0]
                    choices, feedback = content.children[1:3]
                    previous, submit, advance = content.children[3].children
                    submit.click()
                    self.assertIn('Select one', feedback.value)
                    choices.value = next(o.option_id for o in question.options if o.option_id != question.answer)
                    submit.click()
                    self.assertIn('Not quite', feedback.value)
                    choices.value = question.answer
                    self.assertNotIn(question.question_id, quiz._answers)
                    self.assertFalse(submit.disabled)
                    submit.click()
                    if index:
                        previous.click()
                        self.assertEqual(quiz._current, index - 1)
                        quiz._root.children[0].children[3].children[2].click()
                    quiz._root.children[0].children[3].children[2].click()
                self.assertIn('100%', quiz._root.children[0].children[0].value)
                quiz._root.children[0].children[1].children[0].click()
                self.assertEqual(quiz._current, len(quiz.questions) - 1)
                quiz._root.children[0].children[3].children[2].click()
                quiz._root.children[0].children[1].children[1].click()
                self.assertEqual(quiz._answers, {})

    def test_draft_survives_back_navigation(self):
        quiz = CourseQuiz.from_yaml(next(ROOT.glob('level2/*/quiz*.yaml')))
        quiz._render_question()
        content = quiz._root.children[0]
        content.children[1].value = quiz.questions[0].answer
        content.children[3].children[1].click()
        content.children[3].children[2].click()
        content = quiz._root.children[0]
        choice = quiz.questions[1].options[0].option_id
        content.children[1].value = choice
        content.children[3].children[0].click()
        quiz._root.children[0].children[3].children[2].click()
        self.assertEqual(quiz._root.children[0].children[1].value, choice)
        self.assertNotIn(quiz.questions[1].question_id, quiz._answers)

    def test_notebooks_and_both_working_directories(self):
        original = Path.cwd()
        try:
            for path in ROOT.glob('level[123]/*/quiz*.ipynb'):
                nb = nbformat.read(path, 4)
                nbformat.validate(nb)
                initialization = next(c.source for c in nb.cells if 'from pathlib import Path' in c.source)
                self.assertTrue(any('quiz.show()' in c.source for c in nb.cells))
                for directory in (ROOT, path.parent):
                    os.chdir(directory)
                    namespace = {}
                    exec(initialization, namespace)
                    quiz = namespace['quiz']
                    if 'level3' in path.parts:
                        self.assertEqual(len(quiz.questions), 6)
                    else:
                        self.assertIn(len(quiz.questions), (5, 6))
                    self.assertEqual(
                        len({q.question_id for q in quiz.questions}),
                        len(quiz.questions),
                    )
        finally:
            os.chdir(original)

    def test_question_and_option_ids_are_unique_and_explanations_exist(self):
        for path in sorted(ROOT.glob('level[123]/*/quiz*.yaml')):
            with self.subTest(quiz=path.name):
                quiz = CourseQuiz.from_yaml(path)
                question_ids = [question.question_id for question in quiz.questions]
                self.assertEqual(len(question_ids), len(set(question_ids)))
                for question in quiz.questions:
                    option_ids = [option.option_id for option in question.options]
                    self.assertEqual(len(option_ids), len(set(option_ids)))
                    self.assertIn(question.answer, option_ids)
                    self.assertTrue(question.explanation.strip())


if __name__ == '__main__':
    unittest.main()
