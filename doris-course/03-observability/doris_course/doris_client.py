from __future__ import annotations

import html
import json
import platform
import re
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd
import pymysql
from IPython.display import HTML, display


LAB_DIR = Path(__file__).resolve().parent.parent


def install_styles() -> None:
    display(HTML("""
    <style>
      .doris-status {border:1px solid #d9dee5;border-left:4px solid #6b7280;border-radius:4px;
        background:#f8fafc;padding:14px 16px;margin:8px 0 12px;color:#18212f}
      .doris-status.running {border-left-color:#d97706;background:#fffbeb}
      .doris-status.success {border-left-color:#16803c;background:#f0fdf4}
      .doris-status.failure {border-left-color:#c62828;background:#fff5f5}
      .doris-status.skip {border-left-color:#64748b;background:#f8fafc}
      .doris-status-title {font-size:16px;font-weight:650;margin-bottom:7px}
      .doris-meta {display:flex;flex-wrap:wrap;gap:7px}
      .doris-chip {display:inline-block;border:1px solid #cbd5e1;border-radius:4px;background:#fff;
        padding:3px 8px;font-size:12px;color:#334155}
      .doris-workflow {max-width:920px;border:1px solid #d9dee5;border-radius:6px;
        background:#fff;padding:14px 16px;margin:8px 0 12px}
      .doris-workflow-head {display:flex;justify-content:space-between;gap:12px;
        color:#18212f;font-size:15px;font-weight:700;margin-bottom:10px}
      .doris-workflow-list {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px 12px}
      .doris-workflow-item {display:flex;align-items:flex-start;gap:8px;border:1px solid #e2e8f0;
        border-radius:4px;background:#f8fafc;padding:8px 10px;color:#64748b;min-height:44px}
      .doris-workflow-item.running {border-color:#f59e0b;background:#fffbeb;color:#92400e}
      .doris-workflow-item.success {border-color:#86efac;background:#f0fdf4;color:#166534}
      .doris-workflow-item.failure {border-color:#fca5a5;background:#fff5f5;color:#991b1b}
      .doris-workflow-marker {display:inline-flex;align-items:center;justify-content:center;flex:0 0 22px;
        width:22px;height:22px;border-radius:999px;background:#e2e8f0;color:#475569;font-size:11px;font-weight:750}
      .doris-workflow-item.running .doris-workflow-marker {background:#f59e0b;color:#fff}
      .doris-workflow-item.success .doris-workflow-marker {background:#16803c;color:#fff}
      .doris-workflow-item.failure .doris-workflow-marker {background:#c62828;color:#fff}
      .doris-workflow-label {font-size:12px;line-height:1.35;font-weight:650}
      .doris-workflow-detail {color:#64748b;font-size:11px;line-height:1.35;margin-top:2px;
        overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:360px}
      .doris-progress-track {height:6px;border-radius:999px;background:#e2e8f0;overflow:hidden}
      .doris-progress-fill {height:100%;border-radius:999px;background:#0f766e}
      .doris-code {margin:8px 0 16px;max-width:920px}
      .doris-code-title {font-size:14px;font-weight:650;margin:0 0 6px;color:#18212f}
      .doris-code pre {max-height:440px;overflow:auto;white-space:pre;border:1px solid #d9dee5;
        border-radius:4px;background:#f8fafc;color:#18212f;padding:12px;font-size:12px;line-height:1.5}
      details.doris-log {margin:4px 0 16px;color:#475569}
      details.doris-log summary {cursor:pointer;font-size:12px;user-select:none}
      details.doris-log pre {max-height:360px;overflow:auto;white-space:pre-wrap;border:1px solid #d9dee5;
        border-radius:4px;background:#111827;color:#e5e7eb;padding:12px;font-size:11px;line-height:1.45}
      .doris-result {margin:10px 0 18px}
      .doris-result-final {border-left:3px solid #0f766e;background:#f0fdfa;padding:10px 12px 2px;max-width:920px}
      .doris-result-title {font-size:14px;font-weight:650;margin:0 0 6px;color:#18212f}
      .doris-result-count {color:#64748b;font-size:12px;font-weight:400;margin-left:6px}
      .doris-result-table-wrap {overflow-x:auto}
      table.doris-table {border-collapse:collapse;width:auto;min-width:420px;font-size:13px}
      table.doris-table th {background:#eef2f6;border:1px solid #cbd5e1;color:#1f2937;
        padding:7px 10px;text-align:left}
      table.doris-table td {border:1px solid #d9dee5;padding:7px 10px}
      table.doris-table tbody tr:nth-child(even) {background:#f8fafc}
      @media (max-width:700px) {.doris-workflow-list{grid-template-columns:1fr}}
    </style>
    """))


