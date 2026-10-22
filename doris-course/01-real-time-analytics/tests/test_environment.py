"""Offline checks that every place naming a Docker resource or host port agrees."""

import json
import re
import unittest
from pathlib import Path

from doris_course import environment

ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = dict(re.findall(r'env_port\("(DORIS_RTA_\w+)", (\d+)\)', (ROOT / "doris_course/environment.py").read_text()))
SHELL_DEFAULT = re.compile(r"\$\{(DORIS_RTA_\w+):-(\d+)\}")


def notebook_sources():
    for path in sorted(ROOT.glob("level*/module*/*.ipynb")):
        for cell in json.loads(path.read_text())["cells"]:
            yield path, "".join(cell["source"])


class EnvironmentTests(unittest.TestCase):
    def test_compose_files_and_notebooks_use_the_python_defaults(self):
        places = [(path, path.read_text()) for path in sorted(ROOT.glob("level*/module*/compose*.yml"))]
        places += list(notebook_sources())
        seen = set()
        for path, text in places:
            for name, default in SHELL_DEFAULT.findall(text):
                with self.subTest(file=path.name, variable=name):
                    self.assertIn(name, DEFAULTS)
                    self.assertEqual(default, DEFAULTS[name])
                    seen.add(name)
        # Every variable that a shell cell or Compose file can see is defined once in Python.
        self.assertGreaterEqual(len(seen), 12)

    def test_names_use_the_course_prefix(self):
        for name in ("DORIS_CONTAINER", "DORIS_NETWORK", "FE_VOLUME", "BE_VOLUME", "KAFKA_CONTAINER",
                     "METABASE_CONTAINER", "METABASE_VOLUME", "M09_PROJECT"):
            self.assertTrue(getattr(environment, name).startswith("doris-rta"), name)

    def test_default_host_ports_stay_in_the_course_range(self):
        ports = [int(value) for value in DEFAULTS.values()]
        self.assertEqual(len(ports), len(set(ports)))
        for port in ports:
            self.assertTrue(10000 <= port < 20000, port)

    def test_notebooks_no_longer_name_the_old_resources(self):
        old = re.compile(r'container="doris"|start_container\("(doris|kafka|metabase)"\)|doris-course-m09'
                         r'|docker (stop|start|logs|exec|inspect)[^\n]*\s(doris|kafka|metabase)\n|127\.0\.0\.1:(9030|8030|3000)\b')
        for path, text in notebook_sources():
            with self.subTest(notebook=path.name):
                self.assertIsNone(old.search(text))


class PlatformTests(unittest.TestCase):
    README = (ROOT / "README.md").read_text(encoding="utf-8")

    def test_readme_states_every_environment_requirement(self):
        section = self.README.split("## Environment", 1)[1].split("\n## ", 1)[0]
        for row in ("| Platforms |", "| Other platforms |", "| Resources |", "| Downloads |",
                    "| Network |", "| Accounts and keys |", "| Python |"):
            self.assertIn(row, section)
        for fact in ("Apple silicon", "Linux on x86_64", "WSL 2", "4 CPUs, 8 GB of memory, and 20 GB",
                     "apache/doris:all-in-one-4.1.3", "s3.us-east-1.amazonaws.com", "mainland China"):
            self.assertIn(fact, section)

    def test_lab1_accepts_only_the_platforms_the_readme_names(self):
        lab1 = next(ROOT.glob("level1/module01-introduction/lab01_*.ipynb"))
        cells = json.loads(lab1.read_text())["cells"]
        setup = next("".join(c["source"]) for c in cells if 'case "${HOST_OS}/${HOST_ARCH}" in' in "".join(c["source"]))
        accepted = re.findall(r"^\s+([A-Za-z]+/[a-z0-9_]+(?:\|[A-Za-z]+/[a-z0-9_]+)*)\)", setup, re.M)
        self.assertEqual(accepted, ["Darwin/arm64|Darwin/aarch64", "Linux/x86_64|Linux/amd64"])
        self.assertIn("see Environment in the course README", setup)


if __name__ == "__main__":
    unittest.main()
