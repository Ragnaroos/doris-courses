#!/usr/bin/env python3
"""Check each course's release manifest, course.yaml.

Usage (from the repository root, with PyYAML installed; any course virtual
environment has it):
    python3 tools/check_course_manifests.py [COURSE_DIR ...]

COURSE_DIR defaults to every course in doris-course/, the directories whose
names start with two digits. A manifest lists the course's modules in order,
with the lesson, Lab, quiz, and time of each, for a course catalog to publish:

    slug: real-time-analytics        # the directory name without its number
    title: Real-time Analytics with Apache Doris
    status: published                # draft, preview, or published
    language: en
    doris_version: "4.1.3"
    estimated_minutes: 950           # the sum of the modules' minutes
    modules:
      - slug: introduction           # the module lives in levelN/moduleNN-<slug>/
        level: 1
        order: 1                     # 1, 2, 3, ... across the whole course
        title: Introduction to Apache Doris
        course: level1/module01-introduction/course.md
        lab: level1/module01-introduction/lab01_start_doris_and_build_baseline.ipynb
        quiz: level1/module01-introduction/quiz01_doris_fundamentals.yaml
        estimated_minutes: 70
        optional:                    # optional Labs and readings, if the module has any
          - title: "Lab 1 Optional: Connect Metabase and Build a Dashboard"
            path: level1/module01-introduction/optional01_metabase_dashboard.ipynb
            # quiz: <path>             only when the optional part has a quiz of its own

The check fails when a field is missing, unknown, or of the wrong type; when a
path does not exist, lies outside the course directory, or is not named the
way the courses name their files; when a module, Lab, quiz, or optional part
in the course directory is not listed; when a title or a time differs from the
lesson ("# Module N: <title>" and its "Estimated time" row), the quiz title,
or the course README (its first heading and the rows of its course outline);
when a quiz does not follow the quiz structure described in
doris-course/common/doris_labkit/quizbank.py; and when the courses do not all
use the same Doris version. Relative links inside the listed files are checked
by tools/check_links.py.
"""
import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

try:
    import yaml
except ImportError:  # pragma: no cover - depends on the local environment
    sys.exit("PyYAML is required: run this script with a course virtual environment, "
             "or `python3 -m pip install -r tools/requirements.txt`.")

sys.path.insert(0, str(REPO / "doris-course/common"))
from doris_labkit.quizbank import structure_problems  # noqa: E402

COURSE_KEYS = ("slug", "title", "status", "language", "doris_version", "estimated_minutes", "modules")
MODULE_KEYS = ("slug", "level", "order", "title", "course", "lab", "quiz", "estimated_minutes")
OPTIONAL_PART_KEYS = ("title", "path")
STATUSES = ("draft", "preview", "published")
LANGUAGES = ("en",)
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
VERSION = re.compile(r"^\d+\.\d+\.\d+$")
LESSON_MINUTES = re.compile(r"^\| Estimated time \| About (\d+) minutes\b", re.M)
OUTLINE_ROW = re.compile(
    r"^\| *(\d+) *\| *\[Module (\d+): ([^\]]+)\]\(([^)\s]+)\) *\|.*?\| *(\d+) min *\|", re.M)
LISTED_FILES = ("lab*.ipynb", "quiz*.yaml", "quiz*.ipynb", "optional*", "extension*.ipynb")
SKIP_DIRS = {".venv", ".runtime", ".ipynb_checkpoints", "__pycache__"}


def display(path):
    try:
        return path.relative_to(REPO)
    except ValueError:
        return path


