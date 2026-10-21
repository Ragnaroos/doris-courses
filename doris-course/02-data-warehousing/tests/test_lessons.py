"""Offline checks of the lessons (course.md), the optional reading, and their quizzes and Labs."""

import json
import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
LESSONS = sorted(ROOT.glob("level1/module*/course.md"))
READING = ROOT / "level1/module05-ingestion/optional05_continuous_ingestion.md"


def objectives(text):
    """The numbered items of a lesson's Learning objectives section."""
    section = text.split("## Learning objectives", 1)[1].split("\n## ", 1)[0]
    return re.findall(r"^\d+\. (.+)$", section, re.M)


def quiz_for(path, text):
    """The quiz YAML of the quiz notebook that a lesson's or a reading's quiz section links to."""
    section = re.search(r"^## Quiz.*?$(.*?)(?=^## |\Z)", text, re.M | re.S)[1]
    notebook = re.search(r"\]\((quiz[^)]+\.ipynb)\)", section)[1]
    return path.parent / notebook.replace(".ipynb", ".yaml")


class LessonTests(unittest.TestCase):
    def test_every_level1_module_has_a_lesson(self):
        self.assertEqual([lesson.parent for lesson in LESSONS], sorted(ROOT.glob("level1/module*")))

    def test_a_lesson_names_its_module_as_its_lab_and_quiz_do(self):
        for path in LESSONS:
            lesson = path.read_text()
            title = re.match(r"# (Module (\d+): (.+))\n", lesson)
            with self.subTest(lesson=path.parent.name):
                self.assertIsNotNone(title)
                heading, number, name = title.groups()
                quiz_yaml = quiz_for(path, lesson)
                self.assertEqual(yaml.safe_load(quiz_yaml.read_text())["title"], f"Module {number} Quiz: {name}")
                lab = next(path.parent.glob("lab*.ipynb"))
                header = "".join(json.loads(lab.read_text())["cells"][0]["source"])
                self.assertIn(f"**{heading}** · [Lesson](course.md) · [Quiz]({quiz_yaml.with_suffix('.ipynb').name})", header)
                self.assertIn(f"]({lab.name})", lesson)

    def test_a_lesson_has_the_sections_of_the_course_template(self):
        for path in LESSONS:
            lesson = path.read_text()
            with self.subTest(lesson=path.parent.name):
                headings = re.findall(r"^## (.+)$", lesson, re.M)
                for required in ("Module goal", "Learning objectives", "Module structure", "Summary", "References"):
                    self.assertIn(required, headings)
                self.assertTrue(any(heading.startswith("Lab ") for heading in headings))
                self.assertTrue(any(heading.startswith("Quiz ") for heading in headings))
                self.assertLessEqual(3, len(objectives(lesson)))
                self.assertLessEqual(len(objectives(lesson)), 6)
                info = re.search(r"Estimated time \| About (\d+) minutes: reading (\d+), Lab (\d+), quiz (\d+)", lesson)
                self.assertIsNotNone(info)
                total, *parts = (int(value) for value in info.groups())
                self.assertEqual(total, sum(parts))
                # The structure table lists every numbered section, in order, with its minutes.
                structure = lesson.split("## Module structure", 1)[1].split("\n## ", 1)[0]
                listed = re.findall(r"^\| (\d+\.\d+ [^|]+?) \|", structure, re.M)
                self.assertEqual(listed, re.findall(r"^## (\d+\.\d+ .+)$", lesson, re.M))
                minutes = [int(value) for value in re.findall(r"^\| \d+\.\d+ [^|]+\| (\d+) min \|", structure, re.M)]
                self.assertEqual(sum(minutes), int(info.group(2)))
                # The summary returns to each objective, and the quiz section leads on.
                summary = lesson.split("## Summary", 1)[1].split("\n## ", 1)[0]
                self.assertEqual(len(re.findall(r"^- ", summary, re.M)), len(objectives(lesson)))
                quiz_section = lesson.split("\n## Quiz ", 1)[1].split("\n## ", 1)[0]
                self.assertRegex(quiz_section, r"Next(?: module)?: ")

    def test_each_quiz_question_tests_an_objective_of_its_lesson(self):
        for path in [*LESSONS, READING]:
            text = path.read_text()
            quiz = yaml.safe_load(quiz_for(path, text).read_text())
            with self.subTest(text=path.name):
                # One question per objective, in the lesson's own words.
                self.assertEqual(sorted(question["objective"] for question in quiz["questions"]),
                                 sorted(objectives(text)))

    def test_external_links_point_at_versioned_doris_documentation(self):
        for path in [*LESSONS, READING]:
            for url in re.findall(r"\((https://doris\.apache\.org/[^)]+)\)", path.read_text()):
                with self.subTest(text=path.name, url=url):
                    self.assertRegex(url, r"^https://doris\.apache\.org/(docs/4\.x|community)/")


class OptionalReadingTests(unittest.TestCase):
    TEXT = READING.read_text()

    def test_the_reading_links_its_labs_and_its_quiz(self):
        for target in ("optional05_kafka_routine_load.ipynb", "optional05_flink_mysql_cdc.ipynb",
                       "quiz05_continuous_ingestion.ipynb", "course.md"):
            self.assertIn(f"]({target})", self.TEXT)
        lesson = (ROOT / "level1/module05-ingestion/course.md").read_text()
        self.assertIn("](optional05_continuous_ingestion.md)", lesson)

    def test_the_reading_keeps_the_experimental_boundary_and_examples(self):
        streaming = self.TEXT.split("## Streaming Jobs and CDC_STREAM", 1)[1].split("\n## ", 1)[0]
        self.assertIn("Experimental", streaming)
        examples = re.findall(r"\*\*External environment example; not executed in the lab\.\*\*(.*?)(?=\n## |\Z)",
                              self.TEXT, re.S)
        self.assertEqual(len(examples), 3)
        for example in examples:
            self.assertIn("<!-- external-service-example -->\n```sql", example)
            self.assertRegex(example, r"[Ee]xpect|should show")
        for job in ("SHOW ROUTINE LOAD FOR orders_kafka_job", "Name = 'orders_mysql_job'", "Name = 'orders_files_job'"):
            self.assertIn(job, self.TEXT)


if __name__ == "__main__":
    unittest.main()
