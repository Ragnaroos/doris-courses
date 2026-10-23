"""Run tools/check_course_manifests.py on small course trees and check its verdicts."""

import copy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

TOOL = Path(__file__).resolve().parents[1] / "check_course_manifests.py"

README = """# Example Course

One paragraph.

## Course outline

| Level | Module | What you will do | Time |
| --- | --- | --- | --- |
| 1 | [Module 1: First Steps](level1/module01-first-steps/course.md) | Start | 30 min |
| 2 | [Module 2: Next Steps](level2/module02-next-steps/course.md) | Continue | 40 min |

## Environment
"""

MANIFEST = {
    "slug": "example",
    "title": "Example Course",
    "status": "published",
    "language": "en",
    "doris_version": "4.1.3",
    "estimated_minutes": 70,
    "modules": [
        {"slug": "first-steps", "level": 1, "order": 1, "title": "First Steps",
         "course": "level1/module01-first-steps/course.md",
         "lab": "level1/module01-first-steps/lab01_first.ipynb",
         "quiz": "level1/module01-first-steps/quiz01_first.yaml",
         "estimated_minutes": 30,
         "optional": [{"title": "Optional Lab", "path": "level1/module01-first-steps/optional01_extra.ipynb"}]},
        {"slug": "next-steps", "level": 2, "order": 2, "title": "Next Steps",
         "course": "level2/module02-next-steps/course.md",
         "lab": "level2/module02-next-steps/lab02_next.ipynb",
         "quiz": "level2/module02-next-steps/quiz02_next.yaml",
         "estimated_minutes": 40},
    ],
}


def quiz(title, letter_ids=False):
    ids = ["a", "b"] if letter_ids else ["right_option", "wrong_option"]
    return yaml.safe_dump({
        "title": title,
        "description": "Example questions.",
        "questions": [{
            "id": "q1", "objective": "Objective", "prompt": "Question?",
            "options": [{"id": ids[0], "text": "Right"}, {"id": ids[1], "text": "Wrong"}],
            "answer": ids[0], "explanation": "Because it is right.",
        }],
    }, sort_keys=False)


def course_files(manifest=None):
    files = {
        "README.md": README,
        "course.yaml": yaml.safe_dump(MANIFEST if manifest is None else manifest, sort_keys=False, allow_unicode=True),
        "level1/module01-first-steps/course.md": "# Module 1: First Steps\n\n| Estimated time | About 30 minutes: reading 10, Lab 10, quiz 10 |\n",
        "level1/module01-first-steps/lab01_first.ipynb": "{}",
        "level1/module01-first-steps/quiz01_first.yaml": quiz("Module 1 Quiz: First Steps"),
        "level1/module01-first-steps/quiz01_first.ipynb": "{}",
        "level1/module01-first-steps/optional01_extra.ipynb": "{}",
        "level1/module01-first-steps/compose.extra.yml": "services: {}\n",
        "level2/module02-next-steps/course.md": "# Module 2: Next Steps\n\n| Estimated time | About 40 minutes: reading 15, Lab 15, quiz 10 |\n",
        "level2/module02-next-steps/lab02_next.ipynb": "{}",
        "level2/module02-next-steps/quiz02_next.yaml": quiz("Module 2 Quiz: Next Steps"),
        "level2/module02-next-steps/quiz02_next.ipynb": "{}",
    }
    return files


def run(*courses):
    """Write each course (a dict of files, None to delete one) and run the check on all of them."""
    with tempfile.TemporaryDirectory() as directory:
        paths = []
        for number, files in enumerate(courses, start=1):
            root = Path(directory) / f"0{number}-example"
            for relative, text in files.items():
                if text is None:
                    continue
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
            paths.append(str(root))
        return subprocess.run([sys.executable, str(TOOL), *paths], capture_output=True, text=True)


def changed(**changes):
    """The example manifest with some fields of the course or of module 1 changed."""
    manifest = copy.deepcopy(MANIFEST)
    for key, value in changes.items():
        if key.startswith("module_"):
            manifest["modules"][0][key[len("module_"):]] = value
        else:
            manifest[key] = value
    return manifest