def is_count(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def is_text(value):
    return isinstance(value, str) and value.strip() != ""


def first_heading(path):
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


class Course:
    """One course directory: its manifest, the files that the manifest lists, and the problems found."""

    def __init__(self, directory):
        self.directory = directory
        self.path = directory / "course.yaml"
        self.manifest = None
        self.problems = []
        self.listed_files = set()
        self.listed_modules = set()

    def problem(self, message):
        self.problems.append(f"{display(self.path)}: {message}")

    def keys(self, mapping, required, optional, where):
        for key in required:
            if key not in mapping:
                self.problem(f"{where}missing '{key}'")
        for key in mapping:
            if key not in required and key not in optional:
                self.problem(f"{where}unknown key '{key}'")

    def load(self, path, where):
        try:
            return yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as error:
            self.problem(f"{where}{path.name} is not valid YAML: {error}")
            return None

    def file(self, value, where, what, pattern):
        """Return the listed file, or record why it cannot be used and return None."""
        if not is_text(value):
            self.problem(f"{where}'{what}' must be a path relative to the course directory")
            return None
        path = (self.directory / value).resolve()
        if Path(value).is_absolute() or self.directory.resolve() not in path.parents:
            self.problem(f"{where}{what} '{value}' is outside the course directory")
            return None
        if not re.fullmatch(pattern, value):
            self.problem(f"{where}{what} '{value}' is not named as expected ({pattern})")
        if not path.is_file():
            self.problem(f"{where}{what} '{value}' does not exist")
            return None
        self.listed_files.add(path)
        return path

    def quiz(self, value, where, directory, order, module_title=None):
        """Check a quiz and its notebook; a module's own quiz carries the module's title."""
        path = self.file(value, where, "quiz", rf"{re.escape(directory)}/quiz{order:02d}_[a-z0-9_]+\.yaml")
        if path is None:
            return
        notebook = path.with_suffix(".ipynb")
        if notebook.is_file():
            self.listed_files.add(notebook)
        else:
            self.problem(f"{where}the quiz has no notebook {notebook.name} next to it")
        document = self.load(path, where)
        for found in structure_problems(document):
            self.problem(f"{where}{value}: {found}")
        title = document.get("title") if isinstance(document, dict) else None
        if not isinstance(title, str):
            return
        if module_title is not None and title != f"Module {order} Quiz: {module_title}":
            self.problem(f"{where}the quiz title is '{title}', expected 'Module {order} Quiz: {module_title}'")
        elif module_title is None and not title.startswith(f"Module {order} Quiz: "):
            self.problem(f"{where}the quiz title is '{title}', expected 'Module {order} Quiz: ' and its name")

    def check(self):
        if not self.path.is_file():
            self.problem("missing; every course lists its modules in course.yaml")
            return
        manifest = self.manifest = self.load(self.path, "")
        if not isinstance(manifest, dict):
            self.problem("must contain a mapping with " + ", ".join(COURSE_KEYS))
            return
        self.keys(manifest, COURSE_KEYS, (), "")
        slug = re.sub(r"^\d\d-", "", self.directory.name)
        if manifest.get("slug") != slug:
            self.problem(f"slug is '{manifest.get('slug')}', expected '{slug}', the directory name without its number")
        title, status = manifest.get("title"), manifest.get("status")
        if not is_text(title):
            self.problem("'title' must be non-empty text")
        if status not in STATUSES:
            self.problem(f"status must be one of {', '.join(STATUSES)}")
        if manifest.get("language") not in LANGUAGES:
            self.problem(f"language must be one of {', '.join(LANGUAGES)}")
        version = manifest.get("doris_version")
        if not isinstance(version, str) or not VERSION.match(version):
            self.problem('doris_version must be a quoted version such as "4.1.3"')
        modules = manifest.get("modules")
        if not isinstance(modules, list) or not modules:
            self.problem("'modules' must be a non-empty list")
            return
        outline = self.check_readme(title, status, len(modules))
        for order, module in enumerate(modules, start=1):
            self.check_module(order, module, outline)
        minutes = [module.get("estimated_minutes") for module in modules if isinstance(module, dict)]
        if not is_count(manifest.get("estimated_minutes")):
            self.problem("estimated_minutes must be a positive whole number")
        elif all(is_count(value) for value in minutes) and manifest["estimated_minutes"] != sum(minutes):
            self.problem(f"estimated_minutes is {manifest['estimated_minutes']}, "
                         f"but the modules add up to {sum(minutes)}")
        slugs = [module.get("slug") for module in modules if isinstance(module, dict)]
        for slug in sorted({slug for slug in slugs if isinstance(slug, str) and slugs.count(slug) > 1}):
            self.problem(f"the module slug '{slug}' is used more than once")
        self.check_everything_is_listed()

    def check_readme(self, title, status, count):
        """Check the README's heading; return its course outline rows by module number, or None."""
        readme = self.directory / "README.md"
        if not readme.is_file():
            self.problem("the course has no README.md")
            return None
        heading = first_heading(readme)
        allowed = {title, f"{title} (Preview)"} if status == "preview" else {title}
        if is_text(title) and heading not in allowed:
            self.problem(f"the README's first heading is '{heading}', expected '{title}'"
                         + (", optionally followed by ' (Preview)'" if status == "preview" else ""))
        parts = readme.read_text(encoding="utf-8").split("\n## Course outline", 1)
        if len(parts) < 2:
            self.problem("the README has no '## Course outline' section")
            return None
        rows = OUTLINE_ROW.findall(parts[1].split("\n## ", 1)[0])
        numbers = [int(row[1]) for row in rows]
        if numbers != list(range(1, count + 1)):
            self.problem(f"the README's course outline must list Modules 1 to {count} in order, "
                         f"one row each; it lists {numbers}")
        return {int(row[1]): row for row in rows}

    def check_module(self, order, module, outline):
        where = f"module {order}: "
        if not isinstance(module, dict):
            self.problem(f"{where}each module must be a mapping")
            return
        self.keys(module, MODULE_KEYS, ("optional",), where)
        slug, level, title, minutes = (module.get(key) for key in ("slug", "level", "title", "estimated_minutes"))
        if not isinstance(slug, str) or not SLUG.match(slug):
            self.problem(f"{where}slug must be lowercase words joined by hyphens")
        if module.get("order") != order:
            self.problem(f"{where}order is {module.get('order')}, expected {order}: "
                         "modules are numbered in order across the course")
        previous = [m.get("level") for m in self.manifest["modules"][:order - 1] if isinstance(m, dict)]
        if not is_count(level) or any(is_count(value) and value > level for value in previous):
            self.problem(f"{where}level must be a positive whole number, never lower than an earlier module's")
        if not is_text(title):
            self.problem(f"{where}'title' must be non-empty text")
        if not is_count(minutes):
            self.problem(f"{where}estimated_minutes must be a positive whole number")
        directory = f"level{level}/module{order:02d}-{slug}"
        self.listed_modules.add(directory)
        lesson = self.file(module.get("course"), where, "course", rf"{re.escape(directory)}/course\.md")
        self.file(module.get("lab"), where, "lab", rf"{re.escape(directory)}/lab{order:02d}_[a-z0-9_]+\.ipynb")
        self.quiz(module.get("quiz"), where, directory, order, title)
        if lesson is not None:
            heading = first_heading(lesson)
            if heading != f"Module {order}: {title}":
                self.problem(f"{where}the lesson's heading is '{heading}', expected 'Module {order}: {title}'")
            found = LESSON_MINUTES.search(lesson.read_text(encoding="utf-8"))
            if not found:
                self.problem(f"{where}the lesson has no '| Estimated time | About N minutes' row")
            elif int(found[1]) != minutes:
                self.problem(f"{where}the lesson gives about {found[1]} minutes, the manifest {minutes}")
        row = outline.get(order) if outline is not None else None
        if row is not None:
            row_level, _, row_title, row_path, row_minutes = row
            if (int(row_level), row_title, row_path, int(row_minutes)) != (level, title, module.get("course"), minutes):
                self.problem(f"{where}the README's outline row says Level {row_level}, '{row_title}', "
                             f"{row_path}, {row_minutes} min; the manifest says Level {level}, '{title}', "
                             f"{module.get('course')}, {minutes} min")
        if "optional" in module:
            self.check_optional_parts(module["optional"], where, directory, order)

    def check_optional_parts(self, parts, where, directory, order):
        if not isinstance(parts, list) or not parts:
            self.problem(f"{where}'optional' must be a non-empty list when it is present")
            return
        level = directory.split("/", 1)[0]
        pattern = (rf"{re.escape(directory)}/optional{order:02d}_[a-z0-9_]+\.(?:ipynb|md)"
                   rf"|{re.escape(level)}/extensions/extension\d+_[a-z0-9_]+\.ipynb")
        for index, part in enumerate(parts, start=1):
            at = f"{where}optional part {index}: "
            if not isinstance(part, dict):
                self.problem(f"{at}each optional part must be a mapping with title and path")
                continue
            self.keys(part, OPTIONAL_PART_KEYS, ("quiz",), at)
            if not is_text(part.get("title")):
                self.problem(f"{at}'title' must be non-empty text")
            self.file(part.get("path"), at, "path", pattern)
            if "quiz" in part:
                self.quiz(part["quiz"], at, directory, order)

    def check_everything_is_listed(self):
        for lesson in sorted(self.directory.glob("level*/module*/course.md")):
            module = lesson.parent.relative_to(self.directory).as_posix()
            if module not in self.listed_modules:
                self.problem(f"the module {module} is not listed")
        for level in sorted(self.directory.glob("level*")):
            for pattern in LISTED_FILES:
                for path in sorted(level.rglob(pattern)):
                    if path.is_file() and not SKIP_DIRS & set(path.parts) and path.resolve() not in self.listed_files:
                        self.problem(f"{path.relative_to(self.directory).as_posix()} is not listed")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("courses", nargs="*", help="course directories; all of doris-course/ by default")
    args = parser.parse_args()
    directories = [Path(path).resolve() for path in args.courses] or sorted(
        path for path in (REPO / "doris-course").iterdir() if path.is_dir() and re.match(r"^\d\d-", path.name))
    courses = [Course(directory) for directory in directories]
    for course in courses:
        course.check()
    problems = [problem for course in courses for problem in course.problems]
    versions = {course.manifest.get("doris_version") for course in courses if isinstance(course.manifest, dict)}
    if len(versions) > 1:
        problems.append("the courses use different Doris versions ("
                        + ", ".join(sorted(map(str, versions))) + "); every course uses the same one")
    for problem in problems:
        print(f"PROBLEM {problem}")
    print(f"{len(courses)} course manifest(s), {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
