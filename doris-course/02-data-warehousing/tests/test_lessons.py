"""Offline checks of the lessons (course.md), the optional reading, and their quizzes and Labs."""

import json
import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
LESSONS = sorted(ROOT.glob("level*/module*/course.md"))
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
    def test_every_module_has_a_lesson(self):
        self.assertEqual([lesson.parent for lesson in LESSONS], sorted(ROOT.glob("level*/module*")))
        self.assertEqual(len(LESSONS), 14)

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
                # The Lab's cover shows the title and the minutes that the lesson gives it.
                lab_title = re.search(rf"^## Lab {number}: (.+)$", lesson, re.M)[1]
                lab_minutes = re.search(r"Estimated time \| About \d+ minutes: reading \d+, Lab (\d+)", lesson)[1]
                self.assertIn(f">LAB {number} · DATA WAREHOUSING WITH APACHE DORIS</div>", header)
                self.assertIn(f'font-size:30px;line-height:1.3;font-weight:750;margin:0 0 10px">{lab_title}</div>', header)
                self.assertIn(f"Plan about {lab_minutes} minutes", header)
                self.assertEqual(header.count("<div"), header.count("</div>"))
                quiz_header = "".join(json.loads(quiz_yaml.with_suffix(".ipynb").read_text())["cells"][0]["source"])
                self.assertIn(f">QUIZ {int(number):02d} · DATA WAREHOUSING WITH APACHE DORIS</div>", quiz_header)
                self.assertIn(f'font-size:30px;line-height:1.3;font-weight:750;margin:0 0 10px">{name}</div>', quiz_header)
                self.assertEqual(quiz_header.count("<div"), quiz_header.count("</div>"))

    def test_the_course_readme_lists_every_module_and_port(self):
        from dw_course.environment import BACKUP_PORTS, BI_PORTS, LAKE_PORTS, SANDBOX_PORTS

        readme = (ROOT / "README.md").read_text()
        for heading in ("Who this course is for", "What you will learn", "Course outline", "Environment",
                        "Get started", "Dataset", "Clean up", "Troubleshooting"):
            self.assertIn(f"\n## {heading}\n", readme)
        outline = readme.split("## Course outline", 1)[1].split("\n## ", 1)[0]
        rows = re.findall(r"^\| (\d) \| \[(Module \d+: [^\]]+)\]\(([^)]+)\) \| [^|]+ \| (\d+) min \|$", outline, re.M)
        self.assertEqual([path for _, _, path, _ in rows], [str(path.relative_to(ROOT)) for path in LESSONS])
        for level, heading, path, minutes in rows:
            with self.subTest(module=heading):
                lesson = (ROOT / path).read_text()
                self.assertTrue(lesson.startswith(f"# {heading}\n"))
                self.assertEqual(path.split("/")[0], f"level{level}")
                self.assertIn(f"Estimated time | About {minutes} minutes:", lesson)
        environment = readme.split("## Environment", 1)[1].split("\n## ", 1)[0]
        for variable, (port, _) in {**SANDBOX_PORTS, **LAKE_PORTS, **BI_PORTS, **BACKUP_PORTS}.items():
            self.assertRegex(environment, rf"\| {port} \| [^|]+ \| `{variable}` \|")

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

    def test_level2_and_3_lessons_label_the_statements_that_write(self):
        # Level 1's examples have their own rules in test_course.py.
        for path in LESSONS:
            if path.parts[-3] == "level1":
                continue
            lesson = path.read_text()
            blocks = re.findall(r"(?:^((?:[^\n]+\n)?[^\n]+)\n\n(<!-- reading-only-example -->)\n)?^```sql\n(.*?)^```",
                                lesson, re.M | re.S)
            self.assertTrue(blocks, path)
            for label, marker, block in blocks:
                with self.subTest(lesson=path.parent.name, block=block.split("\n", 1)[0]):
                    if marker:
                        # A statement that writes shows what the Lab runs, or that nothing runs it.
                        self.assertRegex(label, r"^(?:.+\n)?\*\*SQL reading example: .+\.\*\*")
                        self.assertRegex(label, r"Do not (?:rerun it after|run (?:it|them) outside) the Lab|not executed in the Lab")
                        continue
                    for statement in (s.strip() for s in block.split(";") if s.strip()):
                        self.assertRegex(statement, r"^(SELECT|WITH|EXPLAIN|SHOW)\b")

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
