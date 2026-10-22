"""Offline checks of the lessons (course.md) and of their links to the Labs and quizzes."""

import json
import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
LESSONS = sorted(ROOT.glob("level*/module*/course.md"))


def objectives(lesson):
    """The numbered items of a lesson's Learning objectives section."""
    section = lesson.split("## Learning objectives", 1)[1].split("\n## ", 1)[0]
    return re.findall(r"^\d+\. (.+)$", section, re.M)


def section(lesson, heading):
    """The text of one `## ` section, without its heading."""
    return lesson.split(f"\n## {heading}", 1)[1].split("\n## ", 1)[0]


def cover(notebook):
    return "".join(json.loads(notebook.read_text())["cells"][0]["source"])


class LessonTests(unittest.TestCase):
    def test_every_module_has_a_lesson(self):
        self.assertEqual([lesson.parent for lesson in LESSONS], sorted(ROOT.glob("level*/module*")))
        self.assertEqual(len(LESSONS), 10)

    def test_a_lesson_names_its_module_as_its_lab_and_quiz_do(self):
        for path in LESSONS:
            lesson = path.read_text()
            title = re.match(r"# (Module (\d+): (.+))\n", lesson)
            with self.subTest(lesson=path.parent.name):
                self.assertIsNotNone(title)
                heading, number, name = title.groups()
                quiz_yaml = next(path.parent.glob("quiz*.yaml"))
                quiz = quiz_yaml.with_suffix(".ipynb")
                lab = next(path.parent.glob("lab*.ipynb"))
                self.assertEqual(yaml.safe_load(quiz_yaml.read_text())["title"], f"Module {number} Quiz: {name}")
                self.assertIn(f"]({lab.name})", lesson)
                self.assertIn(f"]({quiz.name})", lesson)
                # The Lab's cover shows the module, the title, and the minutes that the lesson gives it.
                header = cover(lab)
                self.assertIn(f"**{heading}** · [Lesson](course.md) · [Quiz]({quiz.name})", header)
                lab_title = re.search(rf"^## Lab {number}: (.+)$", lesson, re.M)[1]
                lab_minutes = re.search(r"Estimated time \| About \d+ minutes: reading \d+, Lab (\d+)", lesson)[1]
                self.assertIn(f">LAB {int(number):02d} · REAL-TIME ANALYTICS WITH APACHE DORIS</div>", header)
                self.assertIn(f'font-weight:750;margin:0 0 10px">{lab_title}</div>', header)
                self.assertIn(f"Plan about {lab_minutes} minutes", header)
                self.assertEqual(header.count("<div"), header.count("</div>"))
                # The quiz's cover shows the module's name and leads back to the lesson and the Lab.
                quiz_header = cover(quiz)
                self.assertIn(f">QUIZ {int(number):02d} · REAL-TIME ANALYTICS WITH APACHE DORIS</div>", quiz_header)
                self.assertIn(f'font-weight:750;margin:0 0 10px">{name}</div>', quiz_header)
                self.assertIn(f"[Lesson](course.md) · [Lab]({lab.name})", quiz_header)
                self.assertIn("6 questions · Single choice", quiz_header)
                self.assertEqual(quiz_header.count("<div"), quiz_header.count("</div>"))

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
                structure = section(lesson, "Module structure")
                listed = re.findall(r"^\| (\d+\.\d+ [^|]+?) \|", structure, re.M)
                self.assertEqual(listed, re.findall(r"^## (\d+\.\d+ .+)$", lesson, re.M))
                minutes = [int(value) for value in re.findall(r"^\| \d+\.\d+ [^|]+\| (\d+) min \|", structure, re.M)]
                self.assertEqual(sum(minutes), int(info.group(2)))
                self.assertRegex(structure, rf"(?m)^\| Lab \d+ \| {info.group(3)} min \|")
                self.assertRegex(structure, rf"(?m)^\| Quiz \d+ \| {info.group(4)} min \|")
                # The summary returns to each objective, and the quiz section leads on.
                summary = section(lesson, "Summary")
                self.assertEqual(len(re.findall(r"^- ", summary, re.M)), len(objectives(lesson)))
                quiz_section = lesson.split("\n## Quiz ", 1)[1].split("\n## ", 1)[0]
                self.assertIn("six single-choice questions", quiz_section)
                self.assertRegex(quiz_section, r"Next(?: module)?: ")

    def test_each_quiz_question_tests_an_objective_of_its_lesson(self):
        for path in LESSONS:
            quiz = yaml.safe_load(next(path.parent.glob("quiz*.yaml")).read_text())
            with self.subTest(lesson=path.parent.name):
                # One question per objective, in the lesson's own words.
                self.assertEqual(sorted(question["objective"] for question in quiz["questions"]),
                                 sorted(objectives(path.read_text())))

    def test_a_quiz_notebook_lists_the_objectives_it_assesses(self):
        for path in LESSONS:
            quiz = next(path.parent.glob("quiz*.ipynb"))
            cells = json.loads(quiz.read_text())["cells"]
            purpose = next("".join(cell["source"]) for cell in cells if cell.get("id") == "quiz-purpose")
            with self.subTest(quiz=quiz.name):
                self.assertEqual(re.findall(r"^\d+\. (.+)$", purpose, re.M), objectives(path.read_text()))

    def test_every_lab_ends_with_a_practice_and_a_collapsed_reference_solution(self):
        for path in LESSONS:
            lab = next(path.parent.glob("lab*.ipynb"))
            cells = json.loads(lab.read_text())["cells"]
            ids = [cell.get("id") for cell in cells]
            with self.subTest(lab=lab.name):
                start = ids.index("practice-task")
                self.assertEqual(ids[start:start + 5], ["practice-task", "practice-work", "practice-solution-md",
                                                        "practice-solution", "practice-expected"])
                task, work, _, solution, expected = cells[start:start + 5]
                self.assertRegex("".join(task["source"]), r"^## \d+\. Practice: ")
                self.assertIn("predict", "".join(task["source"]).lower())
                self.assertEqual("".join(work["source"]), "# Your code here")
                self.assertTrue(solution["metadata"]["jupyter"]["source_hidden"])
                self.assertIn("reference-solution", solution["metadata"]["tags"])
                self.assertTrue("".join(expected["source"]).startswith("**Expected result**"))
                # The practice comes before the optional stop and restart cells.
                stop = next(index for index, cell in enumerate(cells)
                            if re.match(r"### Stop the (Doris sandbox|Kafka sandbox|Module 9 cluster)",
                                        "".join(cell["source"])))
                self.assertLess(start, stop)

    def test_external_links_point_at_versioned_doris_documentation(self):
        for path in LESSONS:
            for url in re.findall(r"\((https://doris\.apache\.org/[^)]+)\)", path.read_text()):
                with self.subTest(lesson=path.parent.name, url=url):
                    self.assertRegex(url, r"^https://doris\.apache\.org/(docs/4\.x|community|use-cases)/")
            for url in re.findall(r"\((https://github\.com/apache/doris/blob/[^)]+)\)", path.read_text()):
                with self.subTest(lesson=path.parent.name, url=url):
                    self.assertIn("/blob/4.1.3/", url)


