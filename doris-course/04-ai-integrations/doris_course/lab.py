"""Lab helpers for the AI Integrations course.

``AiIntegrationsLab`` starts the course's Doris sandbox, loads the storefront
events, creates the read-only account that the MCP Server uses, writes the
launcher's protected environment file, and then checks the launcher and the
Server's answers the way a Host would see them.
"""

from __future__ import annotations

import csv
import json
import os
import platform
import re
import secrets
import shutil
import subprocess
import time
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd
import pymysql
import yaml

from doris_labkit import docker as labkit_docker
from doris_labkit.db import connect_doris, report_sql_error, sql
from doris_labkit.docker import (
    container_inspect,
    ensure_network,
    ensure_volume,
    port_in_use,
    run,
    wait_for_health,
)
from doris_labkit.results import result_frame, show_frame
from doris_labkit.ui import card, install_styles, progress_step, show_log, show_sql

from . import environment as env
from .mcp_client import HostSession, ToolCall, run_host_session

COURSE_DIR = Path(__file__).resolve().parents[1]
MODULE_DIR = COURSE_DIR / "level1/module01-doris-mcp"
LAUNCHER = MODULE_DIR / "run-doris-mcp-local"
ENV_FILE = MODULE_DIR / ".env.mcp.local"
ENV_EXAMPLE = MODULE_DIR / ".env.mcp.local.example"
LOG_DIR = MODULE_DIR / "logs"
SERVER_ERROR_LOG = LOG_DIR / "doris_mcp_server_error.log"
SERVER_AUDIT_LOG = LOG_DIR / "doris_mcp_server_audit.log"
DATASET_FILE = COURSE_DIR / "datasets/events.yaml"

MASK = "••••••••"
LOCAL_HOSTS = {"127.0.0.1", "localhost"}
# The all-in-one Doris container needs about 3 GiB; below this, Docker may stop it.
MIN_DOCKER_MEMORY = 4 * 2**30
INSERT_BATCH_ROWS = 5000
# The platforms on which the course was run end to end.
VERIFIED_PLATFORMS = {("Darwin", "arm64"), ("Darwin", "aarch64")}
EXPECTED_PLATFORMS = {("Linux", "x86_64"), ("Linux", "amd64")}
DOMAINS = (
    "doris_catalog", "doris_cluster", "doris_governance", "doris_lakehouse",
    "doris_pipeline", "doris_query", "doris_search", "doris_semantic",
)
# The leading memory values that the lesson reads from get_memory_stats.
MEMORY_METRICS = (
    ("doris_be_memory_allocated_bytes", "Total BE memory allocated"),
    ("doris_be_memory_jemalloc_resident_bytes", "jemalloc resident"),
    ("doris_be_memory_jemalloc_active_bytes", "jemalloc active"),
    ("doris_be_memory_jemalloc_allocated_bytes", "jemalloc allocated"),
)


class EnvironmentNotReady(RuntimeError):
    """A step stopped because the environment or its data is not ready.

    The card shown before raising says why and what to do.
    """

    def _render_traceback_(self) -> list[str]:
        return [f"Stopped: {self}"]


def load_dataset_spec(path: Path = DATASET_FILE) -> dict:
    """Return the description of the course data: columns, file, and expected numbers."""
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def generate_password() -> str:
    """Return a random password that is safe inside single quotes in a shell file."""
    return secrets.token_urlsafe(24)


def read_env_file(path: Path) -> dict[str, str]:
    """Read KEY=VALUE lines, removing one level of single or double quotes."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"\s*([A-Z][A-Z0-9_]*)=(.*)$", line)
        if not match:
            continue
        value = match.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1].replace("'\\''", "'")
        values[match.group(1)] = value
    return values


def _shell_value(name: str, value: str) -> str:
    if name == "DORIS_PASSWORD" or not re.fullmatch(r"[A-Za-z0-9_.,:/@-]*", value):
        return "'" + value.replace("'", "'\\''") + "'"
    return value


def render_env_file(template: str, values: Mapping[str, str]) -> str:
    """Return ``template`` with the value of each KEY=VALUE line that ``values`` names replaced."""
    lines = []
    for line in template.splitlines():
        match = re.match(r"([A-Z][A-Z0-9_]*)=", line)
        if match and match.group(1) in values:
            name = match.group(1)
            line = f"{name}={_shell_value(name, values[name])}"
        lines.append(line)
    return "\n".join(lines) + "\n"


def write_private_file(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` so that only the current user can read it (mode 600)."""
    temporary = path.with_name(path.name + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def env_file_values(password: str) -> dict[str, str]:
    """Return the values that .env.mcp.local needs for the configured Doris."""
    return {
        "DORIS_HOST": env.HOST,
        "DORIS_PORT": str(env.QUERY_PORT),
        "DORIS_USER": env.MCP_USER,
        "DORIS_PASSWORD": password,
        "DORIS_DATABASE": env.DATABASE,
        "DORIS_FE_HTTP_HOST": env.HOST,
        "DORIS_FE_HTTP_PORT": str(env.HTTP_PORT),
        "DORIS_BE_HOSTS": env.HOST,
        "DORIS_BE_WEBSERVER_PORT": str(env.BE_HTTP_PORT),
        "MCP_TOOL_EXPOSURE_MODE": "hierarchical",
    }


def masked_env_text(text: str) -> str:
    return re.sub(r"(?m)^(DORIS_PASSWORD=).*$", rf"\1'{MASK}'", text)


def _gib(value: Any) -> str:
    try:
        return f"{int(value) / 2**30:.2f} GiB"
    except (TypeError, ValueError):
        return ""


def _compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(", ", ": "))


