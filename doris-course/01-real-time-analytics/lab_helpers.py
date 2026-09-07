from __future__ import annotations

import html
import base64
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import time
import urllib.request
import urllib.parse
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import pandas as pd
import pymysql
from IPython.display import HTML, Javascript, display


LAB_DIR = Path.cwd().resolve()


def install_styles() -> None:
    display(HTML("""
    <style>
      .doris-cover {max-width:960px;border-top:4px solid #0f766e;padding:22px 0 18px;margin:0 0 24px}
      .doris-cover-kicker {color:#0f766e;font-size:12px;font-weight:700;letter-spacing:1px;
        text-transform:uppercase;margin-bottom:8px}
      .doris-cover-title {color:#17212b;font-size:30px;line-height:1.2;font-weight:750;margin:0 0 8px}
      .doris-cover-lead {color:#475569;font-size:15px;line-height:1.7;max-width:780px;margin:0}
      .doris-cover-note {display:inline-block;border:1px solid #99f6e4;border-radius:4px;
        background:#f0fdfa;color:#115e59;padding:6px 10px;margin-top:14px;font-size:12px}
      .doris-callout {max-width:920px;border:1px solid #dbe4e8;border-left:3px solid #0f766e;
        border-radius:4px;background:#f8fbfb;color:#334155;padding:10px 12px;margin:14px 0}
      .doris-callout.warn {border-left-color:#d97706;background:#fffbeb}
      .doris-flow {display:flex;flex-wrap:wrap;align-items:stretch;gap:8px;max-width:960px;margin:16px 0 22px}
      .doris-flow-step {flex:1 1 145px;border:1px solid #dbe4e8;border-left:3px solid #0f766e;
        border-radius:4px;background:#f8fbfb;color:#334155;padding:10px 12px;font-size:13px;line-height:1.45}
      .doris-flow-step strong {color:#17212b;display:block;margin-bottom:2px}
      .doris-flow-arrow {align-self:center;color:#94a3b8;font-size:18px;line-height:1}
      .doris-progress {max-width:920px;margin:10px 0 14px}
      .doris-progress-head {display:flex;justify-content:space-between;gap:12px;
        color:#334155;font-size:13px;font-weight:650;margin-bottom:6px}
      .doris-progress-track {height:6px;border-radius:999px;background:#e2e8f0;overflow:hidden}
      .doris-progress-fill {height:100%;border-radius:999px;background:#0f766e}
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
      .doris-code {margin:8px 0 16px;max-width:920px}
      .doris-code-title {font-size:14px;font-weight:650;margin:0 0 6px;color:#18212f}
      .doris-code pre {max-height:440px;overflow:auto;white-space:pre;border:1px solid #d9dee5;
        border-radius:4px;background:#f8fafc;color:#18212f;padding:12px;font-size:12px;line-height:1.5}
      details.doris-log {margin:4px 0 16px;color:#475569}
      details.doris-log summary {cursor:pointer;font-size:12px;user-select:none}
      details.doris-log pre {max-height:360px;overflow:auto;white-space:pre-wrap;border:1px solid #d9dee5;
        border-radius:4px;background:#111827;color:#e5e7eb;padding:12px;font-size:11px;line-height:1.45}
      .doris-match {max-width:960px;border:1px solid #dbe4e8;border-radius:6px;background:#fff;
        color:#334155;padding:16px;margin:14px 0 20px}
      .doris-match-head {display:flex;align-items:flex-start;justify-content:space-between;gap:16px}
      .doris-match-title {color:#17212b;font-size:16px;font-weight:750;margin:0 0 4px}
      .doris-match-help {font-size:12px;line-height:1.55;margin:0;color:#64748b;max-width:720px}
      .doris-match-score {white-space:nowrap;border:1px solid #99f6e4;border-radius:999px;
        background:#f0fdfa;color:#115e59;padding:4px 9px;font-size:12px;font-weight:700}
      .doris-method-bank {display:flex;flex-wrap:wrap;gap:8px;border:1px dashed #94a3b8;
        border-radius:5px;background:#f8fafc;padding:11px;margin:14px 0}
      .doris-method {appearance:none;border:1px solid #0f766e;border-radius:4px;background:#fff;
        color:#115e59;padding:7px 10px;font-size:12px;font-weight:700;cursor:grab}
      .doris-method:hover,.doris-method.selected {background:#ccfbf1;box-shadow:0 0 0 2px #99f6e4}
      .doris-method:focus-visible,.doris-scenario:focus-visible,.doris-match-reset:focus-visible {
        outline:3px solid #5eead4;outline-offset:2px}
      .doris-method[disabled] {cursor:default;opacity:1}
      .doris-scenario-grid {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
      .doris-scenario {border:1px solid #dbe4e8;border-left:3px solid #64748b;border-radius:5px;
        background:#fff;padding:12px;transition:border-color .15s,background .15s}
      .doris-scenario.over {border-color:#0f766e;background:#f0fdfa}
      .doris-scenario.correct {border-left-color:#16803c;background:#f0fdf4}
      .doris-scenario.wrong {border-left-color:#c62828;background:#fff5f5}
      .doris-scenario-title {display:flex;gap:8px;align-items:flex-start;color:#17212b;
        font-size:14px;font-weight:750;margin-bottom:9px}
      .doris-scenario-letter {display:inline-flex;align-items:center;justify-content:center;flex:0 0 22px;
        width:22px;height:22px;border-radius:999px;background:#e2e8f0;color:#475569;font-size:11px}
      .doris-contract {display:grid;grid-template-columns:92px 1fr;gap:4px 8px;margin:0;font-size:11px;line-height:1.4}
      .doris-contract dt {color:#64748b;font-weight:700;margin:0}.doris-contract dd {margin:0;color:#334155}
      .doris-dropzone {display:flex;align-items:center;min-height:36px;border:1px dashed #94a3b8;
        border-radius:4px;background:#f8fafc;color:#64748b;padding:6px 8px;margin-top:11px;font-size:11px}
      .doris-dropzone .doris-method {cursor:default;background:#dcfce7;border-color:#16803c;color:#166534}
      .doris-match-feedback {min-height:34px;font-size:11px;line-height:1.45;margin-top:7px;color:#64748b}
      .doris-scenario.correct .doris-match-feedback {color:#166534}
      .doris-scenario.wrong .doris-match-feedback {color:#991b1b}
      .doris-match-actions {display:flex;justify-content:flex-end;margin-top:12px}
      .doris-match-reset {border:1px solid #cbd5e1;border-radius:4px;background:#fff;color:#475569;
        padding:6px 10px;font-size:11px;cursor:pointer}
      @media (max-width:700px) {.doris-cover-title{font-size:24px}.doris-flow-arrow{display:none}
        .doris-flow-step{flex-basis:100%}.doris-workflow-list{grid-template-columns:1fr}
        .doris-scenario-grid{grid-template-columns:1fr}.doris-match-head{display:block}
        .doris-match-score{display:inline-block;margin-top:8px}.doris-contract{grid-template-columns:82px 1fr}}
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


def progress_step(current: int, total: int, title: str, detail: str = "") -> None:
    percent = max(0, min(100, round(current / total * 100)))
    detail_html = f'<span>{html.escape(detail)}</span>' if detail else ""
    display(HTML(
        '<div class="doris-progress">'
        f'<div class="doris-progress-head"><span>{current}/{total} · {html.escape(title)}</span>'
        f'{detail_html}</div><div class="doris-progress-track">'
        f'<div class="doris-progress-fill" style="width:{percent}%"></div></div></div>'
    ))


def show_log(title: str, output: str, *, opened: bool = False) -> None:
    open_attribute = " open" if opened else ""
    display(HTML(
        f'<details class="doris-log"{open_attribute}><summary>{html.escape(title)}</summary>'
        f'<pre>{html.escape(output or "(no output)")}</pre></details>'
    ))


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
        cells = "".join(f"<td>{html.escape('NULL' if value is None else str(value))}</td>" for value in row)
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


def run(command: Sequence[str], *, check: bool = True, timeout: int | None = None,
        show: bool = False, stream: bool = False) -> subprocess.CompletedProcess[str]:
    command = [str(part) for part in command]
    if stream:
        print("$ " + " ".join(command), flush=True)
        process = subprocess.Popen(
            command,
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
        return_code = process.wait(timeout=timeout)
        output = "".join(lines)
        result = subprocess.CompletedProcess(command, return_code, output, "")
        if check and result.returncode != 0:
            raise RuntimeError(f"Command failed with exit code {result.returncode}: {' '.join(command)}")
        return result
    result = subprocess.run(command, text=True, capture_output=True, timeout=timeout)
    combined = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
    if show:
        show_log("$ " + " ".join(command), combined)
    if check and result.returncode != 0:
        show_log("Command failed", combined)
        raise RuntimeError(f"Command failed with exit code {result.returncode}: {' '.join(command)}")
    return result


def docker_exists(kind: str, name: str) -> bool:
    return run(["docker", kind, "inspect", name], check=False).returncode == 0


def ensure_network(name: str) -> None:
    if docker_exists("network", name):
        card(f"Reusing Docker network {name}", "ok")
    else:
        run(["docker", "network", "create", name], show=True)
        card(f"Created Docker network {name}", "ok")


def ensure_volume(name: str) -> None:
    if docker_exists("volume", name):
        card(f"Reusing Docker volume {name}", "ok")
    else:
        run(["docker", "volume", "create", name], show=True)
        card(f"Created Docker volume {name}", "ok")


def container_inspect(name: str) -> dict | None:
    result = run(["docker", "container", "inspect", name], check=False)
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)[0]


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


def wait_for_port(host: str, port: int, timeout_seconds: int = 60) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        with socket.socket() as sock:
            sock.settimeout(1)
            if sock.connect_ex((host, port)) == 0:
                return
        time.sleep(1)
    raise TimeoutError(f"Timed out waiting for {host}:{port}")


def connect_doris(host: str = "127.0.0.1", port: int = 9030):
    wait_for_port(host, port)
    return pymysql.connect(host=host, port=port, user="root", password="",
                           charset="utf8mb4", autocommit=True,
                           cursorclass=pymysql.cursors.DictCursor)


def sql(connection, statement: str, *, title: str | None = None,
        show_statement: bool = True, final: bool = False,
        columns: Sequence[str] | None = None, quiet_success: bool = False):
    clean = statement.strip()
    if show_statement:
        show_sql(title or "SQL", clean)
    with connection.cursor() as cursor:
        cursor.execute(clean)
        rows = cursor.fetchall() if cursor.description else []
        affected = cursor.rowcount
    if rows:
        frame = pd.DataFrame(rows)
        if columns:
            available = [column for column in columns if column in frame.columns]
            if available:
                frame = frame.loc[:, available]
        show_frame(title or "Query result", frame, final=final)
        return frame
    if not quiet_success:
        card(f"Statement succeeded; affected rows reported by the client: {affected:,}", "ok", title)
    return affected


def execute_quiet(connection, statement: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(statement.strip())
        return cursor.rowcount


def load_env_file(path: Path) -> Mapping[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        raise FileNotFoundError(f"Missing secrets file: {path}")
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator:
            raise ValueError(f"Invalid line in {path.name}: {raw!r}")
        values[key.strip()] = value.strip()
    return values


def sql_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def s3_tvf(config: Mapping[str, str], access_key: str, secret_key: str) -> str:
    properties = {
        "uri": config["uri"],
        "s3.endpoint": config["endpoint"],
        "s3.region": config["region"],
        "s3.access_key": access_key,
        "s3.secret_key": secret_key,
        "format": config["format"],
    }
    body = ",\n".join(f'    "{key}" = "{sql_string(value)}"' for key, value in properties.items())
    return f"S3(\n{body}\n)"


def redacted_s3_config(config: Mapping[str, str]) -> pd.DataFrame:
    rows = [{"property": key, "value": value} for key, value in config.items()]
    rows.extend([
        {"property": "s3.access_key", "value": "•••••••• (loaded from local secrets file)"},
        {"property": "s3.secret_key", "value": "•••••••• (loaded from local secrets file)"},
    ])
    return pd.DataFrame(rows)


class DorisLab:
    """Learner-facing façade shared by the Doris course notebooks.

    The notebook keeps the SQL visible while this class owns environment
    branching, credentials, expected values, progress, and styled diagnostics.
    """

    DORIS_IMAGE = "apache/doris:all-in-one-4.1.3"
    DORIS_CONTAINER = "doris"
    DORIS_NETWORK = "doris-course"
    FE_VOLUME = "doris-fe-meta"
    BE_VOLUME = "doris-be-storage"
    S3_CONFIG = {
        "uri": "s3://yy-glue-test-us-east-1/doris-course/events/v1/events-*.parquet",
        "endpoint": "https://s3.us-east-1.amazonaws.com",
        "region": "us-east-1",
        "format": "parquet",
    }
    EXPECTED_ROW_COUNT = 10_158_080
    EXPECTED_MIN_TIME = "2019-12-01 00:00:12"
    EXPECTED_MAX_TIME = "2020-03-11 04:53:08"
    EXPECTED_DISTINCT_USERS = 1_580_057
    EXPECTED_DISTINCT_PRODUCTS = 204_231
    EXPECTED_TOTAL_REVENUE = Decimal("39984455.64")
    EXPECTED_EVENT_COUNTS = {"view": 9_437_184, "cart": 589_824, "purchase": 131_072}
    SOURCE_TOKEN = "{{COURSE_S3}}"
    S3_ACCESS_KEY_TOKEN = "{{S3_READ_ONLY_ACCESS_KEY}}"
    S3_SECRET_KEY_TOKEN = "{{S3_READ_ONLY_SECRET_KEY}}"

    def __init__(
        self,
        lab_dir: Path | None = None,
        *,
        ready_title: str = "Lab tools are ready",
        ready_message: str = "You can now continue to Section 1 and run the remaining cells in order.",
    ) -> None:
        self.lab_dir = (lab_dir or LAB_DIR).resolve()
        self.connection = None
        self._source_tvf: str | None = None
        self._s3_access_key: str | None = None
        self._s3_secret_key: str | None = None
        self._redacted_tvf = s3_tvf(
            self.S3_CONFIG,
            "{{S3_READ_ONLY_ACCESS_KEY}}",
            "{{S3_READ_ONLY_SECRET_KEY}}",
        )
        install_styles()
        card(
            ready_message,
            "ok",
            ready_title,
        )

    def _failure(self, title: str, message: str, log: str = "") -> None:
        card(message, "fail", title)
        if log:
            show_log("Diagnostic details", log, opened=True)

    def _require_connection(self):
        if self.connection is None:
            try:
                with socket.create_connection(("127.0.0.1", 9030), timeout=1):
                    pass
                self.connection = pymysql.connect(
                    host="127.0.0.1",
                    port=9030,
                    user="root",
                    password="",
                    charset="utf8mb4",
                    autocommit=True,
                    connect_timeout=3,
                    cursorclass=pymysql.cursors.DictCursor,
                )
                # Restore the course context when a learner resumes after a
                # kernel restart. The database does not exist on a first run,
                # so that case intentionally remains harmless.
                try:
                    with self.connection.cursor() as cursor:
                        cursor.execute("USE doris_course")
                except pymysql.MySQLError:
                    pass
            except (OSError, pymysql.MySQLError) as exc:
                raise RuntimeError(
                    "No running Doris server is reachable on 127.0.0.1:9030. "
                    "Run the Prepare environment cell and then the Connect to Doris cell in "
                    "Section 2. A kernel restart does not delete the Docker image, container, "
                    "named volumes, or imported tables."
                ) from exc
        return self.connection

    def _expand_sql(self, statement: str) -> tuple[str, str]:
        display_statement = statement.replace(self.SOURCE_TOKEN, self._redacted_tvf)
        requires_s3_credentials = any(token in statement for token in (
            self.SOURCE_TOKEN,
            self.S3_ACCESS_KEY_TOKEN,
            self.S3_SECRET_KEY_TOKEN,
        ))
        if not requires_s3_credentials:
            return statement, display_statement
        if (
            self._source_tvf is None
            or self._s3_access_key is None
            or self._s3_secret_key is None
        ):
            raise RuntimeError("S3 credentials are not loaded. Complete Section 4 before continuing.")
        executable = statement.replace(self.SOURCE_TOKEN, self._source_tvf)
        executable = executable.replace(self.S3_ACCESS_KEY_TOKEN, self._s3_access_key)
        executable = executable.replace(self.S3_SECRET_KEY_TOKEN, self._s3_secret_key)
        return executable, display_statement

    def sql(
        self,
        statement: str,
        *,
        title: str | None = None,
        final: bool = False,
        columns: Sequence[str] | None = None,
        metadata_view: str | None = None,
    ):
        if metadata_view is not None:
            normalized_view = metadata_view.strip().lower()
            table_match = re.search(
                r"(?i)\b(?:TABLE|FROM)\s+`?([A-Za-z_][A-Za-z0-9_]*)`?",
                statement,
            )
            if not table_match:
                raise ValueError("A table name is required for a metadata summary.")
            table_name = table_match.group(1)
            if normalized_view == "design":
                return self.table_design_summary(table_name, title=title)
            if normalized_view == "partitions":
                return self.partition_layout_summary(table_name, title=title)
            if normalized_view == "tablets":
                return self.tablet_layout_summary(table_name, title=title)
            raise ValueError(f"Unknown metadata view: {metadata_view!r}")
        connection = self._require_connection()
        executable, _visible = self._expand_sql(statement.strip())
        normalized = " ".join(statement.upper().split())
        if columns is None and normalized == "SHOW FRONTENDS":
            columns = ["Name", "Host", "Role", "IsMaster", "Join", "Alive", "Version"]
        elif columns is None and normalized == "SHOW BACKENDS":
            columns = [
                "BackendId", "Host", "Alive", "SystemDecommissioned", "TabletNum", "Version",
            ]
        return sql(
            connection,
            executable,
            title=title,
            show_statement=False,
            final=final,
            columns=columns,
        )

    def execute(self, statement: str) -> int:
        connection = self._require_connection()
        executable, _visible = self._expand_sql(statement.strip())
        return sql(
            connection,
            executable,
            show_statement=False,
            quiet_success=True,
        )

    def insert(
        self,
        statement: str,
        *,
        title: str = "Insert completed",
        low_memory_s3: bool = False,
    ) -> int:
        """Run a learner-visible data insert and report its wall-clock duration."""
        started_at = time.perf_counter()
        connection = self._require_connection()
        previous_settings: dict[str, object] = {}
        if low_memory_s3:
            with connection.cursor() as cursor:
                for variable, value in (
                    ("parallel_pipeline_task_num", 1),
                    ("max_file_scanners_concurrency", 2),
                ):
                    cursor.execute(f"SHOW VARIABLES LIKE '{variable}'")
                    row = cursor.fetchone()
                    if row:
                        previous_settings[variable] = row.get("Value")
                    cursor.execute(f"SET {variable} = {value}")
        try:
            affected = self.execute(statement)
        finally:
            if previous_settings:
                with connection.cursor() as cursor:
                    for variable, value in previous_settings.items():
                        cursor.execute(f"SET {variable} = {int(value)}")
        elapsed = time.perf_counter() - started_at
        card(
            f"Affected rows: {affected:,} · elapsed time: {elapsed:.1f} seconds",
            "ok",
            title,
        )
        return affected

    @staticmethod
    def _safe_table_name(table_name: str) -> str:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table_name):
            raise ValueError(f"Unsafe table name: {table_name!r}")
        return table_name

    def load_table_once(
        self,
        table_name: str,
        statement: str,
        *,
        expected_rows: int | None = None,
    ) -> int:
        """Populate a derived course table without duplicating rows on rerun."""
        table_name = self._safe_table_name(table_name)
        expected_rows = expected_rows or self.EXPECTED_ROW_COUNT
        connection = self._require_connection()
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS row_count FROM `{table_name}`")
            current_count = int(cursor.fetchone()["row_count"])
        if current_count == expected_rows:
            return current_count
        if current_count != 0:
            raise RuntimeError(
                f"{table_name} contains {current_count:,} rows; expected 0 or "
                f"{expected_rows:,}. Drop and recreate that derived table before retrying."
            )
        return self.execute(statement)

    def _metadata_rows(self, statement: str) -> list[dict[str, object]]:
        connection = self._require_connection()
        with connection.cursor() as cursor:
            cursor.execute(statement)
            return list(cursor.fetchall())

    @staticmethod
    def _human_bytes(value: int) -> str:
        amount = float(value)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if amount < 1024 or unit == "TB":
                return f"{amount:,.2f} {unit}"
            amount /= 1024
        return f"{amount:,.2f} TB"

    @staticmethod
    def _number_range(values: Sequence[int]) -> str:
        low, high = min(values), max(values)
        return f"{low:,}" if low == high else f"{low:,}–{high:,}"

    def table_design_summary(
        self,
        table_name: str,
        *,
        title: str | None = None,
    ) -> pd.DataFrame:
        """Turn SHOW CREATE TABLE into the small set of design choices used by Lab 2."""
        table_name = self._safe_table_name(table_name)
        records = self._metadata_rows(f"SHOW CREATE TABLE `{table_name}`")
        if not records:
            raise RuntimeError(f"SHOW CREATE TABLE returned no row for {table_name}.")
        ddl = str(records[0].get("Create Table", ""))

        key_match = re.search(
            r"\b(DUPLICATE|UNIQUE|AGGREGATE)\s+KEY\s*\(([^)]*)\)",
            ddl,
            re.IGNORECASE | re.DOTALL,
        )
        if not key_match:
            raise RuntimeError(f"The table model could not be parsed from {table_name}.")
        key_columns = ", ".join(re.findall(r"`([^`]+)`", key_match.group(2)))

        partition_match = re.search(
            r"date_trunc\s*\(\s*`?([^`,)]+)`?\s*,\s*'([^']+)'\s*\)",
            ddl,
            re.IGNORECASE,
        )
        if "AUTO PARTITION BY RANGE" in ddl.upper() and partition_match:
            partitioning = (
                f"Auto Range · {partition_match.group(1).strip()} by "
                f"{partition_match.group(2).lower()}"
            )
        else:
            partitioning = "No explicit partitioning"

        distribution_match = re.search(
            r"DISTRIBUTED\s+BY\s+(RANDOM|HASH\s*\([^)]*\))\s+BUCKETS\s+(\w+)",
            ddl,
            re.IGNORECASE | re.DOTALL,
        )
        if not distribution_match:
            raise RuntimeError(f"The distribution clause could not be parsed from {table_name}.")
        distribution = re.sub(r"\s+", " ", distribution_match.group(1)).replace("`", "")
        if distribution.upper().startswith("HASH"):
            distribution = f"HASH({distribution.split('(', 1)[1].rsplit(')', 1)[0].strip()})"
        else:
            distribution = "RANDOM"
        bucket_count = distribution_match.group(2)
        replica_match = re.search(
            r'"replication_allocation"\s*=\s*"([^"]+)"', ddl, re.IGNORECASE
        )
        replicas = replica_match.group(1) if replica_match else "not shown"
        replica_parts = replicas.rsplit(":", 1)
        if len(replica_parts) == 2 and replica_parts[1].strip().isdigit():
            replica_count = int(replica_parts[1].strip())
            label = "replica" if replica_count == 1 else "replicas"
            replicas = f"{replica_count} {label} per tablet · {replica_parts[0].strip()}"

        frame = pd.DataFrame([
            {"design choice": "Table model", "resolved value": f"{key_match.group(1).title()} Key"},
            {"design choice": "Sort key", "resolved value": key_columns},
            {"design choice": "Partitioning", "resolved value": partitioning},
            {"design choice": "Distribution", "resolved value": distribution},
            {"design choice": "Buckets per partition", "resolved value": bucket_count},
            {"design choice": "Replica allocation", "resolved value": replicas},
        ])
        show_frame(title or f"{table_name} design summary", frame)
        return frame

    def partition_layout_summary(
        self,
        table_name: str,
        *,
        title: str | None = None,
    ) -> pd.DataFrame:
        """Summarize all partitions without printing one metadata row per date."""
        table_name = self._safe_table_name(table_name)
        partitions = self._metadata_rows(
            f"SHOW PARTITIONS FROM `{table_name}` ORDER BY PartitionName"
        )
        if not partitions:
            raise RuntimeError(f"SHOW PARTITIONS returned no rows for {table_name}.")
        bucket_values = [int(row["Buckets"]) for row in partitions]
        row_count = sum(int(row["RowCount"]) for row in partitions)
        normal_count = sum(str(row["State"]).upper() == "NORMAL" for row in partitions)
        bounds: list[str] = []
        for row in partitions:
            bounds.extend(re.findall(r"\d{4}-\d{2}-\d{2}", str(row.get("Range", ""))))
        partition_bounds = (
            f"{min(bounds)} → {max(bounds)} (upper bound exclusive)"
            if bounds else "not shown"
        )
        distribution_keys = {
            str(row.get("DistributionKey", "")).replace("`", "") for row in partitions
        }
        frame = pd.DataFrame([
            {"partition metric": "Daily partitions", "observed value": f"{len(partitions):,}"},
            {"partition metric": "Date bounds", "observed value": partition_bounds},
            {
                "partition metric": "Healthy partitions",
                "observed value": f"{normal_count}/{len(partitions)} NORMAL",
            },
            {
                "partition metric": "Distribution key",
                "observed value": ", ".join(sorted(distribution_keys)),
            },
            {
                "partition metric": "Buckets per partition",
                "observed value": self._number_range(bucket_values),
            },
            {"partition metric": "Total tablets", "observed value": f"{sum(bucket_values):,}"},
            {"partition metric": "Logical rows", "observed value": f"{row_count:,}"},
        ])
        show_frame(title or f"{table_name} partition summary", frame)
        return frame

    def tablet_layout_summary(
        self,
        table_name: str,
        *,
        title: str | None = None,
    ) -> pd.DataFrame:
        """Summarize every tablet without selecting an arbitrary sample of tablet rows."""
        table_name = self._safe_table_name(table_name)
        tablets = self._metadata_rows(f"SHOW TABLETS FROM `{table_name}`")
        if not tablets:
            raise RuntimeError(f"SHOW TABLETS returned no rows for {table_name}.")
        tablet_ids = {int(row["TabletId"]) for row in tablets}
        replica_counts: dict[int, int] = {}
        for tablet in tablets:
            tablet_id = int(tablet["TabletId"])
            replica_counts[tablet_id] = replica_counts.get(tablet_id, 0) + 1
        tablet_rows = [int(row["RowCount"]) for row in tablets]
        version_counts = [int(row["VersionCount"]) for row in tablets]
        local_bytes = sum(int(row["LocalDataSize"]) for row in tablets)
        frame = pd.DataFrame([
            {"tablet metric": "Unique tablets", "observed value": f"{len(tablet_ids):,}"},
            {
                "tablet metric": "Replicas per tablet",
                "observed value": self._number_range(list(replica_counts.values())),
            },
            {
                "tablet metric": "Rows per tablet",
                "observed value": self._number_range(tablet_rows),
            },
            {
                "tablet metric": "Local replica size",
                "observed value": self._human_bytes(local_bytes),
            },
            {
                "tablet metric": "VersionCount range",
                "observed value": self._number_range(version_counts),
            },
        ])
        show_frame(title or f"{table_name} tablet summary", frame)
        return frame

    def storage_layout_summary(self, table_names: Sequence[str]) -> pd.DataFrame:
        """Compare table-level physical layout without exposing hundreds of tablet rows."""
        rows: list[dict[str, object]] = []
        for candidate in table_names:
            table_name = self._safe_table_name(candidate)
            partitions = self._metadata_rows(f"SHOW PARTITIONS FROM `{table_name}`")
            tablets = self._metadata_rows(f"SHOW TABLETS FROM `{table_name}`")
            if not partitions or not tablets:
                raise RuntimeError(f"Physical metadata is incomplete for {table_name}.")
            bucket_values = [int(row["Buckets"]) for row in partitions]
            tablet_ids = {int(row["TabletId"]) for row in tablets}
            replica_counts: dict[int, int] = {}
            for tablet in tablets:
                tablet_id = int(tablet["TabletId"])
                replica_counts[tablet_id] = replica_counts.get(tablet_id, 0) + 1
            tablet_rows = [int(row["RowCount"]) for row in tablets]
            version_counts = [int(row["VersionCount"]) for row in tablets]
            local_bytes = sum(int(row["LocalDataSize"]) for row in tablets)
            rows.append({
                "table": table_name,
                "partitions": len(partitions),
                "buckets / partition": self._number_range(bucket_values),
                "tablets": len(tablet_ids),
                "replicas / tablet": self._number_range(list(replica_counts.values())),
                "logical rows": f"{sum(int(row['RowCount']) for row in partitions):,}",
                "rows / tablet": self._number_range(tablet_rows),
                "local replica size": self._human_bytes(local_bytes),
                "version count": self._number_range(version_counts),
            })
        frame = pd.DataFrame(rows)
        show_frame("Physical layout comparison", frame)
        return frame

    @staticmethod
    def _explain_value(plan: str, label: str) -> str:
        match = re.search(rf"(?im)^\s*{re.escape(label)}\s*[:=]\s*([^\n]+)", plan)
        return match.group(1).strip() if match else "not shown"

    @staticmethod
    def _explain_scope(value: str) -> str:
        """Keep only the selected/total ratio from an EXPLAIN scope field."""
        match = re.search(r"\b\d+\s*/\s*\d+\b", value)
        return re.sub(r"\s+", "", match.group(0)) if match else value

    def compare_explain(
        self,
        cases: Sequence[tuple[str, str]],
        *,
        title: str = "EXPLAIN scan scope",
    ) -> pd.DataFrame:
        """Render the pruning fields from several EXPLAIN plans as one compact table."""
        connection = self._require_connection()
        rows: list[dict[str, str]] = []
        raw_plans: list[str] = []
        for label, statement in cases:
            normalized = statement.strip()
            if not normalized.upper().startswith("EXPLAIN"):
                raise ValueError(f"EXPLAIN expected for {label!r}.")
            with connection.cursor() as cursor:
                cursor.execute(normalized)
                records = cursor.fetchall()
            plan = "\n".join(str(next(iter(record.values()))) for record in records)
            rows.append({
                "query": label,
                "partitions": self._explain_scope(
                    self._explain_value(plan, "partitions")
                ),
                "tablets": self._explain_scope(
                    self._explain_value(plan, "tablets")
                ),
            })
            raw_plans.append(f"--- {label} ---\n{plan}")
        frame = pd.DataFrame(rows)
        show_frame(title, frame)
        show_log("View the complete EXPLAIN plans", "\n\n".join(raw_plans))
        return frame

    @staticmethod
    def _normalize_statement(statement: str) -> str:
        return " ".join(statement.strip().rstrip(";").split()).lower()

    def _query_profiles(self) -> list[dict[str, object]]:
        connection = self._require_connection()
        with connection.cursor() as cursor:
            cursor.execute("SHOW QUERY PROFILE")
            return list(cursor.fetchall())

    def _latest_profile_id(
        self,
        statement: str,
        *,
        exclude: set[str] | None = None,
        timeout_seconds: int = 8,
    ) -> str:
        target = self._normalize_statement(statement)
        excluded = exclude or set()
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            for profile in self._query_profiles():
                profile_id = str(profile["Profile ID"])
                candidate = str(profile.get("Sql Statement", ""))
                if profile_id not in excluded and self._normalize_statement(candidate) == target:
                    return profile_id
            time.sleep(0.2)
        raise RuntimeError("The newly completed query was not found in SHOW QUERY PROFILE.")

    @staticmethod
    def _profile_metric(profile: str, metric: str) -> str:
        match = re.search(rf"(?im)^\s*-?\s*{re.escape(metric)}:\s*(?:sum\s+)?([^,\n]+)", profile)
        return match.group(1).strip() if match else "not shown"

    @staticmethod
    def _profile_row_sum(profile: str, metric: str) -> int | str:
        values = re.findall(
            rf"(?im)^\s*-\s*{re.escape(metric)}:\s*([^\n]+?)\s*$",
            profile,
        )
        exact_values: list[int] = []
        for value in values:
            parenthesized = re.search(r"\(([0-9,]+)\)\s*$", value)
            if parenthesized:
                exact_values.append(int(parenthesized.group(1).replace(",", "")))
                continue
            plain = re.fullmatch(r"[0-9,]+", value.strip())
            if plain:
                exact_values.append(int(value.replace(",", "")))
        return sum(exact_values) if exact_values else "not shown"

    def _profile_text(self, profile_id: str, *, timeout_seconds: int = 20) -> str:
        token = base64.b64encode(b"root:").decode("ascii")
        url = f"http://127.0.0.1:8030/rest/v2/manager/query/profile/text/{profile_id}"
        deadline = time.monotonic() + timeout_seconds
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                request = urllib.request.Request(
                    url,
                    headers={"Authorization": f"Basic {token}"},
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    payload = json.load(response)
                profile = str(payload.get("data", {}).get("profile", ""))
                if "OLAP_SCAN_OPERATOR" in profile:
                    return profile
                if "Is Cached: Yes" in profile and "Total Instances Num: 0" in profile:
                    raise RuntimeError(
                        "The query used SQL Cache, so Doris did not run a new BE scan operator."
                    )
            except Exception as exc:  # profile materialization can lag the query briefly
                last_error = exc
                if "used SQL Cache" in str(exc):
                    raise
            time.sleep(0.4)
        raise RuntimeError(f"The runtime profile was not ready: {last_error or 'timed out'}")

    def compare_profiles(
        self,
        cases: Sequence[tuple[str, str]],
        *,
        title: str = "Runtime scan evidence",
    ) -> pd.DataFrame:
        """Run comparable queries and summarize only their OLAP scan evidence."""
        connection = self._require_connection()
        controlled_settings = {
            "enable_profile": "true",
            "profile_level": "2",
            "enable_condition_cache": "false",
            "enable_query_cache": "false",
            "enable_sql_cache": "false",
        }
        original_settings: dict[str, str] = {}
        with connection.cursor() as cursor:
            for name, value in controlled_settings.items():
                cursor.execute(f"SHOW VARIABLES LIKE '{name}'")
                row = cursor.fetchone()
                if row is None:
                    raise RuntimeError(f"Doris did not expose the required session variable {name}.")
                original_settings[name] = str(row["Value"])
                cursor.execute(f"SET {name} = {value}")
        rows: list[dict[str, object]] = []
        profile_ids: list[str] = []
        try:
            for label, statement in cases:
                query = statement.strip().rstrip(";")
                existing_profile_ids = {
                    str(profile["Profile ID"]) for profile in self._query_profiles()
                }
                with connection.cursor() as cursor:
                    cursor.execute(query)
                    result = cursor.fetchone() or {}
                profile_id = self._latest_profile_id(query, exclude=existing_profile_ids)
                profile = self._profile_text(profile_id)
                merged = profile
                if "MergedProfile:" in merged:
                    merged = merged.split("MergedProfile:", 1)[1]
                if "DetailProfile" in merged:
                    merged = merged.split("DetailProfile", 1)[0]
                rows.append({
                    "query": label,
                    "event_count": result.get("event_count", "not shown"),
                    "total_revenue": result.get("total_revenue", "not shown"),
                    "scan_rows": self._profile_metric(merged, "ScanRows"),
                    "rows_read": self._profile_row_sum(profile, "RowsRead"),
                    "scan_bytes": self._profile_metric(merged, "ScanBytes"),
                })
                profile_ids.append(f"{label}: {profile_id}")
        finally:
            with connection.cursor() as cursor:
                for name, value in original_settings.items():
                    cursor.execute(f"SET {name} = {value}")
        frame = pd.DataFrame(rows)
        show_frame(title, frame)
        show_log("Profile IDs for optional inspection in the FE web UI", "\n".join(profile_ids))
        return frame

    def shell(self, script: str, *, title: str) -> subprocess.CompletedProcess[str]:
        """Run learner-visible Bash and render its output like the dbt demos."""
        markers = {
            int(number): label
            for number, _total, label in re.findall(
                r'echo\s+"\[(\d+)/(\d+)\]\s+([^"\n]+)"', script
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
        return_code = process.wait()
        elapsed = time.perf_counter() - started_at
        output = "".join(lines)
        result = subprocess.CompletedProcess(
            ["/bin/bash", "-lc", script.strip()], return_code, output, ""
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

    def load_method_quiz(self) -> None:
        """Match visible ingestion contracts to methods by drag, click, or keyboard."""
        scenarios = [
            {
                "id": "A",
                "title": "Bounded client-side CSV batch",
                "answer": "Stream Load",
                "contract": [
                    ("Source", "A pipe-delimited file on the client host"),
                    ("Volume", "One bounded 1,024-row sample"),
                    ("Latency", "Return the outcome with the request"),
                    ("Delivery", "The client pushes bytes over HTTP"),
                    ("Transform", "Parse, map, filter, and report row quality"),
                    ("Retry", "Reuse one stable label after an uncertain response"),
                ],
                "reason": "Correct. Stream Load accepts a bounded client push, returns synchronous quality counts, and uses a stable label to protect a successful batch from the same retry.",
            },
            {
                "id": "B",
                "title": "Fixed Parquet objects in S3",
                "answer": "S3 TVF + INSERT INTO SELECT",
                "contract": [
                    ("Source", "A fixed object set in S3-compatible storage"),
                    ("Volume", "40 Parquet objects; 10,158,080 rows"),
                    ("Latency", "A minutes-scale batch is acceptable"),
                    ("Delivery", "Doris BE pulls the remote objects"),
                    ("Transform", "Use SQL projection before persistence"),
                    ("Retry", "Record the object set and statement outcome externally"),
                ],
                "reason": "Correct. The S3 TVF exposes the fixed objects as a temporary relation, and INSERT INTO SELECT applies SQL transformation and commits the permanent copy.",
            },
            {
                "id": "C",
                "title": "Continuous nested JSON from Kafka",
                "answer": "Routine Load",
                "contract": [
                    ("Source", "A Kafka topic carrying nested JSON messages"),
                    ("Volume", "An unbounded event stream"),
                    ("Latency", "New rows should appear within seconds"),
                    ("Delivery", "A long-running Doris job pulls micro-batches"),
                    ("Transform", "Extract JSON paths and map target columns"),
                    ("Retry", "Resume from offsets committed with successful loads"),
                ],
                "reason": "Correct. Routine Load manages a continuing Kafka subscription and commits consumed offsets together with each successful micro-batch.",
            },
            {
                "id": "D",
                "title": "Frequent tiny application writes",
                "answer": "Group Commit",
                "contract": [
                    ("Source", "An application issuing Stream Load or INSERT writes"),
                    ("Volume", "Very small payloads at high frequency"),
                    ("Latency", "Keep the familiar synchronous or asynchronous mode"),
                    ("Delivery", "Reuse the existing write interface"),
                    ("Transform", "No new source connector is required"),
                    ("Retry", "Follow the underlying write contract"),
                ],
                "reason": "Correct. Group Commit combines frequent small writes to reduce transaction and Rowset pressure; it is an optimization rather than an S3 or Kafka connector.",
            },
        ]
        methods = ["Routine Load", "Stream Load", "Group Commit", "S3 TVF + INSERT INTO SELECT"]
        widget_id = "doris-load-match-" + uuid.uuid4().hex

        method_html = "".join(
            f'<button type="button" class="doris-method" draggable="true" '
            f'data-method="{html.escape(method)}">{html.escape(method)}</button>'
            for method in methods
        )
        scenario_html = []
        for scenario in scenarios:
            contract_html = "".join(
                f'<dt>{html.escape(label)}</dt><dd>{html.escape(value)}</dd>'
                for label, value in scenario["contract"]
            )
            scenario_html.append(
                f'<section class="doris-scenario" data-answer="{html.escape(scenario["answer"])}" '
                f'data-reason="{html.escape(scenario["reason"])}" tabindex="0" role="button" '
                f'aria-label="Match a load method to workload {scenario["id"]}">'
                '<div class="doris-scenario-title">'
                f'<span class="doris-scenario-letter">{scenario["id"]}</span>'
                f'<span>{html.escape(scenario["title"])}</span></div>'
                f'<dl class="doris-contract">{contract_html}</dl>'
                '<div class="doris-dropzone">Drop the matching method here, or select a method and click this card.</div>'
                '<div class="doris-match-feedback" aria-live="polite"></div></section>'
            )

        markup = (
            f'<div id="{widget_id}" class="doris-match">'
            '<div class="doris-match-head"><div>'
            '<div class="doris-match-title">Choose a load method from the complete workload contract</div>'
            '<p class="doris-match-help">Drag each method onto one workload. If dragging is unavailable, '
            'select a method and then click a workload card. An incorrect match explains which requirement conflicts; '
            'a correct match locks in place.</p></div>'
            '<div class="doris-match-score"><span data-score>0</span>/4 matched</div></div>'
            f'<div class="doris-method-bank" aria-label="Available load methods">{method_html}</div>'
            f'<div class="doris-scenario-grid">{"".join(scenario_html)}</div>'
            '<div class="doris-match-actions"><button type="button" class="doris-match-reset">Reset matches</button></div>'
            '</div>'
        )
        display(HTML(markup))

        mismatch = {
            "A": "This is a bounded client push that needs a synchronous quality response and stable-label retry.",
            "B": "This is a fixed object-storage batch that needs SQL transformation before an atomic permanent copy.",
            "C": "This is an unbounded Kafka source that needs a managed subscription and committed offsets.",
            "D": "This workload already has a write path; it needs small-write batching rather than a new source connector.",
        }
        script = f"""
        (() => {{
          const start = () => {{
            const root = document.getElementById({json.dumps(widget_id)});
            if (!root || root.dataset.ready === 'true') return;
            root.dataset.ready = 'true';
            const bank = root.querySelector('.doris-method-bank');
            const methods = [...root.querySelectorAll('.doris-method')];
            const scenarios = [...root.querySelectorAll('.doris-scenario')];
            const score = root.querySelector('[data-score]');
            let selected = null;

            const selectMethod = (button) => {{
              if (button.disabled) return;
              methods.forEach(item => item.classList.remove('selected'));
              selected = button.dataset.method;
              button.classList.add('selected');
            }};

            const attempt = (scenario, method) => {{
              if (!method || scenario.dataset.solved === 'true') return;
              const feedback = scenario.querySelector('.doris-match-feedback');
              if (method === scenario.dataset.answer) {{
                scenario.dataset.solved = 'true';
                scenario.classList.remove('wrong');
                scenario.classList.add('correct');
                const button = methods.find(item => item.dataset.method === method);
                scenario.querySelector('.doris-dropzone').replaceChildren(button);
                button.classList.remove('selected');
                button.disabled = true;
                button.draggable = false;
                feedback.textContent = scenario.dataset.reason;
                selected = null;
                score.textContent = String(scenarios.filter(item => item.dataset.solved === 'true').length);
              }} else {{
                scenario.classList.remove('correct');
                scenario.classList.add('wrong');
                feedback.textContent = 'Not this method. ' + ({json.dumps(mismatch)})[scenario.querySelector('.doris-scenario-letter').textContent];
              }}
            }};

            methods.forEach(button => {{
              button.addEventListener('click', () => selectMethod(button));
              button.addEventListener('dragstart', event => {{
                selectMethod(button);
                event.dataTransfer.setData('text/plain', button.dataset.method);
                event.dataTransfer.effectAllowed = 'move';
              }});
            }});
            scenarios.forEach(scenario => {{
              scenario.addEventListener('dragover', event => {{
                event.preventDefault(); scenario.classList.add('over');
              }});
              scenario.addEventListener('dragleave', () => scenario.classList.remove('over'));
              scenario.addEventListener('drop', event => {{
                event.preventDefault(); scenario.classList.remove('over');
                attempt(scenario, event.dataTransfer.getData('text/plain') || selected);
              }});
              scenario.addEventListener('click', () => attempt(scenario, selected));
              scenario.addEventListener('keydown', event => {{
                if (event.key === 'Enter' || event.key === ' ') {{event.preventDefault(); attempt(scenario, selected);}}
              }});
            }});
            root.querySelector('.doris-match-reset').addEventListener('click', () => {{
              methods.forEach(button => {{
                button.disabled = false; button.draggable = true; button.classList.remove('selected'); bank.appendChild(button);
              }});
              scenarios.forEach(scenario => {{
                scenario.dataset.solved = 'false'; scenario.classList.remove('correct', 'wrong', 'over');
                scenario.querySelector('.doris-dropzone').textContent = 'Drop the matching method here, or select a method and click this card.';
                scenario.querySelector('.doris-match-feedback').textContent = '';
              }});
              selected = null; score.textContent = '0';
            }});
          }};
          if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, {{once:true}});
          else start();
        }})();
        """
        display(Javascript(script))

    @staticmethod
    def new_run_suffix() -> str:
        return time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]

    @staticmethod
    def _validate_fixture(path: Path, kind: str) -> int:
        text = path.read_text(encoding="utf-8")
        lines = [line for line in text.splitlines() if line.strip()]
        if kind in {"stream_csv", "stream_malformed_csv", "group_commit_csv"}:
            expected_rows = {
                "stream_csv": 1024,
                "stream_malformed_csv": 10,
                "group_commit_csv": 2,
            }[kind]
            fields = [line.split("|") for line in lines]
            if len(fields) != expected_rows or any(len(row) != 7 for row in fields):
                raise ValueError(
                    f"{path.name} must contain {expected_rows} rows with seven pipe-delimited fields."
                )
            if kind == "stream_csv":
                if fields[0][1] != "1" or fields[-1][1] != "10027072":
                    raise ValueError("The Stream Load fixture is not the authored Lab 1/2 sample.")
                if any(row[6] == "not-a-number" for row in fields):
                    raise ValueError("The main Stream Load fixture must contain only valid rows.")
            elif kind == "stream_malformed_csv":
                if fields[0][1] != "1" or fields[-1][1] != "10":
                    raise ValueError("The malformed fixture is not the authored ten-row sample.")
                if sum(row[6] == "not-a-number" for row in fields) != 1:
                    raise ValueError("The malformed fixture must contain one invalid revenue value.")
            elif {row[1] for row in fields} != {"10027009", "10027010"}:
                raise ValueError("The Group Commit fixture contains unexpected event_id values.")
            return len(fields)
        if kind == "routine_json":
            if len(lines) != 1024:
                raise ValueError(f"{path.name} must contain 1024 JSON messages.")
            records = [json.loads(line) for line in lines]
            if records[0]["meta"]["event_id"] != 1 or records[-1]["meta"]["event_id"] != 10027072:
                raise ValueError("The Routine Load fixture is not the authored Lab 1/2 sample.")
            if len({record["meta"]["event_id"] for record in records}) != 1024:
                raise ValueError("The Routine Load fixture must contain 1024 distinct event IDs.")
            if any(not isinstance(record["event"]["revenue"], (int, float)) for record in records):
                raise ValueError("The Routine Load fixture must contain only valid numeric revenue values.")
            return len(records)
        raise ValueError(f"Unknown fixture kind: {kind!r}")

    def fetch_fixtures(
        self,
        fixtures: Sequence[tuple[str, str, str, str]],
    ) -> pd.DataFrame:
        """Download validated course fixtures using a same-directory atomic rename."""
        rows: list[dict[str, str]] = []
        for label, remote_url, local_path, kind in fixtures:
            destination = (self.lab_dir / local_path).resolve()
            destination.parent.mkdir(parents=True, exist_ok=True)
            action = "reused"
            try:
                row_count = self._validate_fixture(destination, kind)
            except (FileNotFoundError, ValueError, json.JSONDecodeError):
                action = "downloaded"
                temporary = destination.with_name(destination.name + ".part")
                try:
                    if remote_url.startswith("s3://"):
                        try:
                            import boto3
                        except ImportError as exc:
                            raise RuntimeError(
                                "boto3 is required for the private course S3 fixtures. "
                                "Install requirements.txt and rerun this cell."
                            ) from exc
                        secrets = load_env_file(self.lab_dir / "lab1_secrets.env")
                        access_key = secrets.get("S3_READ_ONLY_ACCESS_KEY", "")
                        secret_key = secrets.get("S3_READ_ONLY_SECRET_KEY", "")
                        if not access_key or not secret_key:
                            raise RuntimeError(
                                "Fill both read-only S3 credentials in lab1_secrets.env "
                                "before downloading the Lab 3 fixtures."
                            )
                        parsed = urllib.parse.urlsplit(remote_url)
                        client = boto3.client(
                            "s3",
                            endpoint_url=self.S3_CONFIG["endpoint"],
                            region_name=self.S3_CONFIG["region"],
                            aws_access_key_id=access_key,
                            aws_secret_access_key=secret_key,
                        )
                        client.download_file(
                            parsed.netloc,
                            parsed.path.lstrip("/"),
                            str(temporary),
                        )
                    else:
                        with urllib.request.urlopen(remote_url, timeout=60) as response:
                            temporary.write_bytes(response.read())
                    row_count = self._validate_fixture(temporary, kind)
                    os.replace(temporary, destination)
                except Exception:
                    temporary.unlink(missing_ok=True)
                    raise
            rows.append({
                "fixture": label,
                "remote source": remote_url,
                "local file": str(destination),
                "rows": str(row_count),
                "action": action,
            })
        frame = pd.DataFrame(rows)
        show_frame("Learner-side source files", frame)
        return frame

    def preview_fixture(self, local_path: str, kind: str, *, limit: int | None = 10) -> pd.DataFrame:
        path = (self.lab_dir / local_path).resolve()
        self._validate_fixture(path, kind)
        if kind in {"stream_csv", "stream_malformed_csv", "group_commit_csv"}:
            columns = [
                "event_time", "event_id", "user_id", "event_type",
                "region", "product_id", "revenue",
            ]
            frame = pd.read_csv(path, sep="|", names=columns, dtype=str)
            if kind == "stream_malformed_csv":
                frame["expected handling"] = [
                    "filtered; batch rejected" if revenue == "not-a-number" else "valid; batch rejected"
                    for revenue in frame["revenue"]
                ]
        elif kind == "routine_json":
            records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
            frame = pd.DataFrame([{
                "event_time": row["meta"]["occurred_at"],
                "event_id": row["meta"]["event_id"],
                "user_id": row["actor"]["user_id"],
                "event_type": row["event"]["type"],
                "region": row["geo"]["region"],
                "product_id": row["product_id"],
                "revenue": row["event"]["revenue"],
                "expected handling": "loaded",
            } for row in records])
        else:
            raise ValueError(f"Unknown fixture kind: {kind!r}")
        visible = frame if limit is None else frame.head(limit)
        show_frame(path.name, visible)
        return frame

    def stream_load(
        self,
        script: str,
        *,
        title: str,
        expected_status: str | Sequence[str] | None = None,
        expected_counts: Mapping[str, int] | None = None,
        display_columns: Sequence[str] | None = None,
        show_response: bool = True,
        show_json: bool = True,
    ) -> Mapping[str, object]:
        """Execute learner-visible curl text and render the Doris JSON contract compactly."""
        started_at = time.perf_counter()
        result = subprocess.run(
            ["/bin/bash", "-lc", script.strip()],
            cwd=self.lab_dir,
            text=True,
            capture_output=True,
            timeout=180,
        )
        elapsed = time.perf_counter() - started_at
        if result.returncode != 0:
            self._failure(title, f"curl exited with status {result.returncode}.", result.stderr)
            raise RuntimeError(f"{title} failed before Doris returned a response.")
        try:
            response = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            self._failure(title, "The Stream Load response was not valid JSON.", result.stdout)
            raise RuntimeError("Invalid Stream Load response.") from exc
        status = str(response.get("Status", "not shown"))
        if expected_status is not None:
            allowed = {expected_status} if isinstance(expected_status, str) else set(expected_status)
            if status not in allowed:
                raise AssertionError(f"Stream Load status is {status!r}; expected {sorted(allowed)!r}.")
        for key, expected in (expected_counts or {}).items():
            if int(response.get(key, -1)) != expected:
                raise AssertionError(
                    f"Stream Load {key} is {response.get(key)!r}; expected {expected}."
                )
        frame = pd.DataFrame([{
            "status": status,
            "label": response.get("Label", "not shown"),
            "transaction": response.get("TxnId", "not shown"),
            "total": response.get("NumberTotalRows", "not shown"),
            "loaded": response.get("NumberLoadedRows", "not shown"),
            "filtered": response.get("NumberFilteredRows", "not shown"),
            "unselected": response.get("NumberUnselectedRows", "not shown"),
            "group commit": response.get("GroupCommit", False),
            "elapsed": f"{elapsed:.1f} s",
        }])
        if display_columns is not None:
            unknown = [column for column in display_columns if column not in frame.columns]
            if unknown:
                raise ValueError(f"Unknown Stream Load display columns: {unknown}")
            frame = frame.loc[:, list(display_columns)]
        if show_response:
            show_frame(title, frame)
        if show_json:
            show_log("Complete Stream Load JSON response", json.dumps(response, indent=2))
        return response

    def show_stream_load_error_log(self, error_url: str) -> str:
        """Fetch and directly display the diagnostic returned by a Stream Load ErrorURL."""
        error_url = str(error_url or "").strip()
        if not error_url:
            raise RuntimeError(
                "Doris rejected the batch but did not return an ErrorURL, so row-level "
                "diagnostic details are unavailable."
            )

        show_sql("ErrorURL returned by Stream Load", error_url)

        candidates = [error_url]
        parsed = urllib.parse.urlsplit(error_url)
        if parsed.hostname not in {None, "127.0.0.1", "localhost"}:
            host_url = urllib.parse.urlunsplit((
                parsed.scheme,
                f"127.0.0.1:{parsed.port or 8040}",
                parsed.path,
                parsed.query,
                parsed.fragment,
            ))
            candidates.insert(0, host_url)

        error_log = ""
        last_error: Exception | None = None
        for candidate in candidates:
            try:
                with urllib.request.urlopen(candidate, timeout=10) as result:
                    error_log = result.read().decode("utf-8", errors="replace")
                if error_log.strip():
                    break
            except Exception as exc:  # Try the address returned by Doris next.
                last_error = exc

        if not error_log.strip():
            raise RuntimeError(f"Could not read the Stream Load ErrorURL: {last_error}")

        show_sql("Content returned by ErrorURL", error_log)
        return error_log

    def wait_for_table_rows(
        self,
        table_name: str,
        expected_rows: int,
        *,
        timeout_seconds: int = 90,
    ) -> int:
        table_name = self._safe_table_name(table_name)
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            records = self._metadata_rows(f"SELECT COUNT(*) AS row_count FROM `{table_name}`")
            count = int(records[0]["row_count"])
            if count == expected_rows:
                return count
            if count > expected_rows:
                raise AssertionError(
                    f"{table_name} contains {count} rows; expected at most {expected_rows}."
                )
            time.sleep(1)
        raise TimeoutError(f"{table_name} did not reach {expected_rows} rows in time.")

    def routine_load_status(self, job_name: str) -> pd.DataFrame:
        job_name = self._safe_table_name(job_name)
        records = self._metadata_rows(f"SHOW ALL ROUTINE LOAD FOR `{job_name}`")
        if not records:
            raise RuntimeError(f"Routine Load job {job_name} was not found.")
        row = records[0]
        statistic_raw = row.get("Statistic", "{}")
        try:
            statistic = json.loads(str(statistic_raw))
        except json.JSONDecodeError:
            statistic = {}
        error_urls = str(row.get("ErrorLogUrls", "")).strip()
        frame = pd.DataFrame([
            {"job metric": "Name", "observed value": row.get("Name", job_name)},
            {"job metric": "State", "observed value": row.get("State", "not shown")},
            {"job metric": "Current tasks", "observed value": row.get("CurrentTaskNum", "not shown")},
            {"job metric": "Total rows", "observed value": statistic.get("totalRows", 0)},
            {"job metric": "Loaded rows", "observed value": statistic.get("loadedRows", 0)},
            {"job metric": "Error rows", "observed value": statistic.get("errorRows", 0)},
            {"job metric": "Unselected rows", "observed value": statistic.get("unselectedRows", 0)},
            {"job metric": "Error log", "observed value": "available" if error_urls not in {"", "[]"} else "none"},
            {"job metric": "State-change reason", "observed value": row.get("ReasonOfStateChanged", "") or "none"},
        ])
        show_frame("Routine Load job status", frame)
        show_log("Complete SHOW ROUTINE LOAD row", json.dumps(row, indent=2, default=str))
        return frame

    def wait_for_routine_state(
        self,
        job_name: str,
        expected_states: str | Sequence[str],
        *,
        timeout_seconds: int = 60,
    ) -> str:
        job_name = self._safe_table_name(job_name)
        states = {expected_states} if isinstance(expected_states, str) else set(expected_states)
        states = {str(state).upper() for state in states}
        include_history = bool(states & {"STOPPED", "CANCELLED"})
        show_statement = (
            f"SHOW ALL ROUTINE LOAD FOR `{job_name}`"
            if include_history
            else f"SHOW ROUTINE LOAD FOR `{job_name}`"
        )
        deadline = time.monotonic() + timeout_seconds
        last_state = "not shown"
        while time.monotonic() < deadline:
            records = self._metadata_rows(show_statement)
            if records:
                last_state = str(records[0].get("State", "not shown")).upper()
                if last_state in states:
                    return last_state
            time.sleep(1)
        raise TimeoutError(
            f"Routine Load job {job_name} remained in {last_state}; expected {sorted(states)}."
        )

    def stop_routine_if_exists(self, job_name: str | None) -> bool:
        """Stop a previous course Routine Load job before starting an isolated rerun."""
        if not job_name:
            return False
        job_name = self._safe_table_name(job_name)
        records = self._metadata_rows("SHOW ALL ROUTINE LOAD")
        matches = [row for row in records if str(row.get("Name", "")) == job_name]
        if not matches:
            return False
        terminal_states = {"STOPPED", "CANCELLED"}
        if any(str(row.get("State", "")).upper() not in terminal_states for row in matches):
            self.execute(f"STOP ROUTINE LOAD FOR `{job_name}`")
            self.wait_for_routine_state(job_name, "STOPPED")
        return True

    def kafka_produce_once(
        self,
        *,
        topic: str,
        script: str,
        expected_messages: int,
    ) -> int:
        if not re.fullmatch(r"[A-Za-z0-9._-]+", topic):
            raise ValueError(f"Unsafe Kafka topic name: {topic!r}")
        offset_command = [
            "docker", "exec", "kafka", "/opt/kafka/bin/kafka-get-offsets.sh",
            "--bootstrap-server", "kafka:29092", "--topic", topic,
        ]

        def message_count() -> int:
            result = run(offset_command, check=True)
            return sum(int(line.rsplit(":", 1)[1]) for line in result.stdout.splitlines() if ":" in line)

        before = message_count()
        if before == expected_messages:
            card(f"{expected_messages} existing messages were reused.", "skip", "Kafka fixture already present")
            return before
        if before != 0:
            raise RuntimeError(
                f"Kafka topic {topic} contains {before} messages; expected 0 or {expected_messages}. "
                "Begin a new Lab 3 run instead of appending an ambiguous partial fixture."
            )
        self.shell(script, title="Publish the JSON fixture to Kafka")
        after = message_count()
        if after != expected_messages:
            raise AssertionError(
                f"Kafka contains {after} messages after publishing; expected {expected_messages}."
            )
        return after

    def publish_kafka_batches(
        self,
        *,
        topic: str,
        fixture_path: str,
        job_name: str,
        target_table: str,
        batch_size: int = 256,
        poll_interval_seconds: float = 1.0,
        batch_pause_seconds: float = 2.0,
        timeout_seconds: int = 90,
    ) -> pd.DataFrame:
        """Publish real Kafka batches and render the producer/consumer timeline."""
        if not re.fullmatch(r"[A-Za-z0-9._-]+", topic):
            raise ValueError(f"Unsafe Kafka topic name: {topic!r}")
        job_name = self._safe_table_name(job_name)
        target_table = self._safe_table_name(target_table)
        if batch_size <= 0:
            raise ValueError("batch_size must be positive.")
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive.")
        if batch_pause_seconds < 0:
            raise ValueError("batch_pause_seconds cannot be negative.")

        fixture = (self.lab_dir / fixture_path).resolve()
        lines = [line for line in fixture.read_text(encoding="utf-8").splitlines() if line.strip()]
        expected_messages = len(lines)
        if expected_messages == 0:
            raise ValueError(f"{fixture.name} contains no Kafka messages.")

        offset_command = [
            "docker", "exec", "kafka", "/opt/kafka/bin/kafka-get-offsets.sh",
            "--bootstrap-server", "kafka:29092", "--topic", topic,
        ]

        def message_count() -> int:
            result = run(offset_command, check=True)
            return sum(
                int(line.rsplit(":", 1)[1])
                for line in result.stdout.splitlines()
                if ":" in line
            )

        def snapshot(stage: str, started_at: float) -> dict[str, object]:
            job_rows = self._metadata_rows(f"SHOW ROUTINE LOAD FOR `{job_name}`")
            if not job_rows:
                raise RuntimeError(f"Routine Load job {job_name} was not found.")
            job = job_rows[0]
            try:
                statistic = json.loads(str(job.get("Statistic", "{}")))
            except json.JSONDecodeError:
                statistic = {}
            target = self._metadata_rows(
                f"SELECT COUNT(*) AS row_count FROM `{target_table}`"
            )
            kafka_messages = message_count()
            routine_loaded = int(statistic.get("loadedRows", 0))
            return {
                "actor / action": stage,
                "Kafka published": kafka_messages,
                "waiting for Doris": max(0, kafka_messages - routine_loaded),
                "Doris committed": routine_loaded,
                "events_routine rows": int(target[0]["row_count"]),
                "errors": int(statistic.get("errorRows", 0)),
                "Routine Load state": str(job.get("State", "not shown")),
                "elapsed": f"{time.perf_counter() - started_at:.1f} s",
            }

        def progress_html(frame: pd.DataFrame) -> HTML:
            latest = frame.iloc[-1]
            headings = "".join(
                f"<th>{html.escape(str(column))}</th>" for column in frame.columns
            )
            rows = []
            for row in frame.itertuples(index=False, name=None):
                cells = "".join(
                    f"<td>{html.escape(str(value))}</td>" for value in row
                )
                rows.append(f"<tr>{cells}</tr>")
            pipeline = (
                '<div class="doris-flow" style="margin-bottom:12px">'
                '<div class="doris-flow-step"><strong>Notebook producer</strong>'
                f'{int(latest["Kafka published"]):,} of {expected_messages:,} messages published</div>'
                '<div class="doris-flow-arrow">→</div>'
                '<div class="doris-flow-step"><strong>Kafka topic</strong>'
                f'{int(latest["waiting for Doris"]):,} published messages awaiting Doris commit</div>'
                '<div class="doris-flow-arrow">→</div>'
                '<div class="doris-flow-step"><strong>Doris Routine Load</strong>'
                f'{int(latest["Doris committed"]):,} committed · '
                f'{html.escape(str(latest["Routine Load state"]))}</div>'
                '<div class="doris-flow-arrow">→</div>'
                '<div class="doris-flow-step"><strong>events_routine</strong>'
                f'{int(latest["events_routine rows"]):,} queryable rows</div>'
                '</div>'
            )
            return HTML(
                '<div class="doris-result">'
                '<div class="doris-result-title">Live producer-to-consumer pipeline</div>'
                f'{pipeline}'
                '<div class="doris-result-title">Producer and consumer timeline '
                f'<span class="doris-result-count">{len(frame)} snapshot(s)</span></div>'
                '<div class="doris-result-table-wrap"><table class="doris-table">'
                f'<thead><tr>{headings}</tr></thead><tbody>{"".join(rows)}</tbody>'
                '</table></div></div>'
            )

        existing = message_count()
        if existing > expected_messages:
            raise RuntimeError(
                f"Kafka topic {topic} contains {existing} messages; expected at most "
                f"{expected_messages}. Begin a new Lab 3 run."
            )

        started_at = time.perf_counter()
        snapshots = [snapshot("Notebook producer · ready", started_at)]
        frame = pd.DataFrame(snapshots)
        handle = display(progress_html(frame), display_id=True)

        def update_timeline(stage: str) -> dict[str, object]:
            observed = snapshot(stage, started_at)
            snapshots.append(observed)
            handle.update(progress_html(pd.DataFrame(snapshots)))
            return observed

        def wait_for_committed_rows(expected: int) -> None:
            deadline = time.monotonic() + timeout_seconds
            target_count = -1
            while time.monotonic() < deadline:
                time.sleep(poll_interval_seconds)
                observed = snapshot(f"Doris consumer · waiting for {expected}", started_at)
                target_count = int(observed["events_routine rows"])
                if target_count >= expected:
                    observed["actor / action"] = f"Doris consumer · committed {expected}"
                    snapshots.append(observed)
                    handle.update(progress_html(pd.DataFrame(snapshots)))
                    return
                snapshots.append(observed)
                handle.update(progress_html(pd.DataFrame(snapshots)))
            raise TimeoutError(
                f"{target_table} reached {target_count} rows after Kafka contained "
                f"{expected} messages; expected at least {expected}."
            )

        published = existing
        if published:
            update_timeline(f"Kafka topic · found {published} existing messages")
            wait_for_committed_rows(published)

        while published < expected_messages:
            batch_end = min(published + batch_size, expected_messages)
            payload = "\n".join(lines[published:batch_end]) + "\n"
            command = [
                "docker", "exec", "-i", "kafka",
                "/opt/kafka/bin/kafka-console-producer.sh",
                "--bootstrap-server", "kafka:29092", "--topic", topic,
            ]
            result = subprocess.run(
                command,
                input=payload,
                text=True,
                capture_output=True,
                timeout=60,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"Kafka producer failed for messages {published + 1}–{batch_end}: "
                    f"{result.stderr.strip()}"
                )

            published = batch_end
            update_timeline(f"Notebook producer · published {published}")
            wait_for_committed_rows(batch_end)
            if published < expected_messages and batch_pause_seconds:
                time.sleep(batch_pause_seconds)

        final = snapshots[-1]
        if int(final["events_routine rows"]) != expected_messages:
            raise AssertionError(
                f"{target_table} contains {final['events_routine rows']} rows; "
                f"expected {expected_messages}."
            )
        return pd.DataFrame(snapshots)

    @staticmethod
    def _workflow_html(
        title: str,
        steps: Mapping[int, str],
        current: int,
        state: str,
        detail: str,
    ) -> HTML:
        total = max(steps)
        if state == "success":
            completed = total
        else:
            completed = max(0, current - 1)
        percent = round(completed / total * 100)
        items = []
        for number in range(1, total + 1):
            if state == "success" or number < current:
                item_state = "success"
                marker = "✓"
            elif number == current:
                item_state = "failure" if state == "failure" else "running"
                marker = "!" if state == "failure" else str(number)
            else:
                item_state = "pending"
                marker = str(number)
            item_detail = detail if number == current and state != "success" else ""
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
            '</div><div class="doris-workflow-list">'
            f'{"".join(items)}</div></div>'
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
        image_activity_reported = False
        assert process.stdout is not None
        for line in process.stdout:
            lines.append(line)
            clean = line.strip()
            step_match = re.match(r"^\[(\d+)/(\d+)\]\s+(.+)$", clean)
            force_update = False
            if step_match:
                current = int(step_match.group(1))
                detail = step_match.group(3)
                force_update = True
                image_activity_reported = False
            elif clean:
                if current == 4 and any(
                    token in clean
                    for token in ("Pulling", "Downloading", "Download complete", "Pull complete")
                ):
                    detail = clean
                    image_activity_reported = True
                elif current != 4 or not image_activity_reported:
                    detail = clean
            now = time.monotonic()
            if force_update or now - last_update >= 0.35:
                handle.update(self._workflow_html(title, steps, current, "running", detail))
                last_update = now

        return_code = process.wait()
        elapsed = time.perf_counter() - started_at
        output = "".join(lines)
        result = subprocess.CompletedProcess(
            ["/bin/bash", "-lc", script.strip()], return_code, output, ""
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

    def connect(
        self,
        *,
        container: str = "doris",
        host: str = "127.0.0.1",
        port: int = 9030,
    ):
        wait_for_health(container, timeout_seconds=300, report=False)
        self.DORIS_CONTAINER = container
        self.connection = connect_doris(host=host, port=port)
        return self.connection

    def prepare_environment(self):
        total_steps = 6

        progress_step(1, total_steps, "Check the host and Docker daemon")
        system = platform.system()
        machine = platform.machine().lower()
        supported = (system == "Darwin" and machine in {"arm64", "aarch64"}) or (
            system == "Linux" and machine in {"x86_64", "amd64"}
        )
        if not supported:
            self._failure(
                "Unsupported course host",
                f"Found {system} {machine}. This course supports macOS Apple Silicon and Linux x86_64.",
            )
            return None

        docker_ready, docker_output = docker_preflight()
        if not docker_ready:
            remedy = (
                "Start Docker Desktop, wait until its engine is running, then rerun this cell."
                if system == "Darwin"
                else "Start Docker Engine (commonly: sudo systemctl start docker), then rerun this cell."
            )
            self._failure("Docker daemon is not running", remedy, docker_output)
            return None
        show_log("Docker client and server", docker_output)
        docker_info = run(
            [
                "docker", "info", "--format",
                "cpus={{.NCPU}} memory={{.MemTotal}} os={{.OperatingSystem}} arch={{.Architecture}}",
            ],
            check=False,
        )
        show_log("Docker resources", docker_info.stdout or docker_info.stderr)
        card(f"Supported host and running Docker daemon: {system} {machine}", "ok")

        progress_step(2, total_steps, "Check required host ports")
        port_rows = []
        for port in (8030, 8040, 9030, 3000):
            with socket.socket() as probe:
                probe.settimeout(0.25)
                in_use = probe.connect_ex(("127.0.0.1", port)) == 0
            port_rows.append({
                "host_port": port,
                "purpose": "optional Metabase" if port == 3000 else "Doris",
                "status": "in use" if in_use else "available",
            })
        show_frame("Host port check", pd.DataFrame(port_rows))

        existing = container_inspect(self.DORIS_CONTAINER)
        busy_ports = [
            row["host_port"] for row in port_rows
            if row["purpose"] == "Doris" and row["status"] == "in use"
        ]
        if existing is None and busy_ports:
            self._failure(
                "Required port is unavailable",
                f"Another process is using: {', '.join(map(str, busy_ports))}. Stop it or change the Lab ports.",
            )
            return None
        card("Required Doris ports are available or belong to the reusable course container.", "ok")

        progress_step(3, total_steps, "Create or reuse Docker storage")
        ensure_network(self.DORIS_NETWORK)
        ensure_volume(self.FE_VOLUME)
        ensure_volume(self.BE_VOLUME)

        progress_step(4, total_steps, "Pull the pinned Doris image", self.DORIS_IMAGE)
        pull = run(
            ["docker", "pull", self.DORIS_IMAGE],
            check=False,
            stream=True,
            timeout=1800,
        )
        if pull.returncode != 0:
            self._failure(
                "Doris image pull failed",
                "Check network/proxy access to Docker Hub, then rerun this cell.",
                pull.stdout,
            )
            return None
        card(f"Pinned course image is ready: {self.DORIS_IMAGE}", "ok")

        progress_step(5, total_steps, "Start Doris and wait for health")
        existing = container_inspect(self.DORIS_CONTAINER)
        if existing is None:
            command = [
                "docker", "run", "-d", "--name", self.DORIS_CONTAINER,
                "--network", self.DORIS_NETWORK,
                "-p", "127.0.0.1:9030:9030",
                "-p", "127.0.0.1:8030:8030",
                "-p", "127.0.0.1:8040:8040",
                "-v", f"{self.FE_VOLUME}:/opt/apache-doris/fe/doris-meta",
                "-v", f"{self.BE_VOLUME}:/opt/apache-doris/be/storage",
                self.DORIS_IMAGE,
            ]
            started = run(command, check=False, stream=True)
            if started.returncode != 0:
                self._failure(
                    "Doris container did not start",
                    "Open the Docker output, correct the conflict, and rerun this cell.",
                    started.stdout,
                )
                return None
        else:
            expected_ports = {
                "9030/tcp": ("127.0.0.1", "9030"),
                "8030/tcp": ("127.0.0.1", "8030"),
                "8040/tcp": ("127.0.0.1", "8040"),
            }
            bindings = existing["HostConfig"]["PortBindings"]
            actual_ports = {
                container_port: (
                    bindings[container_port][0]["HostIp"],
                    bindings[container_port][0]["HostPort"],
                )
                for container_port in expected_ports
                if container_port in bindings and bindings[container_port]
            }
            expected_mounts = {
                "/opt/apache-doris/fe/doris-meta": self.FE_VOLUME,
                "/opt/apache-doris/be/storage": self.BE_VOLUME,
            }
            actual_mounts = {
                mount["Destination"]: mount.get("Name") for mount in existing["Mounts"]
            }
            attached_networks = set(existing["NetworkSettings"]["Networks"])
            matches = (
                existing["Config"]["Image"] == self.DORIS_IMAGE
                and actual_ports == expected_ports
                and all(actual_mounts.get(path) == name for path, name in expected_mounts.items())
                and self.DORIS_NETWORK in attached_networks
            )
            if not matches:
                self._failure(
                    "Existing container conflict",
                    "A container named doris exists but does not match this Lab's image, ports, volumes, or network. It was left unchanged.",
                )
                return None
            if existing["State"]["Status"] != "running":
                started = run(
                    ["docker", "start", self.DORIS_CONTAINER],
                    check=False,
                    stream=True,
                )
                if started.returncode != 0:
                    self._failure(
                        "Existing Doris container did not start",
                        "Inspect the Docker output and container logs, then rerun this cell.",
                        started.stdout,
                    )
                    return None
            else:
                card(f"Reusing running container {self.DORIS_CONTAINER}", "ok")

        try:
            wait_for_health(self.DORIS_CONTAINER, timeout_seconds=300)
        except Exception as exc:
            self._failure("Doris health check failed", str(exc))
            return None
        state = container_inspect(self.DORIS_CONTAINER)
        show_frame("Doris container", pd.DataFrame([{
            "container": self.DORIS_CONTAINER,
            "image": state["Config"]["Image"],
            "status": state["State"]["Status"],
            "health": state["State"]["Health"]["Status"],
        }]))

        progress_step(6, total_steps, "Connect to FE and inspect FE/BE")
        self.connection = connect_doris()
        self.sql(
            "SELECT VERSION() AS doris_version, CURRENT_USER() AS current_user",
            title="Connection",
        )
        self.sql("SHOW FRONTENDS", title="Frontend status")
        self.sql("SHOW BACKENDS", title="Backend status")
        card("Environment ready: Doris is healthy and both FE and BE are available.", "ok")
        return self.connection

    def load_s3_credentials(self, filename: str = "lab1_secrets.env") -> bool:
        secret_path = self.lab_dir / filename
        try:
            secrets = load_env_file(secret_path)
        except (FileNotFoundError, ValueError) as exc:
            self._failure("S3 credential file is unavailable", str(exc))
            return False
        access_key = secrets.get("S3_READ_ONLY_ACCESS_KEY", "")
        secret_key = secrets.get("S3_READ_ONLY_SECRET_KEY", "")
        if not access_key or not secret_key:
            self._failure(
                "S3 credentials are incomplete",
                f"Fill both credential fields in {secret_path.name}, then rerun this cell.",
            )
            return False
        self._s3_access_key = access_key
        self._s3_secret_key = secret_key
        self._source_tvf = s3_tvf(self.S3_CONFIG, access_key, secret_key)
        return True

    def preview_s3(self, statement: str):
        if not self.load_s3_credentials():
            return None
        result = self.sql(statement, title="Ten remote event rows")
        if len(result) != 10:
            raise AssertionError(f"Expected a 10-row preview; Doris returned {len(result)} rows.")
        return result

    def load_events_once(self, statement: str):
        connection = self._require_connection()
        # This is a rerun guard, not a learner-facing query result.
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS row_count FROM events")
            current_count = int(cursor.fetchone()["row_count"])
        if current_count == self.EXPECTED_ROW_COUNT:
            self._baseline_load_skipped = True
            return current_count
        if current_count != 0:
            raise RuntimeError(
                f"events contains {current_count:,} rows; expected 0 or {self.EXPECTED_ROW_COUNT:,}. "
                "The Lab will not append into an unexpected table."
            )
        self._baseline_load_skipped = False
        return self.execute(statement)

    def verify_baseline(self, statement: str):
        result = self.sql(statement, title="Load validation")
        actual = result.iloc[0]
        checks = {
            "row count": int(actual["row_count"]) == self.EXPECTED_ROW_COUNT,
            "minimum event time": str(actual["min_event_time"]) == self.EXPECTED_MIN_TIME,
            "maximum event time": str(actual["max_event_time"]) == self.EXPECTED_MAX_TIME,
        }
        failed = [name for name, passed in checks.items() if not passed]
        if failed:
            raise AssertionError("Baseline validation failed: " + ", ".join(failed))
        if getattr(self, "_baseline_load_skipped", False):
            message = (
                f"Baseline ready: {self.EXPECTED_ROW_COUNT:,} existing rows passed validation; "
                "the import was skipped on this safe rerun."
            )
        else:
            message = f"Baseline ready: {self.EXPECTED_ROW_COUNT:,} rows were loaded and validated."
        card(message, "ok")
        return result

    def verify_recovery(self, statement: str):
        result = self.sql(statement, title="Persistence check")
        recovered = int(result.iloc[0]["recovered_rows"])
        if recovered != self.EXPECTED_ROW_COUNT:
            raise AssertionError(
                f"Recovered {recovered:,} rows; expected {self.EXPECTED_ROW_COUNT:,}."
            )
        card("The events table and all baseline rows survived the restart.", "ok")
        return result

    def verify_event_counts(self, statement: str):
        result = self.sql(statement, title="Event funnel totals")
        actual = {row.event_type: int(row.event_count) for row in result.itertuples()}
        if actual != self.EXPECTED_EVENT_COUNTS:
            raise AssertionError(
                f"Validation failed: event counts {actual!r} do not match the expected values "
                f"{self.EXPECTED_EVENT_COUNTS!r}."
            )
        actual_revenue = sum(Decimal(str(row.total_revenue)) for row in result.itertuples())
        if actual_revenue != self.EXPECTED_TOTAL_REVENUE:
            raise AssertionError(
                f"Validation failed: total revenue is {actual_revenue}, while the expected value "
                f"is {self.EXPECTED_TOTAL_REVENUE}."
            )
        return result

    def restart_and_verify(self) -> None:
        connection = self._require_connection()
        connection.close()
        run(["docker", "stop", self.DORIS_CONTAINER], show=True, timeout=180)
        run(["docker", "start", self.DORIS_CONTAINER], show=True)
        wait_for_health(self.DORIS_CONTAINER, timeout_seconds=300)
        self.connection = connect_doris()
        self.sql("USE doris_course")
        recovered = self.sql(
            "SELECT COUNT(*) AS recovered_rows FROM events",
            title="Persistence check",
        )
        if int(recovered.iloc[0]["recovered_rows"]) != self.EXPECTED_ROW_COUNT:
            raise AssertionError("The recovered events row count does not match the baseline.")
        card("Database metadata and all baseline rows survived restart. Module 2 can reuse them.", "ok")
