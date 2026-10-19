from __future__ import annotations

import re
import shlex
import subprocess
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd
import pymysql

from doris_labkit.db import connect_doris, report_sql_error, sql
from doris_labkit.docker import (
    container_inspect,
    docker_exists,
    docker_preflight,
    port_in_use,
    run,
    wait_for_health,
    wait_for_port,
)
from doris_labkit import docker as labkit_docker
from doris_labkit.results import result_frame, show_frame
from doris_labkit.shell import run_shell
from doris_labkit.ui import card, install_styles, show_log, show_sql

from . import environment as env


LAB_DIR = Path(__file__).resolve().parent.parent

# Host ports published by each part of the environment: (port, variable, purpose).
CORE_PORTS = (
    (env.QUERY_PORT, "DORIS_OBS_QUERY_PORT", "Doris FE query port (MySQL protocol)"),
    (env.HTTP_PORT, "DORIS_OBS_HTTP_PORT", "Doris FE HTTP"),
    (env.BE_HTTP_PORT, "DORIS_OBS_BE_HTTP_PORT", "Doris BE HTTP"),
    (env.GRAFANA_PORT, "DORIS_OBS_GRAFANA_PORT", "Grafana"),
    (env.OTLP_GRPC_PORT, "DORIS_OBS_OTLP_GRPC_PORT", "Collector OTLP gRPC"),
    (env.OTLP_HTTP_PORT, "DORIS_OBS_OTLP_HTTP_PORT", "Collector OTLP HTTP"),
)
DEMO_PORTS = ((env.DEMO_PORT, "DORIS_OBS_DEMO_PORT", "Demo storefront"),)

# The override files replace upstream lists with the !override merge tag (Compose 2.24.4).
MIN_COMPOSE_VERSION = (2, 24, 4)

# Fetch only the pinned commit, and nothing when the checkout is already there.
CHECKOUT_STACK = r"""
if [ ! -d "$STACK_DIR/.git" ]; then
  git -c init.defaultBranch=main init --quiet "$STACK_DIR"
  git -C "$STACK_DIR" remote add origin "$STACK_REPOSITORY"
fi
if [ "$(git -C "$STACK_DIR" rev-parse --verify --quiet HEAD)" = "$STACK_COMMIT" ]; then
  echo "Reusing the DOG stack at commit $STACK_COMMIT"
else
  git -C "$STACK_DIR" fetch --depth 1 origin "$STACK_COMMIT"
  git -C "$STACK_DIR" -c advice.detachedHead=false checkout --force "$STACK_COMMIT"
fi
"""


class EnvironmentNotReady(RuntimeError):
    """A preparation step stopped; the card shown before raising says why and what to do."""

    def _render_traceback_(self) -> list[str]:
        return [f"Stopped: {self}"]