class AiIntegrationsLab:
    """Learner-facing helpers for the AI Integrations labs."""

    def __init__(self, lab_dir: Path | None = None) -> None:
        self.lab_dir = (lab_dir or COURSE_DIR).resolve()
        self.dataset = load_dataset_spec()
        self.connection = None
        self.doris_clock_at_trace: str | None = None
        install_styles()
        self._show_ready()

    def _show_ready(self) -> None:
        target = "the course sandbox" if self.uses_sandbox else "your own Doris"
        card(
            f"Doris: {env.HOST}:{env.QUERY_PORT} (MySQL protocol), FE HTTP {env.HTTP_PORT}, "
            f"BE HTTP {env.BE_HTTP_PORT} ({target}). Launcher: {LAUNCHER}",
            "ok",
            "AI Integrations lab tools are ready",
        )

    # ------------------------------------------------------------------ helpers

    @property
    def uses_sandbox(self) -> bool:
        """False when DORIS_AI_HOST or the administrator account points the labs at another Doris."""
        return env.HOST in LOCAL_HOSTS and env.ADMIN_USER == "root" and not env.ADMIN_PASSWORD

    @property
    def launcher(self) -> Path:
        """The absolute path that every Host configuration uses."""
        return LAUNCHER

    def _failure(self, title: str, message: str, log: str = "") -> None:
        card(message, "fail", title)
        if log:
            show_log("Diagnostic details", log, opened=True)

    def _admin(self):
        if self.connection is None:
            try:
                self.connection = connect_doris(
                    host=env.HOST, port=env.QUERY_PORT, user=env.ADMIN_USER,
                    password=env.ADMIN_PASSWORD, connect_timeout=5,
                )
            except (OSError, pymysql.MySQLError) as error:
                self._failure(
                    "Doris is not reachable",
                    f"No Doris FE accepted {env.ADMIN_USER} on {env.HOST}:{env.QUERY_PORT}. Run "
                    "lab.prepare_environment() (or lab.start() after lab.stop()), then rerun this cell.",
                    str(error),
                )
                raise EnvironmentNotReady("Doris is not reachable.") from error
        return self.connection

    def _reader_connection(self, password: str | None = None):
        password = self.env_value("DORIS_PASSWORD") if password is None else password
        return pymysql.connect(
            host=env.HOST, port=env.QUERY_PORT, user=env.MCP_USER, password=password,
            charset="utf8mb4", autocommit=True, connect_timeout=5,
            cursorclass=pymysql.cursors.DictCursor,
        )

    def query(self, statement: str) -> pd.DataFrame:
        """Run a statement as the administrator and return its rows without displaying them."""
        clean = statement.strip().rstrip(";")
        with self._admin().cursor() as cursor:
            try:
                cursor.execute(clean)
            except pymysql.MySQLError as error:
                report_sql_error(None, clean, error)
                raise
            rows = cursor.fetchall() if cursor.description else []
            columns = [column[0] for column in cursor.description or ()]
        return result_frame(rows, columns)

    def sql(self, statement: str, *, title: str | None = None, final: bool = False):
        """Run a statement as the administrator and display it with its result."""
        return sql(self._admin(), statement, title=title, final=final)

    # ---------------------------------------------------------------- sandbox

    def _check_platform(self) -> None:
        system, machine = platform.system(), platform.machine().lower()
        if (system, machine) in VERIFIED_PLATFORMS:
            card(f"{system} {machine}: the course was verified on this platform.", "ok", "Host platform")
        elif (system, machine) in EXPECTED_PLATFORMS:
            card(
                f"{system} {machine}: the sandbox uses the same Doris image as on macOS, but the course was "
                "not run end to end on this platform.", "info", "Host platform",
            )
        else:
            card(
                f"{system} {machine} is not a platform this course was tested on. The launcher needs Bash; "
                "on Windows, run the course inside WSL 2.", "info", "Host platform",
            )

    def _check_docker_memory(self) -> None:
        info = run(["docker", "info", "--format", "{{.NCPU}} {{.MemTotal}}"], check=False)
        try:
            cpus, memory = (int(value) for value in info.stdout.split())
        except ValueError:
            return
        message = f"Docker can use {cpus} CPUs and {memory / 2**30:.1f} GiB of memory."
        if memory < MIN_DOCKER_MEMORY:
            card(message + " The sandbox needs about 3 GiB; give Docker at least 4 GiB if Doris stops "
                 "unexpectedly.", "info", "Docker resources")
        else:
            card(message, "ok", "Docker resources")

    def _check_ports(self) -> None:
        ports = (
            (env.QUERY_PORT, "DORIS_AI_QUERY_PORT", "FE MySQL protocol"),
            (env.HTTP_PORT, "DORIS_AI_HTTP_PORT", "FE HTTP"),
            (env.BE_HTTP_PORT, "DORIS_AI_BE_HTTP_PORT", "BE HTTP"),
        )
        state = container_inspect(env.DORIS_CONTAINER)
        published: set[int] = set()
        if state and state.get("State", {}).get("Running"):
            for bindings in (state.get("HostConfig", {}).get("PortBindings") or {}).values():
                published.update(int(item["HostPort"]) for item in bindings or [] if item.get("HostPort"))
        rows, blocked = [], []
        for port, variable, purpose in ports:
            if port in published:
                status = "used by this course"
            elif port_in_use(port):
                status = "in use"
                blocked.append(f"{port} ({variable})")
            else:
                status = "available"
            rows.append({"host_port": port, "purpose": purpose, "variable": variable, "status": status})
        show_frame("Host port check", pd.DataFrame(rows))
        if blocked:
            self._failure(
                "Required port is unavailable",
                f"Another program is using: {', '.join(blocked)}. Stop it, or set the variable to a free "
                "port before starting Jupyter, then rerun this cell.",
            )
            raise EnvironmentNotReady("a required host port is in use.")

    def _expected_container(self) -> dict:
        return {
            "image": env.DORIS_IMAGE,
            "ports": {
                "9030/tcp": ("127.0.0.1", str(env.QUERY_PORT)),
                "8030/tcp": ("127.0.0.1", str(env.HTTP_PORT)),
                f"{env.BE_HTTP_PORT}/tcp": ("127.0.0.1", str(env.BE_HTTP_PORT)),
            },
            "mounts": {
                "/opt/apache-doris/fe/doris-meta": env.FE_VOLUME,
                "/opt/apache-doris/be/storage": env.BE_VOLUME,
            },
        }

    def _container_matches(self, state: dict) -> bool:
        expected = self._expected_container()
        bindings = state.get("HostConfig", {}).get("PortBindings") or {}
        ports = {
            port: (bindings[port][0]["HostIp"], bindings[port][0]["HostPort"])
            for port in expected["ports"] if bindings.get(port)
        }
        mounts = {mount["Destination"]: mount.get("Name") for mount in state.get("Mounts", [])}
        return (
            state.get("Config", {}).get("Image") == expected["image"]
            and ports == expected["ports"]
            and all(mounts.get(path) == name for path, name in expected["mounts"].items())
            and env.DORIS_NETWORK in state.get("NetworkSettings", {}).get("Networks", {})
        )

    def prepare_environment(self) -> None:
        """Start the course's Doris sandbox, or reuse it, and show its FE and BE."""
        if not self.uses_sandbox:
            card(
                f"The DORIS_AI_HOST or DORIS_AI_ADMIN_* variables point the labs at your own Doris at "
                f"{env.HOST}:{env.QUERY_PORT}. This step starts nothing; continue with the next section.",
                "skip", "Sandbox not needed",
            )
            return
        steps = 5
        progress_step(1, steps, "Check this computer and Docker")
        self._check_platform()
        labkit_docker.ensure_docker_ready()
        self._check_docker_memory()

        progress_step(2, steps, "Check the host ports")
        self._check_ports()
        existing = container_inspect(env.DORIS_CONTAINER)
        if existing is not None and not self._container_matches(existing):
            self._failure(
                "Existing container conflict",
                f"A container named {env.DORIS_CONTAINER} exists but does not use this course's image, ports, "
                f"volumes, or network, for example because it was created with other DORIS_AI_* ports. It was "
                f"left unchanged. Set the variables back to the ports it was created with, or remove it with "
                f"`docker rm -f {env.DORIS_CONTAINER}` (its volumes keep the data) and rerun this cell.",
            )
            raise EnvironmentNotReady(f"a different container named {env.DORIS_CONTAINER} exists.")

        progress_step(3, steps, "Create or reuse the Docker network and volumes")
        ensure_network(env.DORIS_NETWORK)
        ensure_volume(env.FE_VOLUME)
        ensure_volume(env.BE_VOLUME)

        progress_step(4, steps, "Pull the pinned Doris image and start the sandbox", env.DORIS_IMAGE)
        if existing is None:
            pull = run(["docker", "pull", env.DORIS_IMAGE], check=False, stream=True, timeout=3600)
            if pull.returncode != 0:
                self._failure("Doris image pull failed",
                              "Check network or proxy access to Docker Hub, then rerun this cell.", pull.stdout)
                raise EnvironmentNotReady("the Doris image could not be pulled.")
            started = run([
                "docker", "run", "-d", "--name", env.DORIS_CONTAINER,
                "--network", env.DORIS_NETWORK,
                "-e", f"BE_HTTP_PORT={env.BE_HTTP_PORT}",
                "-e", f"BE_CONFIG_EXTRA=webserver_port = {env.BE_HTTP_PORT}",
                "-p", f"127.0.0.1:{env.QUERY_PORT}:9030",
                "-p", f"127.0.0.1:{env.HTTP_PORT}:8030",
                "-p", f"127.0.0.1:{env.BE_HTTP_PORT}:{env.BE_HTTP_PORT}",
                "-v", f"{env.FE_VOLUME}:/opt/apache-doris/fe/doris-meta",
                "-v", f"{env.BE_VOLUME}:/opt/apache-doris/be/storage",
                env.DORIS_IMAGE,
            ], check=False, stream=True)
            if started.returncode != 0:
                self._failure("The Doris container did not start",
                              "Read the Docker output, correct the conflict, and rerun this cell.", started.stdout)
                raise EnvironmentNotReady("the Doris container did not start.")
        elif not existing.get("State", {}).get("Running"):
            run(["docker", "start", env.DORIS_CONTAINER], show=True)
        else:
            card(f"Reusing the running container {env.DORIS_CONTAINER}", "ok")
        try:
            wait_for_health(env.DORIS_CONTAINER, timeout_seconds=300)
        except (RuntimeError, TimeoutError) as error:
            self._failure("Doris did not become healthy", str(error))
            raise EnvironmentNotReady("Doris did not become healthy.") from error

        progress_step(5, steps, "Connect to Doris and check the FE and BE")
        self.connection = None
        nodes = [
            {"node": node, "host": row.get("Host"), "alive": row.get("Alive"), "version": row.get("Version")}
            for node, statement in (("FE", "SHOW FRONTENDS"), ("BE", "SHOW BACKENDS"))
            for row in self.query(statement).to_dict("records")
        ]
        show_frame("Doris nodes (SHOW FRONTENDS, SHOW BACKENDS)", pd.DataFrame(nodes))
        card(
            f"Doris is running in {env.DORIS_CONTAINER}: 127.0.0.1:{env.QUERY_PORT} for MySQL clients, "
            f"http://127.0.0.1:{env.HTTP_PORT} for the FE, and http://127.0.0.1:{env.BE_HTTP_PORT} for the BE.",
            "ok", "The sandbox is ready",
        )

    # ------------------------------------------------------------------- data

    def _table_ddl(self) -> str:
        columns = ",\n".join(
            f'    {column["name"]} {column["type"]} NOT NULL'
            + (' DEFAULT "0.00"' if column["name"] == "revenue" else "")
            + f' COMMENT "{column["comment"]}"'
            for column in self.dataset["columns"]
        )
        return (
            f"CREATE TABLE IF NOT EXISTS {env.DATABASE}.{env.TABLE} (\n{columns}\n)\n"
            "DUPLICATE KEY(event_time, event_id)\n"
            f'COMMENT "{self.dataset["comment"]}"\n'
            "DISTRIBUTED BY HASH(event_id) BUCKETS 1\n"
            'PROPERTIES ("replication_num" = "1")'
        )

    def _csv_rows(self) -> list[list[str]]:
        path = DATASET_FILE.with_name(self.dataset["file"])
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            header = next(reader)
            expected = [column["name"] for column in self.dataset["columns"]]
            if header != expected:
                raise ValueError(f"{path.name} has columns {header}; expected {expected}.")
            return list(reader)

    @staticmethod
    def _values(row: Sequence[str]) -> str:
        event_time, event_id, user_id, event_type, region, product_id, revenue = row
        return (f"('{event_time}', {int(event_id)}, {int(user_id)}, '{event_type}', '{region}', "
                f"{int(product_id)}, {Decimal(revenue)})")

    def _table_summary(self) -> dict:
        frame = self.query(f"""
SELECT COUNT(*) AS row_count,
       MIN(event_time) AS min_event_time,
       MAX(event_time) AS max_event_time,
       COUNT(DISTINCT user_id) AS distinct_users,
       SUM(revenue) AS total_revenue,
       SUM(CASE WHEN event_type = 'view' THEN 1 ELSE 0 END) AS views,
       SUM(CASE WHEN event_type = 'cart' THEN 1 ELSE 0 END) AS carts,
       SUM(CASE WHEN event_type = 'purchase' THEN 1 ELSE 0 END) AS purchases
FROM {env.DATABASE}.{env.TABLE}""")
        return frame.iloc[0].to_dict()

    def _matches_dataset(self, summary: Mapping[str, Any]) -> list[tuple[str, str, str]]:
        spec = self.dataset
        checks = [
            ("rows", spec["row_count"], summary["row_count"]),
            ("first event", spec["min_event_time"], summary["min_event_time"]),
            ("last event", spec["max_event_time"], summary["max_event_time"]),
            ("distinct shoppers", spec["distinct_users"], summary["distinct_users"]),
            ("total revenue", spec["total_revenue"], summary["total_revenue"]),
            ("view events", spec["event_counts"]["view"], summary["views"]),
            ("cart events", spec["event_counts"]["cart"], summary["carts"]),
            ("purchase events", spec["event_counts"]["purchase"], summary["purchases"]),
        ]
        return [(name, str(expected), str(actual)) for name, expected, actual in checks]

    def load_dataset(self, *, statistics_timeout_seconds: int = 180) -> None:
        """Create the course table, load datasets/events.csv once, and check the result."""
        self.sql(f"CREATE DATABASE IF NOT EXISTS {env.DATABASE}", title="Create the course database")
        self.sql(self._table_ddl(), title="Create the events table")
        rows = self._csv_rows()
        summary = self._table_summary()
        if all(expected == actual for _, expected, actual in self._matches_dataset(summary)):
            card(f"{env.DATABASE}.{env.TABLE} already holds the {len(rows):,} course events; nothing to load.",
                 "ok", "Reusing the loaded data")
        else:
            self.sql(f"TRUNCATE TABLE {env.DATABASE}.{env.TABLE}", title="Empty the table before loading")
            show_sql(
                f"Insert {len(rows):,} rows from datasets/{self.dataset['file']} in batches of {INSERT_BATCH_ROWS:,}",
                f"INSERT INTO {env.DATABASE}.{env.TABLE} VALUES\n"
                + ",\n".join(self._values(row) for row in rows[:3]) + ",\n...",
            )
            started = time.perf_counter()
            with self._admin().cursor() as cursor:
                for first in range(0, len(rows), INSERT_BATCH_ROWS):
                    batch = rows[first:first + INSERT_BATCH_ROWS]
                    cursor.execute(f"INSERT INTO {env.DATABASE}.{env.TABLE} VALUES "
                                   + ",".join(self._values(row) for row in batch))
            card(f"Inserted {len(rows):,} rows in {time.perf_counter() - started:.1f} seconds.", "ok",
                 "Loaded the course events")
            summary = self._table_summary()
        checks = self._matches_dataset(summary)
        show_frame("The loaded table compared with datasets/events.yaml",
                   pd.DataFrame(checks, columns=["check", "expected", "in Doris"]))
        if any(expected != actual for _, expected, actual in checks):
            self._failure("The loaded data does not match the course dataset",
                          "Rerun this cell. If the numbers still differ, the CSV file was changed.")
            raise EnvironmentNotReady("the loaded data does not match datasets/events.yaml.")
        self._wait_for_table_statistics(self.dataset["row_count"], statistics_timeout_seconds)

    def _wait_for_table_statistics(self, expected_rows: int, timeout_seconds: int) -> None:
        statement = (
            "SELECT TABLE_ROWS FROM information_schema.tables "
            f"WHERE TABLE_SCHEMA = '{env.DATABASE}' AND TABLE_NAME = '{env.TABLE}'"
        )
        show_sql("Wait for the table statistics that metadata tools report", statement)
        deadline = time.monotonic() + timeout_seconds
        reported = None
        while True:
            value = self.query(statement).iloc[0, 0]
            reported = int(value) if value is not None else 0
            if reported == expected_rows:
                card(f"information_schema.tables reports {reported:,} rows for {env.DATABASE}.{env.TABLE}.",
                     "ok", "Table statistics are up to date")
                return
            if time.monotonic() > deadline:
                break
            print(f"TABLE_ROWS = {reported:,}; Doris refreshes it about once a minute. Waiting...", flush=True)
            time.sleep(10)
        card(f"TABLE_ROWS still reports {reported:,}. The data is loaded; metadata tools will report the new "
             "count after the next refresh.", "info", "Table statistics are not refreshed yet")

    # -------------------------------------------------------- MCP account

    def env_value(self, name: str) -> str:
        """Return one value from the launcher's .env.mcp.local file."""
        values = read_env_file(ENV_FILE)
        if name not in values:
            self._failure(f"{ENV_FILE.name} has no {name}",
                          "Run lab.create_mcp_account() to write the file, then rerun this cell.")
            raise EnvironmentNotReady(f"{ENV_FILE.name} has no {name}.")
        return values[name]

    def update_env_file(self, **values: str) -> None:
        """Change values in .env.mcp.local, keeping the file readable only by you."""
        if not ENV_FILE.exists():
            self._failure(f"{ENV_FILE.name} does not exist",
                          "Run lab.create_mcp_account() first, then rerun this cell.")
            raise EnvironmentNotReady(f"{ENV_FILE.name} does not exist.")
        text = render_env_file(ENV_FILE.read_text(encoding="utf-8"), values)
        write_private_file(ENV_FILE, text)
        names = ", ".join(sorted(values))
        card(f"Updated {names} in {ENV_FILE}.", "ok", "Environment file changed")

    def create_mcp_account(self) -> None:
        """Create mcp_reader with SELECT on the course database and write .env.mcp.local."""
        existing = read_env_file(ENV_FILE).get("DORIS_PASSWORD", "")
        reuse = bool(existing) and not existing.startswith("<")
        password = existing if reuse else generate_password()
        account = f"'{env.MCP_USER}'@'%'"
        literal = password.replace("\\", "\\\\").replace("'", "\\'")
        statements = (
            f"CREATE USER IF NOT EXISTS {account} IDENTIFIED BY '{literal}'",
            f"ALTER USER {account} IDENTIFIED BY '{literal}'",
            f"GRANT SELECT_PRIV ON internal.{env.DATABASE}.* TO {account}",
        )
        show_sql("Create the read-only account (password hidden)",
                 ";\n".join(statement.replace(literal, MASK) for statement in statements) + ";")
        with self._admin().cursor() as cursor:
            for statement in statements:
                try:
                    cursor.execute(statement)
                except pymysql.MySQLError as error:
                    report_sql_error("Create the read-only account", statement.replace(literal, MASK), error,
                                     secrets=(password, literal))
                    raise
        self.sql(f"SHOW GRANTS FOR {account}", title="What mcp_reader may do")

        template = ENV_EXAMPLE.read_text(encoding="utf-8")
        write_private_file(ENV_FILE, render_env_file(template, env_file_values(password)))
        mode = oct(ENV_FILE.stat().st_mode & 0o777)
        show_log(f"{ENV_FILE.name} (mode {mode[2:]}, password hidden)",
                 masked_env_text(ENV_FILE.read_text(encoding="utf-8")), opened=True)
        ignored = subprocess.run(["git", "check-ignore", "-q", str(ENV_FILE)], cwd=MODULE_DIR,
                                 capture_output=True).returncode == 0 if shutil.which("git") else None
        if ignored is False:
            card(f"Git does not ignore {ENV_FILE.name} here. Do not commit it.", "fail", "Check .gitignore")
        source = "reused the password already in the file" if reuse else "generated a new password"
        card(f"Wrote {ENV_FILE} and {source}. Host configurations need only this path: {LAUNCHER}",
             "ok", "The MCP account and its environment file are ready")

    def check_mcp_account(self) -> None:
        """Show that mcp_reader can read the course table and cannot write or administer."""
        rows = []
        connection = self._reader_connection()
        probes = (
            ("read the course table", f"SELECT COUNT(*) AS row_count FROM {env.DATABASE}.{env.TABLE}", True),
            ("write to the course table",
             f"INSERT INTO {env.DATABASE}.{env.TABLE} SELECT * FROM {env.DATABASE}.{env.TABLE} WHERE 1 = 0", False),
            ("create a table",
             f"CREATE TABLE {env.DATABASE}.mcp_reader_probe (id INT) DISTRIBUTED BY HASH(id) BUCKETS 1 "
             "PROPERTIES ('replication_num' = '1')", False),
            ("read the Doris audit log", "SELECT query_id FROM __internal_schema.audit_log LIMIT 1", False),
        )
        unexpected = []
        try:
            for action, statement, allowed in probes:
                show_sql(f"As mcp_reader: {action}", statement)
                with connection.cursor() as cursor:
                    try:
                        cursor.execute(statement)
                        result = cursor.fetchall() if cursor.description else []
                        outcome = f"allowed: {_compact(result[0]) if result else 'no rows'}"
                        ok = allowed
                    except pymysql.MySQLError as error:
                        message = str(error.args[1]) if len(error.args) > 1 else str(error)
                        outcome = "denied: " + message.split("detailMessage =", 1)[-1].strip()
                        ok = not allowed
                rows.append({"action": action, "expected": "allowed" if allowed else "denied",
                             "result": outcome})
                if not ok:
                    unexpected.append(action)
        finally:
            connection.close()
        show_frame("What mcp_reader can do", pd.DataFrame(rows))
        if unexpected:
            self.query(f"DROP TABLE IF EXISTS {env.DATABASE}.mcp_reader_probe")
            self._failure("mcp_reader has the wrong privileges",
                          f"Unexpected result for: {', '.join(unexpected)}. Review its grants before a Host uses it.")
            raise EnvironmentNotReady("mcp_reader has the wrong privileges.")
        card("mcp_reader reads the course data and is denied writes, DDL, and the audit log.", "ok",
             "Least privilege confirmed")

    def check_reader_login(self) -> bool:
        """Log in to Doris as mcp_reader with the password in .env.mcp.local."""
        try:
            connection = self._reader_connection()
        except pymysql.MySQLError as error:
            message = str(error.args[1]) if len(error.args) > 1 else str(error)
            card(message, "fail", "Doris rejected the password in .env.mcp.local")
            return False
        connection.close()
        card(f"{env.MCP_USER} logged in to {env.HOST}:{env.QUERY_PORT} with the password in {ENV_FILE.name}.",
             "ok", "The password is correct")
        return True

    def reader_query(self, statement: str, *, title: str = "The same SQL, run directly as mcp_reader"):
        """Run one SELECT as mcp_reader and display the rows, to compare with an agent's answer."""
        connection = self._reader_connection()
        try:
            return sql(connection, statement, title=title, final=True,
                       secrets=(self.env_value("DORIS_PASSWORD"),))
        finally:
            connection.close()

    # ------------------------------------------------------- MCP launcher

    def _error_log_size(self) -> int:
        return SERVER_ERROR_LOG.stat().st_size if SERVER_ERROR_LOG.exists() else 0

    def _show_failure(self, session: HostSession, error_log_offset: int, title: str) -> None:
        details = [f"Client: {session.error}"]
        if session.stderr.strip():
            details.append("Launcher and Server standard error:\n" + session.stderr.strip())
        if SERVER_ERROR_LOG.exists():
            with SERVER_ERROR_LOG.open(encoding="utf-8", errors="replace") as handle:
                handle.seek(error_log_offset)
                new_errors = handle.read().strip()
            if new_errors:
                details.append(f"{SERVER_ERROR_LOG.relative_to(COURSE_DIR)}:\n{new_errors}")
        card("The Server exited or did not answer. A Host would show this Server as failed or disconnected.",
             "fail", title)
        show_log("What the launcher and the Server reported", "\n\n".join(details), opened=True)

    def check_launcher(self) -> HostSession:
        """Start the launcher the way a Host does and list the tools the Server offers."""
        show_sql("What a Host runs", f"{LAUNCHER}\n(working directory /, MCP over standard input and output)")
        offset = self._error_log_size()
        session = run_host_session(LAUNCHER)
        if not session.ok:
            self._show_failure(session, offset, "The launcher did not start a working Server")
            return session
        show_frame("The Server's answer to tools/list", pd.DataFrame({
            "tool": session.tools,
            "domain": ["yes" if name in DOMAINS else "no" for name in session.tools],
        }))
        if sorted(session.tools) == sorted(DOMAINS):
            card(f"{session.server} answered over MCP {session.protocol_version} with the eight Doris domain "
                 f"tools. Every Host that runs {LAUNCHER.name} by this path gets the same tools.",
                 "ok", "The launcher works")
        else:
            card(f"Expected the eight domain tools {', '.join(DOMAINS)}; check MCP_TOOL_EXPOSURE_MODE in "
                 f"{ENV_FILE.name}.", "fail", "Unexpected tool list")
        return session

    def host_configs(self) -> None:
        """Show each Host's configuration with this computer's launcher path filled in."""
        path = str(LAUNCHER)
        servers = {"doris": {"command": path, "args": []}}
        show_sql("Claude Desktop: claude_desktop_config.json (merge into mcpServers)",
                 json.dumps({"mcpServers": servers}, indent=2))
        show_sql("Cursor: .cursor/mcp.json in the project you open",
                 json.dumps({"mcpServers": servers}, indent=2))
        show_sql("VS Code: .vscode/mcp.json in the workspace you open",
                 json.dumps({"servers": {"doris": {"type": "stdio", "command": path, "args": []}}}, indent=2))
        show_sql("Codex CLI, IDE extension, and ChatGPT desktop app: run in a terminal",
                 f'codex mcp add doris -- "{path}"\ncodex mcp get doris')
        card("Each configuration holds only the launcher path; the password stays in .env.mcp.local.",
             "ok", "Host configurations for this computer")

    # ----------------------------------------------------- reference trace

    def _show_call(self, call: ToolCall) -> None:
        result = call.result
        row = {
            "tool": call.tool,
            "arguments": _compact(call.arguments),
            "mode": result.get("mode", ""),
            "manifest_version": result.get("manifest_version", ""),
            "seconds": f"{call.seconds:.2f}",
        }
        show_frame("Tool call", pd.DataFrame([row]))
        if result.get("mode") == "manifest":
            children = pd.DataFrame([
                {
                    "child": child.get("name"),
                    "callable": child.get("availability", {}).get("callable"),
                    "reason_code": child.get("availability", {}).get("reason_code"),
                }
                for child in result.get("children", [])
            ])
            show_frame(f"Children discovered in {call.tool}", children)
        elif result.get("mode") == "error":
            error = result.get("error", {})
            card(f"{error.get('code')}: {error.get('message')} "
                 f"(reason_code {error.get('details', {}).get('reason_code')})", "fail", "The Server rejected the call")
        else:
            self._show_result(result)
        show_log("Complete structured result", json.dumps(result, indent=2, ensure_ascii=False))

    def _show_result(self, result: Mapping[str, Any]) -> None:
        child = result.get("child_tool")
        payload = result.get("data", {})
        data = payload.get("data", {})
        evidence = {
            "status": payload.get("status"),
            "warnings": _compact(payload.get("warnings", [])),
            "source": result.get("metadata", {}).get("source"),
            "truncated": result.get("metadata", {}).get("truncated"),
        }
        if child == "get_table_context":
            columns = data.get("schema", {}).get("data", {}).get("columns", [])
            show_frame("Columns returned by get_table_context", pd.DataFrame([
                {"column": c.get("column_name"), "type": c.get("data_type"),
                 "nullable": c.get("is_nullable"), "key": c.get("key"),
                 "default": c.get("default_value"), "comment": c.get("comment")}
                for c in columns
            ]))
            show_frame("Sections", pd.DataFrame([
                {"section": name, "status": section.get("status"), "warnings": _compact(section.get("warnings", []))}
                for name, section in data.items()
            ]))
            basic = data.get("basic", {}).get("data", {})
            evidence.update({"basic.row_count": basic.get("row_count"),
                             "indexes": data.get("indexes", {}).get("data", {}).get("index_count")})
        elif child == "execute_query":
            show_frame("Rows returned by execute_query",
                       result_frame(data.get("rows", []), [c["name"] for c in data.get("columns", [])]))
            meta = payload.get("metadata", {})
            evidence.update({"operation": meta.get("operation"), "row_count": data.get("row_count"),
                             "max_rows": meta.get("limits", {}).get("max_rows")})
        elif child == "get_memory_stats":
            for node in data.get("nodes", []):
                metrics = node.get("metrics", {})
                show_frame(f"Memory values for {node.get('role', '').upper()} node {node.get('node_id')}",
                           pd.DataFrame([
                               {"metric": name, "meaning": meaning, "bytes": metrics.get(name),
                                "approximately": _gib(metrics.get(name))}
                               for name, meaning in MEMORY_METRICS if name in metrics
                           ]))
            evidence.update({"detail": data.get("detail"),
                             "invented_values": payload.get("metadata", {}).get("invented_values"),
                             "metric source": payload.get("metadata", {}).get("source")})
        show_frame("Evidence fields", pd.DataFrame([{"field": key, "value": str(value)}
                                                     for key, value in evidence.items()]))

    def reference_trace(self, weekly_sql: str) -> HostSession:
        """Run the three requests of the lesson through the launcher and show each call and result."""
        self.doris_clock_at_trace = str(self.query("SELECT NOW() AS now").iloc[0, 0])
        requests = (
            ("doris_catalog", "get_table_context", {"database": env.DATABASE, "table": env.TABLE}),
            ("doris_query", "execute_query", {"sql": weekly_sql.strip().rstrip(";")}),
            ("doris_cluster", "get_memory_stats", {}),
        )
        offset = self._error_log_size()
        session = run_host_session(LAUNCHER, requests)
        if not session.ok:
            self._show_failure(session, offset, "The reference trace stopped")
            return session
        titles = {
            "doris_catalog": "Step 1 · Ground the conversation in the table",
            "doris_query": "Step 2 · Run the bounded read-only aggregation",
            "doris_cluster": "Step 3 · Read one memory evidence path",
        }
        shown = set()
        for call in session.calls:
            if call.tool not in shown:
                card(f"Discovery with {{}}, then one child call to {call.tool}", "info", titles[call.tool])
                shown.add(call.tool)
            self._show_call(call)
        failed = [call.tool for call in session.calls if call.is_error]
        if failed:
            card(f"These calls returned an error: {', '.join(failed)}.", "fail", "Reference trace incomplete")
        else:
            card("Compare each call with the tool calls in your Host: the tool, the child, the arguments, "
                 "and the returned fields.", "ok", "Reference trace complete")
        return session

    # ------------------------------------------------------------- audit

    def server_audit_log(self, lines: int = 12) -> pd.DataFrame:
        """Show the last entries of the MCP Server's own audit log."""
        if not SERVER_AUDIT_LOG.exists():
            card(f"{SERVER_AUDIT_LOG} does not exist yet. Start the Server once with lab.check_launcher().",
                 "info", "No Server audit log yet")
            return pd.DataFrame()
        pattern = re.compile(r"^(\S+ \S+) \[AUDIT\] audit - (.*)$")
        rows = []
        for line in SERVER_AUDIT_LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]:
            match = pattern.match(line)
            if not match:
                continue
            fields = dict(item.split("=", 1) for item in match.group(2).split() if "=" in item)
            rows.append({
                "time (this computer)": match.group(1),
                "tool": fields.get("tool", ""),
                "status": fields.get("status", ""),
                "duration_ms": fields.get("duration_ms", ""),
                "argument names": fields.get("argument_names", "") or "(none)",
            })
        frame = pd.DataFrame(rows)
        show_frame(f"Last entries of {SERVER_AUDIT_LOG.relative_to(COURSE_DIR)}", frame)
        return frame

    def doris_audit_log(self, *, since: str | None = None, timeout_seconds: int = 150) -> pd.DataFrame:
        """Show the statements mcp_reader ran on the course data, from Doris's own audit table."""
        since = since or self.doris_clock_at_trace
        if since is None:
            since = str(self.query("SELECT NOW() - INTERVAL 30 MINUTE AS since").iloc[0, 0])
        statement = (
            "SELECT `time`, state, LEFT(REPLACE(stmt, '\\n', ' '), 160) AS stmt\n"
            "FROM __internal_schema.audit_log\n"
            f"WHERE `user` = '{env.MCP_USER}'\n"
            f"  AND `time` >= '{since}'\n"
            f"  AND stmt LIKE '%{env.DATABASE}%'\n"
            "ORDER BY `time`"
        )
        show_sql("As the administrator: what mcp_reader ran on the course data", statement)
        deadline = time.monotonic() + timeout_seconds
        while True:
            frame = self.query(statement)
            if any("event_type" in str(value) for value in frame.get("stmt", [])):
                break
            if time.monotonic() > deadline:
                break
            print("Doris writes audit entries in batches, at most every 60 seconds. Waiting...", flush=True)
            time.sleep(10)
        show_frame("Doris audit entries for mcp_reader", frame, final=True)
        others = self.query(
            "SELECT COUNT(*) AS statements FROM __internal_schema.audit_log "
            f"WHERE `user` = '{env.MCP_USER}' AND `time` >= '{since}' AND stmt NOT LIKE '%{env.DATABASE}%'"
        ).iloc[0, 0]
        card(f"mcp_reader also ran {int(others):,} statements that do not name {env.DATABASE}: the Server's "
             "connection checks and capability probes (SELECT 1, SHOW FRONTENDS, and similar).",
             "info", "Other statements in the same period")
        return frame

    # ------------------------------------------------------------ cleanup

    def stop(self) -> None:
        """Stop the sandbox container and keep its data."""
        if container_inspect(env.DORIS_CONTAINER) is None:
            card(f"There is no {env.DORIS_CONTAINER} container.", "skip", "Nothing to stop")
            return
        run(["docker", "stop", env.DORIS_CONTAINER], show=True)
        self.connection = None
        card(f"{env.DORIS_CONTAINER} is stopped; its volumes keep the data. Run lab.start() to continue. "
             "A Host that starts the launcher meanwhile reports the Server as failed.", "ok", "Sandbox stopped")

    def start(self) -> None:
        """Start the stopped sandbox again with the same data."""
        labkit_docker.start_container(env.DORIS_CONTAINER,
                                      missing_hint="Run lab.prepare_environment() to create it.")
        self.connection = None
        card(f"{env.DORIS_CONTAINER} is running with its earlier data.", "ok", "Sandbox started")

    def drop_mcp_account(self) -> None:
        """Remove mcp_reader from Doris; Hosts that still run the launcher can no longer connect."""
        self.sql(f"DROP USER IF EXISTS '{env.MCP_USER}'@'%'", title="Remove the read-only account")

    def teardown(self) -> None:
        """Remove the course's containers, volumes, and network, and the files Lab 1 wrote.

        That includes Module 2's model server and its downloaded model file, when
        they exist: the server is on the sandbox's network.
        """
        removed = []
        for container in (env.LLM_CONTAINER, env.DORIS_CONTAINER):
            if container_inspect(container) is not None:
                run(["docker", "rm", "-f", container], show=True)
                removed.append(f"container {container}")
        for volume in (env.FE_VOLUME, env.BE_VOLUME, env.LLM_VOLUME):
            if labkit_docker.docker_exists("volume", volume):
                run(["docker", "volume", "rm", volume], show=True)
                removed.append(f"volume {volume}")
        if labkit_docker.docker_exists("network", env.DORIS_NETWORK):
            run(["docker", "network", "rm", env.DORIS_NETWORK], show=True)
            removed.append(f"network {env.DORIS_NETWORK}")
        if ENV_FILE.exists():
            ENV_FILE.unlink()
            removed.append(str(ENV_FILE.relative_to(COURSE_DIR)))
        if LOG_DIR.exists():
            shutil.rmtree(LOG_DIR)
            removed.append(str(LOG_DIR.relative_to(COURSE_DIR)) + "/")
        self.connection = None
        message = ("Removed " + ", ".join(removed) + ".") if removed else "Nothing was left to remove."
        if not self.uses_sandbox:
            message += (f" Your own Doris still has the {env.DATABASE} database, {env.MCP_USER}, and, after "
                        f"Module 2, the AI Resource {env.AI_RESOURCE}; run lab.drop_mcp_account(), "
                        f"DROP RESOURCE IF EXISTS {env.AI_RESOURCE}, and DROP DATABASE {env.DATABASE} if you "
                        "no longer need them.")
        card(message + " Remove the doris entry from each Host you configured (see Clean up in the lesson).",
             "ok", "Environment removed")


DorisLab = AiIntegrationsLab