class ReadmeTests(unittest.TestCase):
    README = (ROOT / "README.md").read_text()

    def test_readme_has_the_sections_of_the_course_template(self):
        self.assertEqual(re.findall(r"^## (.+)$", self.README, re.M), [
            "Who this course is for", "What you will learn", "Course outline", "Environment", "Get started",
            "Dataset", "Clean up", "Troubleshooting",
        ])

    def test_readme_outline_leads_to_every_lesson_with_its_time(self):
        outline = self.README.split("## Course outline", 1)[1].split("\n## ", 1)[0]
        rows = re.findall(r"^\| (\d) \| \[(Module \d+: [^\]]+)\]\(([^)]+)\) \| [^|]+ \| (\d+) min \|$", outline, re.M)
        self.assertEqual([row[2] for row in rows], [lesson.relative_to(ROOT).as_posix() for lesson in LESSONS])
        for level, name, path, minutes in rows:
            with self.subTest(module=name):
                # The outline uses the lesson's own name, level, and total time.
                lesson = (ROOT / path).read_text()
                self.assertTrue(lesson.startswith(f"# {name}\n"))
                self.assertEqual(path.split("/")[0], f"level{level}")
                self.assertIn(f"Estimated time | About {minutes} minutes:", lesson)

    def test_readme_lists_every_port_variable(self):
        variables = set(re.findall(r'env_port\("(DORIS_RTA_\w+)"', (ROOT / "doris_course/environment.py").read_text()))
        self.assertTrue(variables)
        for variable in sorted(variables):
            with self.subTest(variable=variable):
                self.assertIn(f"`{variable}`", self.README)


if __name__ == "__main__":
    unittest.main()
