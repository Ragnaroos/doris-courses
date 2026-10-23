"""Offline checks of the lessons (course.md) and of their links to the Labs and quizzes."""

import json
import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
LESSONS = sorted(ROOT.glob("level*/module*/course.md"))


def objectives(lesson):
    """The numbered items of the lesson's Learning objectives section."""
    section = lesson.split("## Learning objectives", 1)[1].split("\n## ", 1)[0]
    return re.findall(r"^\d+\. (.+)$", section, re.M)


class LessonTests(unittest.TestCase):
    def test_every_module_has_a_lesson(self):
        self.assertEqual([lesson.parent for lesson in LESSONS], sorted(ROOT.glob("level*/module*")))

    def test_a_lesson_names_its_module_as_its_lab_and_quiz_do(self):
        for path in LESSONS:
            lesson = path.read_text()
            title = re.match(r"# (Module (\d+): (.+))\n", lesson)
            with self.subTest(lesson=path.parent.name):
                self.assertIsNotNone(title)
                heading, number, name = title.groups()
                quiz_yaml = next(path.parent.glob("quiz*.yaml"))
                self.assertEqual(yaml.safe_load(quiz_yaml.read_text())["title"], f"Module {number} Quiz: {name}")
                lab = next(path.parent.glob("lab*.ipynb"))
                quiz = quiz_yaml.with_suffix(".ipynb")
                header = "".join(json.loads(lab.read_text())["cells"][0]["source"])
                self.assertIn(f"**{heading}** · [Lesson](course.md) · [Quiz]({quiz.name})", header)
                # The lesson leads to its Lab and its quiz.
                self.assertIn(f"]({lab.name})", lesson)
                self.assertIn(f"]({quiz.name})", lesson)

    def test_a_lesson_has_the_sections_of_the_course_template(self):
        for path in LESSONS:
            lesson = path.read_text()
            with self.subTest(lesson=path.parent.name):
                headings = re.findall(r"^## (.+)$", lesson, re.M)
                for required in ("Module goal", "Learning objectives", "Summary", "References"):
                    self.assertIn(required, headings)
                self.assertTrue(any(heading.startswith("Lab ") for heading in headings))
                self.assertTrue(any(heading.startswith("Quiz ") for heading in headings))
                self.assertLessEqual(3, len(objectives(lesson)))
                self.assertLessEqual(len(objectives(lesson)), 6)
                self.assertRegex(lesson, r"Estimated time \| About \d+ minutes: reading \d+, Lab \d+")
                # The quiz section ends with the way to the next module.
                quiz_section = lesson.split("\n## Quiz ", 1)[1].split("\n## ", 1)[0]
                self.assertRegex(quiz_section, r"Next(?: module)?: ")

    def test_each_quiz_question_tests_an_objective_of_its_lesson(self):
        for path in LESSONS:
            quiz = yaml.safe_load(next(path.parent.glob("quiz*.yaml")).read_text())
            used = [question["objective"] for question in quiz["questions"]]
            with self.subTest(lesson=path.parent.name):
                # The quiz uses the lesson's wording, and every objective has a question.
                self.assertEqual(set(used), set(objectives(path.read_text())))

    def test_a_lesson_links_each_image_with_a_description(self):
        for path in LESSONS:
            for alt, target in re.findall(r"!\[([^\]]*)\]\(([^)]+)\)", path.read_text()):
                with self.subTest(lesson=path.parent.name, image=target):
                    self.assertTrue((path.parent / target).is_file())
                    self.assertGreater(len(alt.split()), 10)


class ReadmeTests(unittest.TestCase):
    README = (ROOT / "README.md").read_text()

    def test_readme_has_the_sections_of_the_course_template(self):
        self.assertEqual(re.findall(r"^## (.+)$", self.README, re.M), [
            "Who this course is for", "What you will learn", "Course outline", "Environment", "Get started",
            "Dataset", "Clean up", "Troubleshooting",
        ])

    def test_readme_outline_leads_to_every_lesson_in_order(self):
        rows = re.findall(r"^\| (\d) \| \[(Module (\d+): [^\]]+)\]\(([^)]+)\) \|", self.README, re.M)
        self.assertEqual([row[3] for row in rows], [lesson.relative_to(ROOT).as_posix() for lesson in LESSONS])
        for level, name, number, path in rows:
            with self.subTest(module=number):
                # The outline uses the lesson's own name, and the module's level.
                self.assertTrue((ROOT / path).read_text().startswith(f"# {name}\n"))
                self.assertIn(f"level{level}/", path)

    def test_readme_lists_every_port_variable(self):
        variables = set(re.findall(r'env_port\("(DORIS_OBS_\w+)"', (ROOT / "doris_course/environment.py").read_text()))
        self.assertTrue(variables)
        for variable in sorted(variables):
            self.assertIn(f"`{variable}`", self.README)


if __name__ == "__main__":
    unittest.main()