class ObservabilityLab:
    """Learner-facing facade for the DOG and Doris observability labs."""

    DORIS_IMAGE = env.DORIS_IMAGE
    DORIS_CONTAINER = env.DORIS_CONTAINER
    DOG_NETWORK = env.NETWORK
    STACK_REPOSITORY = env.STACK_REPOSITORY
    STACK_COMMIT = env.STACK_COMMIT
    RUNTIME_DIRECTORY = ".runtime"
    STACK_DIRECTORY = "ai-observe-stack"
    DORIS_LOG_DIRECTORY = "doris-logs"
    DEMO_PORT = env.DEMO_PORT

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
        install_styles()
        card(ready_message, "ok", ready_title)

    def _failure(self, title: str, message: str, log: str = "") -> None:
        card(message, "fail", title)
        if log:
            show_log("Diagnostic details", log, opened=True)

    def _require_connection(self):
        if self.connection is None:
            try:
                self.connection = connect_doris(port=env.QUERY_PORT, connect_timeout=5)
                try:
                    with self.connection.cursor() as cursor:
                        cursor.execute("USE otel")
                except pymysql.MySQLError:
                    pass
            except (OSError, pymysql.MySQLError) as exc:
                raise RuntimeError(
                    f"No running Doris server is reachable on 127.0.0.1:{env.QUERY_PORT}. "
                    "Run the prepare-environment cell in Module 1, then retry."
                ) from exc
        return self.connection

    @property
    def fe_http_url(self) -> str:
        """The FE HTTP address on this host, for REST requests such as Query Profile text."""
        return f"http://127.0.0.1:{env.HTTP_PORT}"

    @property
    def grafana_url(self) -> str:
        return f"http://127.0.0.1:{env.GRAFANA_PORT}"

    @property
    def otlp_http_url(self) -> str:
        """The DOG Collector's OTLP/HTTP receiver on this host."""
        return f"http://127.0.0.1:{env.OTLP_HTTP_PORT}"

    @property
    def demo_url(self) -> str:
        """The demo storefront on this host."""
        return f"http://127.0.0.1:{env.DEMO_PORT}"

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
        port: int = env.QUERY_PORT,
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

    def _compose_script(self, body: str) -> str:
        """Prefix ``body`` with the stack location and the course's two Compose commands."""
        header = f"""set -euo pipefail

COURSE_ROOT="$(pwd -P)"
STACK_DIR="$COURSE_ROOT/{self.RUNTIME_DIRECTORY}/{self.STACK_DIRECTORY}"
STACK_REPOSITORY={shlex.quote(env.STACK_REPOSITORY)}
STACK_COMMIT={env.STACK_COMMIT}
export DORIS_OBS_COURSE_ROOT="$COURSE_ROOT"

# The upstream Compose files with this course's overrides (environments/dog-stack/).
dog_compose() {{
  (cd "$STACK_DIR/docker" && docker compose -p {env.PROJECT} \\
    -f docker-compose.yaml -f "$COURSE_ROOT/environments/dog-stack/compose.dog.yml" "$@")
}}
demo_compose() {{
  local env_files=(--env-file .env)
  # Java workaround for recent Apple silicon (JDK-8345296), as in the demo's Makefile.
  if [ "$(uname -s)" = Darwin ] && [ "$(uname -m)" = arm64 ]; then
    env_files+=(--env-file .env.arm64)
  fi
  (cd "$STACK_DIR/doris-opentelemetry-demo" && docker compose -p {env.DEMO_PROJECT} "${{env_files[@]}}" \\
    -f docker-compose.yml -f "$COURSE_ROOT/environments/dog-stack/compose.demo.yml" "$@")
}}
"""
        return header + body

    def _check_compose_version(self) -> None:
        result = run(["docker", "compose", "version", "--short"], check=False)
        found = result.stdout.strip() if result.returncode == 0 else ""
        numbers = tuple(int(part) for part in re.findall(r"\d+", found)[:3])
        if numbers < MIN_COMPOSE_VERSION:
            required = ".".join(map(str, MIN_COMPOSE_VERSION))
            self._failure(
                "Docker Compose is too old",
                f"This course needs Docker Compose {required} or later; found {found or 'no Compose plugin'}. "
                "Update Docker Desktop or the Docker Compose plugin, then rerun this cell.",
            )
            raise EnvironmentNotReady(f"Docker Compose {required} or later is required.")

    def _check_ports(self, ports: Sequence[tuple[int, str, str]], containers: Sequence[str]) -> None:
        """Show the host ports a step publishes; stop when another program holds one."""
        published: set[int] = set()
        for name in containers:
            state = container_inspect(name)
            # A running course container may already publish the port.
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
                f"Another program is using: {', '.join(blocked)}. Stop it, or set the variable "
                "to a free port before starting Jupyter, then rerun this cell.",
            )
            raise EnvironmentNotReady("a required host port is in use.")

    def prepare_environment(self) -> None:
        """Check out the pinned DOG stack and start Doris, the OTel Collector, and Grafana."""
        self.ensure_docker_ready()
        self._check_compose_version()
        self._check_ports(CORE_PORTS, (env.DORIS_CONTAINER, env.COLLECTOR_CONTAINER, env.GRAFANA_CONTAINER))
        script = self._compose_script(r"""
echo "[1/4] Prepare the local runtime directory"
mkdir -p .runtime/doris-logs/fe .runtime/doris-logs/be

echo "[2/4] Check out the pinned DOG stack"
""" + CHECKOUT_STACK + r"""
echo "[3/4] Start the DOG core services"
dog_compose up -d

echo "[4/4] Show the running stack"
dog_compose ps
""")
        self.shell(script, title="Prepare the DOG observability environment")
        self.connect()
        wait_for_health(env.GRAFANA_CONTAINER, timeout_seconds=300, report=False)
        self.execute("CREATE DATABASE IF NOT EXISTS otel")
        self.execute("USE otel")
        nodes = [
            {"node": node, "host": row.get("Host"), "version": row.get("Version"), "alive": row.get("Alive")}
            for node, statement in (("FE", "SHOW FRONTENDS"), ("BE", "SHOW BACKENDS"))
            for row in self.query(statement).to_dict("records")
        ]
        show_frame("Doris nodes (SHOW FRONTENDS, SHOW BACKENDS)", pd.DataFrame(nodes))
        self.sql("SELECT DATABASE() AS current_database", title="Current database")
        card(
            f"Grafana: {self.grafana_url}/a/velodb-doris-app (user admin, password admin). "
            f"Doris: 127.0.0.1:{env.QUERY_PORT} for MySQL clients, {self.fe_http_url} for HTTP.",
            "ok",
            "The DOG stack is running",
        )

    def _dog_stack_running(self) -> bool:
        state = container_inspect(env.COLLECTOR_CONTAINER)
        return bool(
            state
            and state.get("State", {}).get("Running")
            and env.NETWORK in state.get("NetworkSettings", {}).get("Networks", {})
        )

    def start_demo(self) -> None:
        """Start the OpenTelemetry demo storefront, which sends its telemetry to the DOG Collector."""
        self.ensure_docker_ready()
        if not self._dog_stack_running():
            self._failure(
                "The DOG stack is not running",
                "The demo sends its telemetry to the DOG Collector. Run lab.prepare_environment() "
                "in Module 1 first, then rerun this cell.",
            )
            raise EnvironmentNotReady("the DOG stack is not running.")
        self._check_compose_version()
        self._check_ports(DEMO_PORTS, (env.DEMO_PROXY_CONTAINER,))
        script = self._compose_script(r"""
echo "[1/2] Start the demo services"
demo_compose up -d

echo "[2/2] Show the demo services"
demo_compose ps
""")
        self.shell(script, title="Start the OpenTelemetry demo")
        card(f"Open the storefront at {self.demo_url}", "ok", "The demo is running")

    def stop_demo(self) -> None:
        """Stop and remove the demo containers. The telemetry already in Doris stays."""
        # Compose finds a project's containers and networks by their labels, without the files.
        self.shell(f"docker compose -p {env.DEMO_PROJECT} down", title="Stop the OpenTelemetry demo")

    def teardown(self, *, keep_data: bool = False) -> None:
        """Remove every container and network of this course, and its volumes unless keep_data.

        With keep_data=True, prepare_environment() later starts Doris and Grafana
        again with the same data.
        """
        volumes = "" if keep_data else " --volumes"
        collectors = " ".join(env.MODULE2_COLLECTORS)
        # Compose finds each project's containers, networks, and volumes by their labels,
        # so this also works after .runtime/ was deleted. The demo Collector and the
        # Module 2 collectors are attached to the doris-obs network: remove them first.
        script = f"""set -euo pipefail

echo "[1/3] Remove the OpenTelemetry demo"
docker compose -p {env.DEMO_PROJECT} down

echo "[2/3] Remove the Module 2 collectors"
for name in {collectors}; do
  if docker container inspect "$name" >/dev/null 2>&1; then
    docker rm -f "$name"
  fi
done

echo "[3/3] Remove the DOG core services"
docker compose -p {env.PROJECT} down{volumes}
"""
        self.shell(script, title="Remove the observability environment")
        self.connection = None
        kept = "The Doris and Grafana volumes were kept." if keep_data else "Their volumes were removed too."
        card(
            f"Removed the course containers and networks. {kept} The upstream checkout and the "
            f"Doris logs stay in {self.RUNTIME_DIRECTORY}/; delete that directory if you no longer need them.",
            "ok",
            "Environment removed",
        )

    def show_containers(self) -> None:
        """Display the containers of this course: the DOG stack, the collectors, and the demo."""
        self.shell(
            f'docker ps -a --filter name={env.PROJECT} '
            '--format "table {{.Names}}\\t{{.Image}}\\t{{.Status}}\\t{{.Ports}}"',
            title="Course containers",
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
