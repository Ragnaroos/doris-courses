"""Offline checks that every place naming a Docker resource, port, or file agrees."""

import json
import os
import re
import unittest
from pathlib import Path

from doris_course import environment
from doris_course.lab import ENV_EXAMPLE, LAUNCHER, env_file_values, read_env_file

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "level1/module01-doris-mcp"
DEFAULTS = dict(re.findall(r'env_port\("(DORIS_AI_\w+)", (\d+)\)', (ROOT / "doris_course/environment.py").read_text()))


def course_texts():
    """Yield the course README and the learner-facing files of each module with their text."""
    yield ROOT / "README.md", (ROOT / "README.md").read_text()
    for path in sorted(ROOT.glob("level*/module*/*")):
        if path.suffix == ".ipynb":
            cells = json.loads(path.read_text())["cells"]
            yield path, "\n".join("".join(cell["source"]) for cell in cells)
        elif path.name == "course.md" or path.name.startswith("quiz") or path.name in {LAUNCHER.name, ENV_EXAMPLE.name}:
            yield path, path.read_text()


class EnvironmentTests(unittest.TestCase):
    def test_ports_follow_the_course_port_range(self):
        self.assertEqual(DEFAULTS, {
            "DORIS_AI_QUERY_PORT": "39030",
            "DORIS_AI_HTTP_PORT": "38030",
            "DORIS_AI_BE_HTTP_PORT": "38040",
        })

    def test_names_use_the_course_prefix(self):
        for name in (environment.DORIS_CONTAINER, environment.DORIS_NETWORK,
                     environment.FE_VOLUME, environment.BE_VOLUME):
            with self.subTest(name=name):
                self.assertTrue(name.startswith("doris-ai"))

    def test_env_example_matches_the_python_defaults(self):
        example = read_env_file(ENV_EXAMPLE)
        self.assertEqual(example["DORIS_PORT"], DEFAULTS["DORIS_AI_QUERY_PORT"])
        self.assertEqual(example["DORIS_FE_HTTP_PORT"], DEFAULTS["DORIS_AI_HTTP_PORT"])
        self.assertEqual(example["DORIS_BE_WEBSERVER_PORT"], DEFAULTS["DORIS_AI_BE_HTTP_PORT"])
        self.assertEqual(example["DORIS_DATABASE"], environment.DATABASE)
        self.assertEqual(example["DORIS_USER"], environment.MCP_USER)
        self.assertEqual(example["MCP_TOOL_EXPOSURE_MODE"], "hierarchical")

    def test_lab_writes_every_key_of_the_example(self):
        written = env_file_values("secret")
        self.assertEqual(set(written), set(read_env_file(ENV_EXAMPLE)))

    def test_launcher_runs_the_course_server_over_stdio(self):
        text = LAUNCHER.read_text()
        self.assertTrue(os.access(LAUNCHER, os.X_OK), "run-doris-mcp-local must be executable")
        self.assertTrue(text.startswith("#!/usr/bin/env bash\n"))
        self.assertIn("set -euo pipefail", text)
        self.assertIn('ENV_FILE="$MCP_HOME/.env.mcp.local"', text)
        self.assertIn('SERVER="$COURSE_HOME/.venv/bin/doris-mcp-server"', text)
        self.assertIn('LOG_FILE_PATH="${LOG_FILE_PATH:-$MCP_HOME/logs/doris_mcp_server.log}"', text)
        self.assertRegex(text, r'\nexec "\$SERVER" --transport stdio\n$')
        # Diagnostics go to standard error: standard output carries only MCP messages.
        for line in text.splitlines():
            if line.strip().startswith("echo "):
                self.assertTrue(line.rstrip().endswith(">&2"), line)

    def test_files_the_lab_writes_are_ignored(self):
        ignored = (MODULE / ".gitignore").read_text().split()
        self.assertIn(".env.mcp.local", ignored)
        self.assertIn("logs/", ignored)

    def test_course_files_do_not_depend_on_another_course(self):
        forbidden = re.compile(r"doris-rta|1903\d|1803\d|1804\d|doris_course\.events|01-real-time-analytics|"
                               r"\bLevel 1[–-]8\b")
        for path, text in course_texts():
            with self.subTest(file=path.name):
                self.assertIsNone(forbidden.search(text), forbidden.search(text))

    def test_course_files_use_the_course_ports(self):
        ports = re.compile(r"127\.0\.0\.1:(\d{4,5})")
        allowed = {DEFAULTS[name] for name in DEFAULTS}
        for path, text in course_texts():
            for port in ports.findall(text):
                with self.subTest(file=path.name, port=port):
                    self.assertIn(port, allowed)


if __name__ == "__main__":
    unittest.main()
