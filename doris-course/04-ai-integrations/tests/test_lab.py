"""Offline tests of the lab helpers that do not need Docker or Doris."""

import json
import os
import stat
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from doris_course import lab as lab_module
from doris_course.lab import (
    MASK,
    AiIntegrationsLab,
    generate_password,
    masked_env_text,
    read_env_file,
    render_env_file,
    write_private_file,
)
from doris_course.mcp_client import run_host_session

FIXTURES = Path(__file__).with_name("fixtures")

FAKE_SERVER = textwrap.dedent('''
    from typing import Any
    from mcp.server.mcpserver import MCPServer

    server = MCPServer("fake-doris")

    @server.tool(name="doris_catalog", structured_output=True)
    def doris_catalog(child_tool: str = "", arguments: dict[str, Any] | None = None,
                      manifest_version: str = "") -> dict[str, Any]:
        """A domain tool with one child, shaped like the Doris MCP Server's."""
        if not child_tool:
            return {"mode": "manifest", "domain": "doris_catalog", "manifest_version": "catalog.test",
                    "generated_at": "2026-01-01T00:00:00Z",
                    "children": [{"name": "get_table_context", "availability": {"callable": True}}]}
        return {"mode": "result", "domain": "doris_catalog", "child_tool": child_tool,
                "manifest_version": manifest_version, "data": {"echo": arguments},
                "metadata": {"request_id": "r", "duration_ms": 1, "source": "fake", "truncated": False},
                "warnings": []}

    server.run("stdio")
''')


def make_launcher(directory: Path, body: str) -> Path:
    launcher = directory / "launcher"
    launcher.write_text("#!/usr/bin/env bash\n" + body)
    launcher.chmod(0o700)
    return launcher


