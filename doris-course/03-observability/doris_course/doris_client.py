from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Mapping

import pandas as pd
import pymysql

from doris_labkit.db import connect_doris, report_sql_error, sql
from doris_labkit.docker import (
    container_inspect,
    docker_exists,
    docker_preflight,
    run,
    wait_for_health,
    wait_for_port,
)
from doris_labkit import docker as labkit_docker
from doris_labkit.results import result_frame, show_frame
from doris_labkit.shell import run_shell
from doris_labkit.ui import card, install_styles, show_log, show_sql


LAB_DIR = Path(__file__).resolve().parent.parent


class ObservabilityLab:
    """Learner-facing facade for the DOG and Doris observability labs."""

    DORIS_IMAGE = "apache/doris:4.0.3-all-slim"
    DORIS_CONTAINER = "doris"
    DOG_NETWORK = "docker_aiobs-net"
    STACK_REPOSITORY = "https://github.com/ai-observe/ai-observe-stack.git"
    RUNTIME_DIRECTORY = ".runtime"
    STACK_DIRECTORY = "ai-observe-stack"
    DORIS_LOG_DIRECTORY = "doris-logs"
    DEMO_PORT = 8082

    def __init__(
        self,
        lab_dir: Path | None = None,
        *,
        ready_title: str = "Observability lab tools are ready",
        ready_message: str = "Run the environment cells in order, then use lab.sql(...) or lab.shell(...).",
    ) -> None:
        self.lab_dir = (lab_dir or LAB_DIR).resolve()
        self.connection = None
        self.stack_dir = self.lab_dir / self.RUNTIME_DIRECTORY / self.STACK_DIRECTORY
        self.doris_log_dir = self.lab_dir / self.RUNTIME_DIRECTORY / self.DORIS_LOG_DIRECTORY
        self.compose_override = self.lab_dir / "compose.doris-logs.yml"
        install_styles()
        card(ready_message, "ok", ready_title)

    def _failure(self, title: str, message: str, log: str = "") -> None:
        card(message, "fail", title)
        if log:
            show_log("Diagnostic details", log, opened=True)

    def _require_connection(self):
        if self.connection is None:
            try:
                self.connection = connect_doris(connect_timeout=5)
                try:
                    with self.connection.cursor() as cursor:
                        cursor.execute("USE otel")
                except pymysql.MySQLError:
                    pass
            except (OSError, pymysql.MySQLError) as exc:
                raise RuntimeError(
                    "No running Doris server is reachable on 127.0.0.1:9030. "
                    "Run the prepare-environment cell in Module 1, then retry."
                ) from exc
        return self.connection

    def sql(
        self,
        statement: str,
        *,
        title: str | None = None,
        final: bool = False,
    ):
        return sql(
            self._require_connection(),
            statement,
            title=title,
            show_statement=True,
            final=final,
        )

    def execute(self, statement: str, *, title: str | None = None) -> int:
        if title:
            show_sql(title, statement)
        return sql(
            self._require_connection(),
            statement,
            title=title,
            show_statement=False,
        )

    def query(self, statement: str) -> pd.DataFrame:
        connection = self._require_connection()
        clean = statement.strip().rstrip(";")
        with connection.cursor() as cursor:
            try:
                cursor.execute(clean)
                rows = cursor.fetchall() if cursor.description else []
            except pymysql.MySQLError as error:
                report_sql_error(None, clean, error)
                raise
            if cursor.description is None:
                raise ValueError("query() requires a statement that returns rows.")
            columns = [column[0] for column in cursor.description]
        if rows and isinstance(rows[0], Mapping):
            columns = list(rows[0])
        return result_frame(rows, columns)

    def connect(
        self,
        *,
        container: str = DORIS_CONTAINER,
        host: str = "127.0.0.1",
        port: int = 9030,
    ):
        wait_for_health(container, timeout_seconds=300, report=False)
        self.DORIS_CONTAINER = container
        self.connection = connect_doris(host=host, port=port, connect_timeout=5)
        return self.connection

    def shell(self, script: str, *, title: str) -> subprocess.CompletedProcess[str]:
        """Run learner-visible Bash from the course root with live progress."""
        return run_shell(script, title=title, cwd=self.lab_dir)

    def ensure_docker_ready(self, *, timeout_seconds: int = 180) -> None:
        """Ensure the Docker daemon is reachable, starting Docker Desktop on macOS."""
        labkit_docker.ensure_docker_ready(timeout_seconds=timeout_seconds)

    def start_container(
        self,
        container: str = DORIS_CONTAINER,
        *,
        wait_for_healthy: bool = True,
        timeout_seconds: int = 300,
    ) -> dict:
        """Start or reuse an existing course container."""
        return labkit_docker.start_container(
            container,
            wait_for_healthy=wait_for_healthy,
            timeout_seconds=timeout_seconds,
            missing_hint="Run prepare_environment() first.",
        )

    def prepare_environment(self) -> None:
        """Clone or update the pinned DOG stack and start Doris, Grafana, and OTel."""
        self.ensure_docker_ready()
        script = r"""
set -euo pipefail

COURSE_ROOT="$(pwd -P)"
STACK_DIR=".runtime/ai-observe-stack"
DORIS_LOG_ROOT="$COURSE_ROOT/.runtime/doris-logs"

echo "[1/5] Prepare the local runtime directory"
mkdir -p "$DORIS_LOG_ROOT/fe" "$DORIS_LOG_ROOT/be"

echo "[2/5] Clone or update the DOG stack"
if [ ! -d "$STACK_DIR/.git" ]; then
  git clone --depth 1 https://github.com/ai-observe/ai-observe-stack.git "$STACK_DIR"
else
  git -C "$STACK_DIR" pull --ff-only
fi

echo "[3/5] Start the DOG core services"
cd "$STACK_DIR/docker"
DORIS_IMAGE="apache/doris:4.0.3-all-slim" \
DORIS_LOG_ROOT="$DORIS_LOG_ROOT" \
docker compose \
  -f docker-compose.yaml \
  -f "$COURSE_ROOT/compose.doris-logs.yml" \
  up -d

echo "[4/5] Wait for the Doris container"
for attempt in $(seq 1 120); do
  if [ "$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' doris 2>/dev/null || true)" = "healthy" ]; then
    break
  fi
  if [ "$attempt" -eq 120 ]; then
    docker logs --tail 200 doris
    exit 1
  fi
  sleep 2
done

echo "[5/5] Show the running stack"
docker compose ps
"""
        self.shell(script, title="Prepare the DOG observability environment")
        self.connect()
        self.execute("CREATE DATABASE IF NOT EXISTS otel")
        self.execute("USE otel")
        self.sql(
            "SELECT VERSION() AS doris_version, CURRENT_USER() AS current_user",
            title="Doris connection",
        )
        self.sql("SELECT DATABASE() AS current_database", title="Current database")

    def start_demo(self) -> None:
        """Start the OpenTelemetry ecommerce demo on port 8082."""
        self.ensure_docker_ready()
        script = rf"""
set -euo pipefail

STACK_DIR=".runtime/ai-observe-stack"
if [ ! -d "$STACK_DIR/.git" ]; then
  echo "The DOG stack is not prepared. Run prepare_environment() first."
  exit 1
fi

cd "$STACK_DIR/doris-opentelemetry-demo"
ENVOY_PORT={self.DEMO_PORT} docker compose up -d
docker compose ps
"""
        self.shell(script, title="Start the OpenTelemetry demo")

    def show_containers(self) -> None:
        """Display the containers owned by the DOG observability stack."""
        self.shell(
            'docker ps --format "table {{.Names}}\\t{{.Image}}\\t{{.Status}}\\t{{.Ports}}"',
            title="DOG containers",
        )


DorisLab = ObservabilityLab

__all__ = [
    "DorisLab",
    "ObservabilityLab",
    "card",
    "connect_doris",
    "container_inspect",
    "docker_exists",
    "docker_preflight",
    "install_styles",
    "run",
    "show_frame",
    "show_log",
    "show_sql",
    "sql",
    "wait_for_health",
    "wait_for_port",
]