def card(message: str, kind: str = "info", title: str | None = None) -> None:
    status_kind = {"ok": "success", "info": "running", "fail": "failure", "skip": "skip"}.get(kind, kind)
    status_title = title or message
    chips = [] if title is None else [message]
    chip_html = "".join(f'<span class="doris-chip">{html.escape(str(chip))}</span>' for chip in chips)
    display(HTML(
        f'<div class="doris-status {status_kind}">'
        f'<div class="doris-status-title">{html.escape(str(status_title))}</div>'
        f'<div class="doris-meta">{chip_html}</div></div>'
    ))


def show_log(title: str, output: str, *, opened: bool = False) -> None:
    open_attribute = " open" if opened else ""
    display(HTML(
        f'<details class="doris-log"{open_attribute}><summary>{html.escape(title)}</summary>'
        f'<pre>{html.escape(output or "(no output)")}</pre></details>'
    ))


def show_sql(title: str, statement: str) -> None:
    display(HTML(
        '<div class="doris-code">'
        f'<div class="doris-code-title">{html.escape(title)}</div>'
        f'<pre>{html.escape(statement.strip())}</pre></div>'
    ))


def show_frame(title: str, frame: pd.DataFrame, *, final: bool = False) -> None:
    headings = "".join(f"<th>{html.escape(str(column))}</th>" for column in frame.columns)
    body_rows = []
    for row in frame.itertuples(index=False, name=None):
        cells = "".join(
            f"<td>{html.escape('NULL' if value is None else str(value))}</td>"
            for value in row
        )
        body_rows.append(f"<tr>{cells}</tr>")
    final_class = " doris-result-final" if final else ""
    display(HTML(
        f'<div class="doris-result{final_class}">'
        f'<div class="doris-result-title">{html.escape(title)} '
        f'<span class="doris-result-count">{len(frame):,} row(s)</span></div>'
        f'<div class="doris-result-table-wrap"><table class="doris-table">'
        f'<thead><tr>{headings}</tr></thead><tbody>{"".join(body_rows)}</tbody>'
        '</table></div></div>'
    ))


def run(
    command: Sequence[str],
    *,
    check: bool = True,
    timeout: int | None = None,
    show: bool = False,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [str(part) for part in command]
    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
        timeout=timeout,
        cwd=cwd,
    )
    combined = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
    if show:
        show_log("$ " + " ".join(command), combined)
    if check and result.returncode != 0:
        show_log("Command failed", combined)
        raise RuntimeError(f"Command failed with exit code {result.returncode}: {' '.join(command)}")
    return result


def docker_exists(kind: str, name: str) -> bool:
    return run(["docker", kind, "inspect", name], check=False).returncode == 0


def docker_preflight() -> tuple[bool, str]:
    """Return a learner-readable Docker readiness result without raising."""
    if shutil.which("docker") is None:
        return False, "Docker CLI was not found in PATH."
    result = run(
        ["docker", "version", "--format", "client={{.Client.Version}} server={{.Server.Version}}"],
        check=False,
    )
    output = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
    return result.returncode == 0, output


def container_inspect(name: str) -> dict | None:
    result = run(["docker", "container", "inspect", name], check=False)
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)[0]


def wait_for_port(host: str, port: int, timeout_seconds: int = 60) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        with socket.socket() as sock:
            sock.settimeout(1)
            if sock.connect_ex((host, port)) == 0:
                return
        time.sleep(1)
    raise TimeoutError(f"Timed out waiting for {host}:{port}")


def wait_for_health(name: str, timeout_seconds: int = 300, *, report: bool = True) -> None:
    deadline = time.monotonic() + timeout_seconds
    last = "unknown"
    reported = None
    while time.monotonic() < deadline:
        data = container_inspect(name)
        if data is None:
            raise RuntimeError(f"Container {name} disappeared")
        state = data.get("State", {})
        last = state.get("Health", {}).get("Status", "no-healthcheck")
        if last != reported and report:
            elapsed = int(timeout_seconds - max(0, deadline - time.monotonic()))
            print(f"[{name}] container={state.get('Status')} health={last} elapsed={elapsed}s", flush=True)
            reported = last
        if last == "healthy":
            if report:
                card(f"{name} is healthy", "ok")
            return
        if last == "unhealthy" or state.get("Status") in {"dead", "exited"}:
            logs = run(["docker", "logs", "--tail", "200", name], check=False)
            show_log(f"{name} logs", logs.stdout + logs.stderr)
            raise RuntimeError(f"{name} entered state={state.get('Status')}, health={last}")
        time.sleep(2)
    logs = run(["docker", "logs", "--tail", "200", name], check=False)
    show_log(f"{name} logs", logs.stdout + logs.stderr)
    raise TimeoutError(f"{name} did not become healthy within {timeout_seconds}s (last={last})")