class EnvFileTests(unittest.TestCase):
    def test_render_replaces_only_named_keys(self):
        template = "# comment\nDORIS_HOST=127.0.0.1\nDORIS_PASSWORD='<GENERATED_LOCAL_PASSWORD>'\nOTHER=1\n"
        text = render_env_file(template, {"DORIS_PASSWORD": "abc-DEF_123", "DORIS_HOST": "doris.local"})
        self.assertEqual(text, "# comment\nDORIS_HOST=doris.local\nDORIS_PASSWORD='abc-DEF_123'\nOTHER=1\n")

    def test_values_survive_a_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env.mcp.local"
            for password in ("plain", "with space", "it's", generate_password()):
                with self.subTest(password=password):
                    path.write_text(render_env_file("DORIS_PASSWORD=x\n", {"DORIS_PASSWORD": password}))
                    self.assertEqual(read_env_file(path)["DORIS_PASSWORD"], password)

    def test_bash_reads_the_same_password(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env.mcp.local"
            password = "it's a test"
            path.write_text(render_env_file("DORIS_PASSWORD=x\n", {"DORIS_PASSWORD": password}))
            import subprocess
            result = subprocess.run(["bash", "-c", f'set -a; . "{path}"; printf %s "$DORIS_PASSWORD"'],
                                    capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout, password)

    def test_generated_passwords_are_shell_and_sql_safe(self):
        for _ in range(50):
            password = generate_password()
            self.assertGreaterEqual(len(password), 24)
            self.assertRegex(password, r"^[A-Za-z0-9_-]+$")

    def test_private_file_is_readable_only_by_the_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env.mcp.local"
            path.write_text("old")
            path.chmod(0o644)
            write_private_file(path, "DORIS_PASSWORD='secret'\n")
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(path.read_text(), "DORIS_PASSWORD='secret'\n")

    def test_masked_text_hides_only_the_password(self):
        text = "DORIS_USER=mcp_reader\nDORIS_PASSWORD='secret'\n"
        masked = masked_env_text(text)
        self.assertNotIn("secret", masked)
        self.assertIn(f"DORIS_PASSWORD='{MASK}'", masked)
        self.assertIn("DORIS_USER=mcp_reader", masked)


class DatasetLoadTests(unittest.TestCase):
    def test_table_ddl_declares_every_column_with_its_comment(self):
        lab = AiIntegrationsLab.__new__(AiIntegrationsLab)
        lab.dataset = lab_module.load_dataset_spec()
        ddl = lab._table_ddl()
        for column in lab.dataset["columns"]:
            self.assertIn(f'{column["name"]} {column["type"]} NOT NULL', ddl)
            self.assertIn(f'COMMENT "{column["comment"]}"', ddl)
        self.assertIn("DUPLICATE KEY(event_time, event_id)", ddl)
        self.assertIn('DEFAULT "0.00"', ddl)

    def test_insert_values_are_typed(self):
        values = AiIntegrationsLab._values(
            ["2026-03-01 00:10:30", "1", "50758", "purchase", "US", "1132", "12.50"])
        self.assertEqual(values, "('2026-03-01 00:10:30', 1, 50758, 'purchase', 'US', 1132, 12.50)")
        with self.assertRaises(ValueError):
            AiIntegrationsLab._values(["2026-03-01 00:10:30", "1; DROP", "1", "view", "US", "1", "0"])


class ResultDisplayTests(unittest.TestCase):
    """The summaries of the reference trace read the fields the lesson talks about."""

    @classmethod
    def setUpClass(cls):
        cls.results = json.loads((FIXTURES / "reference_results.json").read_text())

    def frames(self, result):
        shown = []
        lab = AiIntegrationsLab.__new__(AiIntegrationsLab)
        with mock.patch.object(lab_module, "show_frame", lambda title, frame, **_: shown.append((title, frame))):
            lab._show_result(result)
        return dict(shown)

    def test_table_context_summary(self):
        frames = self.frames(self.results["doris_catalog.get_table_context"])
        columns = frames["Columns returned by get_table_context"]
        self.assertEqual(list(columns["column"]), ["event_time", "event_id", "user_id", "event_type",
                                                   "region", "product_id", "revenue"])
        self.assertEqual(list(columns["key"]), ["YES", "YES", "NO", "NO", "NO", "NO", "NO"])
        evidence = dict(zip(frames["Evidence fields"]["field"], frames["Evidence fields"]["value"]))
        self.assertEqual(evidence["status"], "success")
        self.assertEqual(evidence["indexes"], "0")
        self.assertEqual(evidence["basic.row_count"], "14307")

    def test_query_summary(self):
        frames = self.frames(self.results["doris_query.execute_query"])
        rows = frames["Rows returned by execute_query"]
        self.assertEqual(rows.values.tolist(), [["view", 2904, 453], ["cart", 238, 204], ["purchase", 106, 94]])
        evidence = dict(zip(frames["Evidence fields"]["field"], frames["Evidence fields"]["value"]))
        self.assertEqual((evidence["operation"], evidence["truncated"], evidence["max_rows"]),
                         ("SELECT", "False", "100"))

    def test_memory_summary(self):
        frames = self.frames(self.results["doris_cluster.get_memory_stats"])
        memory = frames["Memory values for BE node configured_0"]
        self.assertEqual(list(memory["metric"]), [name for name, _ in lab_module.MEMORY_METRICS])
        evidence = dict(zip(frames["Evidence fields"]["field"], frames["Evidence fields"]["value"]))
        self.assertEqual((evidence["metric source"], evidence["invented_values"], evidence["status"]),
                         ("doris_be_metrics", "False", "success"))

    def test_discovery_lists_unavailable_children_with_a_reason(self):
        children = self.results["doris_query.discovery"]["children"]
        unavailable = {child["name"]: child["availability"]["reason_code"]
                       for child in children if not child["availability"]["callable"]}
        self.assertEqual(unavailable["list_slow_queries"], "RUNTIME_PROBE_FAILED")


class HostSessionTests(unittest.TestCase):
    """run_host_session starts a launcher the way a Host does."""

    def test_discovery_then_child_call(self):
        with tempfile.TemporaryDirectory() as directory:
            server = Path(directory) / "fake_server.py"
            server.write_text(FAKE_SERVER)
            launcher = make_launcher(Path(directory), f'exec "{sys.executable}" "{server}"\n')
            session = run_host_session(launcher, [("doris_catalog", "get_table_context", {"table": "events"})],
                                       timeout_seconds=60)
        self.assertTrue(session.ok, session.error)
        self.assertEqual(session.server, "fake-doris")
        self.assertEqual(session.tools, ["doris_catalog"])
        discovery, child = session.calls
        self.assertEqual((discovery.arguments, discovery.result["mode"]), ({}, "manifest"))
        self.assertEqual(child.arguments, {"child_tool": "get_table_context", "arguments": {"table": "events"},
                                           "manifest_version": "catalog.test"})
        self.assertEqual(child.result["data"], {"echo": {"table": "events"}})

    def test_launcher_runs_with_a_host_like_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            server = Path(directory) / "fake_server.py"
            server.write_text(FAKE_SERVER)
            launcher = make_launcher(Path(directory), textwrap.dedent(f'''
                [ "$(pwd)" = / ] || {{ echo "working directory is $(pwd)" >&2; exit 1; }}
                [ -z "${{DORIS_AI_SECRET_FOR_TEST:-}}" ] || {{ echo "inherited the notebook environment" >&2; exit 1; }}
                exec "{sys.executable}" "{server}"
            '''))
            with mock.patch.dict(os.environ, {"DORIS_AI_SECRET_FOR_TEST": "1"}):
                session = run_host_session(launcher, timeout_seconds=60)
        self.assertTrue(session.ok, session.error + session.stderr)

    def test_a_failing_launcher_is_reported_with_its_stderr(self):
        with tempfile.TemporaryDirectory() as directory:
            launcher = make_launcher(Path(directory), 'echo "run-doris-mcp-local: .env.mcp.local is missing" >&2\nexit 1\n')
            session = run_host_session(launcher, timeout_seconds=30)
        self.assertFalse(session.ok)
        self.assertIn("Connection closed", session.error)
        self.assertIn(".env.mcp.local is missing", session.stderr)

    def test_a_silent_server_times_out(self):
        with tempfile.TemporaryDirectory() as directory:
            launcher = make_launcher(Path(directory), "exec sleep 30\n")
            session = run_host_session(launcher, timeout_seconds=2)
        self.assertFalse(session.ok)
        self.assertIn("did not answer within 2 seconds", session.error)


if __name__ == "__main__":
    unittest.main()