class CourseManifestTests(unittest.TestCase):
    def assertProblem(self, result, *fragments):
        self.assertEqual(result.returncode, 1, result.stdout)
        for fragment in fragments:
            self.assertIn(fragment, result.stdout)

    def test_a_complete_course_passes(self):
        result = run(course_files())
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("1 course manifest(s), 0 problem(s)", result.stdout)

    def test_a_missing_manifest_fails(self):
        files = course_files()
        files["course.yaml"] = None
        self.assertProblem(run(files), "course.yaml: missing")

    def test_missing_and_misnamed_files_fail(self):
        files = course_files()
        files["level1/module01-first-steps/lab01_first.ipynb"] = None
        self.assertProblem(run(files), "lab 'level1/module01-first-steps/lab01_first.ipynb' does not exist")

        files = course_files(changed(module_lab="level1/module01-first-steps/lab1_first.ipynb"))
        files["level1/module01-first-steps/lab1_first.ipynb"] = "{}"
        self.assertProblem(run(files), "is not named as expected")

        files = course_files()
        files["level1/module01-first-steps/quiz01_first.ipynb"] = None
        self.assertProblem(run(files), "the quiz has no notebook quiz01_first.ipynb")

    def test_titles_must_match_the_lesson_the_quiz_and_the_readme(self):
        result = run(course_files(changed(module_title="First Step")))
        self.assertProblem(result, "the lesson's heading is 'Module 1: First Steps', expected 'Module 1: First Step'",
                           "expected 'Module 1 Quiz: First Step'", "the README's outline row says Level 1, 'First Steps'")
        self.assertProblem(run(course_files(changed(title="Another Course"))),
                           "the README's first heading is 'Example Course', expected 'Another Course'")

    def test_a_preview_course_may_say_so_in_its_heading(self):
        files = course_files(changed(status="preview"))
        files["README.md"] = README.replace("# Example Course", "# Example Course (Preview)")
        self.assertEqual(run(files).returncode, 0)
        files = course_files()
        files["README.md"] = README.replace("# Example Course", "# Example Course (Preview)")
        self.assertProblem(run(files), "the README's first heading")

    def test_times_must_match_the_lesson_the_readme_and_the_total(self):
        result = run(course_files(changed(module_estimated_minutes=35, estimated_minutes=75)))
        self.assertProblem(result, "the lesson gives about 30 minutes, the manifest 35", "30 min; the manifest says")
        self.assertProblem(run(course_files(changed(estimated_minutes=80))),
                           "estimated_minutes is 80, but the modules add up to 70")

    def test_the_readme_lists_every_module_in_order(self):
        files = course_files()
        files["README.md"] = "\n".join(line for line in README.splitlines() if "Module 2:" not in line)
        self.assertProblem(run(files), "must list Modules 1 to 2 in order, one row each; it lists [1]")

    def test_everything_in_the_course_must_be_listed(self):
        files = course_files()
        files["level2/module02-next-steps/optional02_more.md"] = "# More\n"
        files["level2/module03-later/course.md"] = "# Module 3: Later\n"
        files["level1/extensions/extension12_more.ipynb"] = "{}"
        self.assertProblem(run(files), "level2/module02-next-steps/optional02_more.md is not listed",
                           "the module level2/module03-later is not listed",
                           "level1/extensions/extension12_more.ipynb is not listed")

    def test_paths_outside_the_course_fail(self):
        manifest = changed(module_optional=[{"title": "Notes", "path": "../../maintenance/notes.md"}])
        files = course_files(manifest)
        files["level1/module01-first-steps/optional01_extra.ipynb"] = None
        self.assertProblem(run(files), "path '../../maintenance/notes.md' is outside the course directory")

    def test_quiz_structure_is_checked(self):
        files = course_files()
        files["level1/module01-first-steps/quiz01_first.yaml"] = quiz("Module 1 Quiz: First Steps", letter_ids=True)
        self.assertProblem(run(files), "is a single letter")

    def test_fields_must_be_known_and_well_formed(self):
        manifest = changed(status="done", doris_version=4.1, owner="someone", module_order=3, module_slug="First")
        result = run(course_files(manifest))
        self.assertProblem(result, "status must be one of draft, preview, published", "doris_version must be a quoted",
                           "unknown key 'owner'", "order is 3, expected 1", "slug must be lowercase words")
        self.assertProblem(run(course_files(changed(module_optional=[]))), "'optional' must be a non-empty list")

    def test_levels_never_go_down(self):
        manifest = copy.deepcopy(MANIFEST)
        manifest["modules"][0]["level"], manifest["modules"][1]["level"] = 2, 1
        self.assertProblem(run(course_files(manifest)), "module 2: level must be a positive whole number, never lower")

    def test_courses_must_share_a_doris_version(self):
        result = run(course_files(), course_files(changed(doris_version="4.0.3")))
        self.assertProblem(result, "the courses use different Doris versions (4.0.3, 4.1.3)")


if __name__ == "__main__":
    unittest.main()