def connect_doris(
    host: str = "127.0.0.1",
    port: int = 9030,
    *,
    user: str = "root",
    password: str = "",
):
    wait_for_port(host, port)
    return pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=5,
        cursorclass=pymysql.cursors.DictCursor,
    )


def sql(
    connection,
    statement: str,
    *,
    title: str | None = None,
    show_statement: bool = True,
    final: bool = False,
):
    clean = statement.strip().rstrip(";")
    if show_statement:
        show_sql(title or "SQL", clean)
    with connection.cursor() as cursor:
        cursor.execute(clean)
        rows = cursor.fetchall() if cursor.description else []
        columns = (
            [column[0] for column in cursor.description]
            if cursor.description
            else []
        )
        affected = cursor.rowcount
    if columns:
        frame = pd.DataFrame(rows, columns=columns)
        show_frame(title or "Query result", frame, final=final)
        return frame
    if not final:
        card(f"Statement completed. Affected rows: {max(affected, 0):,}", "ok")
    return affected


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
                self.connection = connect_doris()
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
        with connection.cursor() as cursor:
            cursor.execute(statement.strip().rstrip(";"))
            if cursor.description is None:
                raise ValueError("query() requires a statement that returns rows.")
            rows = cursor.fetchall()
            columns = [column[0] for column in cursor.description]
        return pd.DataFrame(rows, columns=columns)

    def connect(
        self,
        *,
        container: str = DORIS_CONTAINER,
        host: str = "127.0.0.1",
        port: int = 9030,
    ):
        wait_for_health(container, timeout_seconds=300, report=False)
        self.DORIS_CONTAINER = container
        self.connection = connect_doris(host=host, port=port)
        return self.connection

    def shell(self, script: str, *, title: str) -> subprocess.CompletedProcess[str]:
        """Run learner-visible Bash from a notebook cell."""
        markers = {
            int(number): label
            for number, _total, label in re.findall(
                r'echo\s+"\[(\d+)/(\d+)\]\s+([^"\n]+)"',
                script,
            )
        }
        if markers:
            return self._workflow_shell(script, title=title, steps=markers)

        card("Command in progress", "info", title)
        started_at = time.perf_counter()
        process = subprocess.Popen(
            ["/bin/bash", "-lc", script.strip()],
            cwd=self.lab_dir,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
        )
        lines: list[str] = []
        assert process.stdout is not None
        for line in process.stdout:
            lines.append(line)
            print(line, end="", flush=True)
        process.stdout.close()
        return_code = process.wait()
        elapsed = time.perf_counter() - started_at
        output = "".join(lines)
        result = subprocess.CompletedProcess(
            ["/bin/bash", "-lc", script.strip()],
            return_code,
            output,
            "",
        )
        if return_code != 0:
            self._failure(
                f"Failed: {title}",
                f"Bash exited with status {return_code} after {elapsed:.1f} seconds.",
                output,
            )
            raise RuntimeError(f"{title} failed with exit status {return_code}.")
        card(f"Completed in {elapsed:.1f} seconds", "ok", f"Passed: {title}")
        if output:
            show_log("View full command log", output)
        return result

    def _workflow_html(
        self,
        title: str,
        steps: Mapping[int, str],
        current: int,
        state: str,
        detail: str,
    ) -> HTML:
        total = max(steps)
        percent = max(0, min(100, round(current / total * 100)))
        items = []
        for number in range(1, total + 1):
            if number < current:
                item_state, marker = "success", "OK"
                item_detail = "Complete"
            elif number == current:
                item_state, marker = state, str(number)
                item_detail = detail
            else:
                item_state, marker, item_detail = "", str(number), "Waiting"
            items.append(
                f'<div class="doris-workflow-item {item_state}">'
                f'<span class="doris-workflow-marker">{marker}</span>'
                '<div style="min-width:0">'
                f'<div class="doris-workflow-label">{html.escape(steps[number])}</div>'
                f'<div class="doris-workflow-detail">{html.escape(item_detail)}</div>'
                '</div></div>'
            )
        headline = "Completed" if state == "success" else (
            "Failed" if state == "failure" else f"Step {current} of {total}"
        )
        bar_color = "#c62828" if state == "failure" else "#0f766e"
        return HTML(
            '<div class="doris-workflow">'
            f'<div class="doris-workflow-head"><span>{html.escape(title)}</span>'
            f'<span>{headline}</span></div>'
            '<div class="doris-progress-track" style="margin-bottom:12px">'
            f'<div class="doris-progress-fill" style="width:{percent}%;background:{bar_color}"></div>'
            f'</div><div class="doris-workflow-list">{"".join(items)}</div></div>'
        )

    def _workflow_shell(
        self,
        script: str,
        *,
        title: str,
        steps: Mapping[int, str],
    ) -> subprocess.CompletedProcess[str]:
        current = 1
        detail = "Starting..."
        handle = display(
            self._workflow_html(title, steps, current, "running", detail),
            display_id=True,
        )
        started_at = time.perf_counter()
        process = subprocess.Popen(
            ["/bin/bash", "-lc", script.strip()],
            cwd=self.lab_dir,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
        )
        lines: list[str] = []
        last_update = 0.0
        assert process.stdout is not None
        for line in process.stdout:
            lines.append(line)
            clean = line.strip()
            step_match = re.match(r"^\[(\d+)/(\d+)\]\s+(.+)$", clean)
            if step_match:
                current = int(step_match.group(1))
                detail = step_match.group(3)
            elif clean:
                detail = clean
            now = time.monotonic()
            if step_match or now - last_update >= 0.35:
                handle.update(self._workflow_html(title, steps, current, "running", detail))
                last_update = now

        process.stdout.close()
        return_code = process.wait()
        elapsed = time.perf_counter() - started_at
        output = "".join(lines)
        result = subprocess.CompletedProcess(
            ["/bin/bash", "-lc", script.strip()],
            return_code,
            output,
            "",
        )
        if return_code != 0:
            handle.update(self._workflow_html(title, steps, current, "failure", detail))
            show_log("View diagnostic log", output, opened=True)
            raise RuntimeError(f"{title} failed with exit status {return_code}.")

        handle.update(self._workflow_html(title, steps, max(steps), "success", ""))
        card(f"Completed in {elapsed:.1f} seconds", "ok", f"Passed: {title}")
        if output:
            show_log("View full command log", output)
        return result

    def ensure_docker_ready(self, *, timeout_seconds: int = 180) -> None:
        """Ensure the Docker daemon is reachable, starting Docker Desktop on macOS."""
        if shutil.which("docker") is None:
            raise RuntimeError("Docker CLI was not found in PATH.")

        ready, output = docker_preflight()
        if ready:
            card("Docker daemon is already running", "ok")
            return

        if platform.system() != "Darwin":
            raise RuntimeError(
                "Docker Engine is not running. Start it on this host, then rerun this cell. "
                f"Docker reported: {output or 'no diagnostic output'}"
            )

        launched = run(["open", "-a", "Docker"], check=False)
        if launched.returncode != 0:
            raise RuntimeError(
                "Docker Desktop could not be opened. Start it manually, then rerun this cell."
            )

        deadline = time.monotonic() + timeout_seconds
        last_output = output
        while time.monotonic() < deadline:
            ready, last_output = docker_preflight()
            if ready:
                card("Docker Desktop is running", "ok")
                return
            time.sleep(2)
        raise TimeoutError(
            f"Docker Desktop did not become ready within {timeout_seconds} seconds. "
            f"Last diagnostic: {last_output or 'no diagnostic output'}"
        )

    def start_container(
        self,
        container: str = DORIS_CONTAINER,
        *,
        wait_for_healthy: bool = True,
        timeout_seconds: int = 300,
    ) -> dict:
        """Start or reuse an existing course container."""
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", container):
            raise ValueError("container must be a simple Docker container name.")

        self.ensure_docker_ready()
        state = container_inspect(container)
        if state is None:
            raise RuntimeError(
                f"Container {container!r} does not exist. Run prepare_environment() first."
            )
        status = str(state.get("State", {}).get("Status", "unknown"))
        if status == "paused":
            run(["docker", "unpause", container], show=True)
        elif status not in {"running", "restarting"}:
            run(["docker", "start", container], show=True)
        else:
            card(f"Reusing {status} container {container}", "ok")
        if wait_for_healthy:
            wait_for_health(container, timeout_seconds=timeout_seconds)
        state = container_inspect(container)
        assert state is not None
        return state

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
