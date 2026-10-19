from __future__ import annotations

import html
import base64
import csv
import http.client
import io
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
import urllib.error
import uuid
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import pandas as pd
import pymysql
from IPython.display import HTML, Javascript, display


# Every notebook uses the course root as its runtime workspace, even when the
# notebook file itself lives several module directories below it.
LAB_DIR = Path(__file__).resolve().parent.parent


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
      table.doris-table td.doris-empty {color:#64748b;font-style:italic}
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


def is_null(value: object) -> bool:
    """Return True for SQL NULL in every form pandas may have converted it to."""
    if value is None or value is pd.NA or value is pd.NaT:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def result_frame(rows: Sequence, columns: Sequence[str]) -> pd.DataFrame:
    """Build a result DataFrame that keeps SQL NULL and integer values intact.

    pandas stores an integer column that contains NULL as float64, so 10 would
    display as 10.0. Such columns use the nullable Int64 dtype instead.
    """
    names = list(columns)
    records = [
        [row.get(name) for name in names] if isinstance(row, Mapping) else list(row)
        for row in rows
    ]
    data = {}
    for position in range(len(names)):
        values = [record[position] for record in records]
        present = [value for value in values if value is not None]
        if (
            present
            and len(present) < len(values)
            and all(type(value) is int and -2**63 <= value < 2**63 for value in present)
        ):
            data[position] = pd.array(values, dtype="Int64")
        else:
            data[position] = values
    frame = pd.DataFrame(data, index=pd.RangeIndex(len(records)))
    frame.columns = names
    return frame


def show_frame(title: str, frame: pd.DataFrame, *, final: bool = False) -> None:
    headings = "".join(f"<th>{html.escape(str(column))}</th>" for column in frame.columns)
    body_rows = []
    for row in frame.itertuples(index=False, name=None):
        cells = "".join(
            f"<td>{html.escape('NULL' if is_null(value) else str(value))}</td>" for value in row
        )
        body_rows.append(f"<tr>{cells}</tr>")
    if not body_rows and len(frame.columns):
        body_rows.append(
            f'<tr><td class="doris-empty" colspan="{len(frame.columns)}">No rows returned.</td></tr>'
        )
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


class ReturnLater(RuntimeError):
    """Stop a cell whose observation needs the real clock to advance first.

    The card shown before raising says when to come back. Raising keeps
    "Run All" from continuing into checks that cannot pass yet, and IPython
    renders this exception as one line instead of a traceback.
    """

    def _render_traceback_(self) -> list[str]:
        return [f"Stopped on purpose: {self}"]


def mask_secrets(text: str, secrets: Sequence[str] = ()) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "••••••••")
    return text


def report_sql_error(title: str | None, statement: str, error: Exception, *,
                     secrets: Sequence[str] = ()) -> str:
    """Show a failed statement as a short card and shorten its notebook traceback.

    The full statement and server response stay available in a collapsed log.
    IPython renders an exception through ``_render_traceback_`` when the
    exception provides one, so the learner sees one line instead of the
    PyMySQL call stack. The original exception is still raised by the caller.
    """
    message = str(error.args[1]) if len(error.args) > 1 else str(error)
    # Doris wraps server messages as "errCode = 2, detailMessage = <message>".
    summary = mask_secrets(message.split("detailMessage =", 1)[-1].strip(), secrets)
    summary = summary or type(error).__name__
    card(summary, "fail", f"{title or 'SQL statement'} failed")
    show_log(
        "Statement and full error",
        mask_secrets(f"{statement.strip()}\n\n{type(error).__name__}: {error}", secrets),
    )
    error._render_traceback_ = lambda: [f"{type(error).__name__}: {summary}"]
    return summary


def sql(connection, statement: str, *, title: str | None = None,
        show_statement: bool = True, final: bool = False,
        columns: Sequence[str] | None = None, quiet_success: bool = False,
        display_statement: str | None = None, show_errors: bool = True,
        secrets: Sequence[str] = ()):
    """Run one statement and display its result.

    A statement that returns a result set gives a DataFrame, also when the
    result has no rows; any other statement gives the affected-row count.
    ``display_statement`` replaces the executed text in error details, so
    credentials expanded into ``statement`` are never shown.
    """
    clean = statement.strip()
    if show_statement:
        show_sql(title or "SQL", clean)
    with connection.cursor() as cursor:
        try:
            cursor.execute(clean)
            rows = cursor.fetchall() if cursor.description else []
        except pymysql.MySQLError as error:
            if show_errors:
                report_sql_error(title, display_statement or clean, error, secrets=secrets)
            raise
        description = cursor.description
        affected = cursor.rowcount
    if description:
        names = (
            list(rows[0]) if rows and isinstance(rows[0], Mapping)
            else [column[0] for column in description]
        )
        frame = result_frame(rows, names)
        if columns:
            available = [column for column in columns if column in frame.columns]
            if available:
                frame = frame.loc[:, available]
        if len(frame) or not quiet_success:
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
        connection_host: str = "127.0.0.1",
        connection_port: int = 9030,
        profile_http_host: str | None = None,
        profile_http_port: int = 8030,
        ready_title: str = "Lab tools are ready",
        ready_message: str = "You can now continue to Section 1 and run the remaining cells in order.",
    ) -> None:
        self.lab_dir = (lab_dir or LAB_DIR).resolve()
        self.connection = None
        self._connection_host = connection_host
        self._connection_port = connection_port
        self._profile_http_host = profile_http_host or connection_host
        self._profile_http_port = profile_http_port
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

    def _secrets(self) -> tuple[str, ...]:
        keys = (getattr(self, "_s3_access_key", None), getattr(self, "_s3_secret_key", None))
        return tuple(key for key in keys if key)

    def _require_connection(self):
        if self.connection is None:
            try:
                with socket.create_connection(
                    (self._connection_host, self._connection_port), timeout=1
                ):
                    pass
                self.connection = pymysql.connect(
                    host=self._connection_host,
                    port=self._connection_port,
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
                    "No running Doris server is reachable on "
                    f"{self._connection_host}:{self._connection_port}. "
                    "Start this module's Doris environment if it is stopped, then rerun the "
                    "Notebook initialization cell. A kernel restart clears the Python "
                    "connection, but it does not delete Docker containers, named volumes, "
                    "or imported tables."
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
        executable, visible = self._expand_sql(statement.strip())
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
            display_statement=visible,
            secrets=self._secrets(),
        )

    def query(self, statement: str):
        """Execute a SQL query and return all rows without displaying them."""
        connection = self._require_connection()
        executable, visible = self._expand_sql(statement.strip())
        with connection.cursor() as cursor:
            try:
                cursor.execute(executable)
                rows = cursor.fetchall() if cursor.description else []
            except pymysql.MySQLError as error:
                report_sql_error(None, visible, error, secrets=self._secrets())
                raise
            if cursor.description is None:
                raise ValueError("query() requires a statement that returns rows.")
            columns = [column[0] for column in cursor.description]
        if rows and isinstance(rows[0], Mapping):
            columns = list(rows[0])
        return result_frame(rows, columns)

    def compare_queries(
        self,
        left_sql: str,
        right_sql: str,
        *,
        left_label: str,
        right_label: str,
        title: str = "Query-result comparison",
    ):
        """Run two SQL statements, summarize their full row comparison, and return both results."""
        from collections import Counter

        left = self.query(left_sql)
        right = self.query(right_sql)
        differing_rows = None
        if list(left.columns) == list(right.columns):
            left_rows = Counter(left.itertuples(index=False, name=None))
            right_rows = Counter(right.itertuples(index=False, name=None))
            differing_rows = sum((left_rows - right_rows).values())
            differing_rows += sum((right_rows - left_rows).values())
        show_frame(title, pd.DataFrame([{
            "left_result": left_label,
            "left_rows": len(left.index),
            "right_result": right_label,
            "right_rows": len(right.index),
            "differing_rows": differing_rows if differing_rows is not None else "column mismatch",
        }]))
        self.assert_same_rows(left, right)
        return left, right

    def summarize_query_values(
        self,
        left_sql: str,
        right_sql: str,
        *,
        left_label: str,
        right_label: str,
        value_column: str,
        values: Sequence[object],
        metrics: Sequence[str],
        title: str,
    ):
        """Run two SQL statements and summarize selected values from each result."""
        left = self.query(left_sql)
        right = self.query(right_sql)
        rows = []
        for label, frame in ((left_label, left), (right_label, right)):
            if value_column not in frame.columns:
                raise ValueError(f"Value column {value_column!r} is missing from the result.")
            for value in values:
                focused = frame.loc[frame[value_column] == value]
                row = {
                    "result": label,
                    value_column: value,
                    "groups": len(focused.index),
                }
                for metric in metrics:
                    if metric not in frame.columns:
                        raise ValueError(f"Metric {metric!r} is missing from the result.")
                    row[metric] = focused[metric].sum()
                rows.append(row)
        show_frame(title, pd.DataFrame(rows))
        return left, right

    def execute(self, statement: str, *, show_errors: bool = True) -> int:
        connection = self._require_connection()
        executable, visible = self._expand_sql(statement.strip())
        return sql(
            connection,
            executable,
            show_statement=False,
            quiet_success=True,
            display_statement=visible,
            show_errors=show_errors,
            secrets=self._secrets(),
        )

    def insert(
        self,
        statement: str,
        *,
        title: str = "Insert completed",
        low_memory_s3: bool = False,
        expected_rows: int | None = None,
        show: bool = True,
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
        if expected_rows is not None and affected != expected_rows:
            raise AssertionError(
                f"{title} affected {affected:,} rows; expected {expected_rows:,}."
            )
        elapsed = time.perf_counter() - started_at
        if show:
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
        title: str | None = None,
        low_memory_s3: bool = False,
    ) -> int:
        """Populate a derived course table without duplicating rows on rerun."""
        table_name = self._safe_table_name(table_name)
        expected_rows = expected_rows or self.EXPECTED_ROW_COUNT
        if not self._metadata_rows(f"SHOW TABLES LIKE '{table_name}'"):
            raise RuntimeError(
                f"{table_name} does not exist. Run its CREATE TABLE cell first."
            )
        partitions = self._metadata_rows(f"SHOW PARTITIONS FROM `{table_name}`")
        if not partitions:
            raise RuntimeError(f"{table_name} has no visible Partition metadata.")
        visible_versions = [int(row["VisibleVersion"]) for row in partitions]
        metadata_rows = sum(int(row.get("RowCount", 0)) for row in partitions)
        if any(version > 1 for version in visible_versions):
            if metadata_rows > 0 and metadata_rows != expected_rows:
                raise RuntimeError(
                    f"{table_name} metadata reports {metadata_rows:,} rows; expected "
                    f"{expected_rows:,}. Explicitly reset this Module table before retrying."
                )
            card(
                f"Reused the committed {expected_rows:,}-row load; no INSERT was executed.",
                "skip",
                title or f"Reuse {table_name}",
            )
            return expected_rows
        if metadata_rows > 0:
            raise RuntimeError(
                f"{table_name} metadata reports {metadata_rows:,} rows; expected 0 or "
                f"{expected_rows:,}. Explicitly reset this Module table before retrying."
            )
        return self.insert(
            statement,
            title=title or f"Load {table_name}",
            low_memory_s3=low_memory_s3,
            expected_rows=expected_rows,
        )

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
    def _capacity_bytes(value: object) -> float:
        units = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
        match = re.match(r"\s*([0-9.]+)\s*([KMGT]?B)?", str(value), re.IGNORECASE)
        if not match:
            return 0
        return float(match.group(1)) * units.get((match.group(2) or "B").upper(), 1)

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
            {"design choice": "Table model", "resolved value": f"{key_match.group(1).title()} Key model"},
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

    def tablet_replica_placement(
        self,
        table_name: str,
        *,
        title: str | None = None,
        show: bool = True,
    ) -> pd.DataFrame:
        """Show one compact row per logical tablet and its physical BE replicas."""
        table_name = self._safe_table_name(table_name)
        tablets = self._metadata_rows(f"SHOW TABLETS FROM `{table_name}`")
        backends = self._metadata_rows("SHOW BACKENDS")
        alive_by_id = {
            str(row["BackendId"]): str(row["Alive"]).lower() == "true" for row in backends
        }
        grouped: dict[str, list[dict[str, object]]] = {}
        for row in tablets:
            grouped.setdefault(str(row["TabletId"]), []).append(row)
        rows = []
        for tablet_id, replicas in sorted(grouped.items(), key=lambda item: int(item[0])):
            backend_ids = sorted(str(row["BackendId"]) for row in replicas)
            alive = sum(alive_by_id.get(backend_id, False) for backend_id in backend_ids)
            versions = [int(row["Version"]) for row in replicas]
            target_version = max(versions)
            complete = sum(
                str(row.get("State", "")).upper() == "NORMAL"
                and int(row["Version"]) == target_version
                and int(row["Version"]) == int(row["LstSuccessVersion"])
                and int(row["LstFailedVersion"]) == -1
                for row in replicas
            )
            rows.append({
                "tablet_id": tablet_id,
                "replicas": len(replicas),
                "alive_replicas": alive,
                "version_complete": complete,
                "version": self._number_range(versions),
                "backend_ids": ", ".join(backend_ids),
            })
        frame = pd.DataFrame(rows)
        if show:
            show_frame(title or f"{table_name} tablet-to-replica placement", frame)
        return frame

    def tablet_replica_health_summary(
        self,
        table_name: str,
        *,
        title: str | None = None,
        expected_tablets: int | None = None,
        expected_replicas: int | None = None,
        expected_alive: int | None = None,
        expected_complete: int | None = None,
    ) -> pd.DataFrame:
        """Summarize replica records and currently alive copies for one table."""
        placement = self.tablet_replica_placement(table_name, show=False)
        checks = (
            (expected_tablets, len(placement.index), "logical tablets"),
            (expected_replicas, placement["replicas"].astype(int), "replicas per tablet"),
            (expected_alive, placement["alive_replicas"].astype(int), "alive replicas per tablet"),
            (
                expected_complete,
                placement["version_complete"].astype(int),
                "version-complete replicas per tablet",
            ),
        )
        for expected, observed, label in checks:
            if expected is None:
                continue
            matches = observed == expected
            if hasattr(matches, "all"):
                matches = matches.all()
            if not matches:
                raise AssertionError(
                    f"{table_name} did not have {expected} {label}; "
                    f"observed {observed!r}."
                )
        backend_counts = [
            len({value.strip() for value in str(ids).split(",") if value.strip()})
            for ids in placement["backend_ids"]
        ]
        frame = pd.DataFrame([{
            "table": self._safe_table_name(table_name),
            "tablets": len(placement.index),
            "replicas / tablet": self._number_range(placement["replicas"].astype(int).tolist()),
            "BE nodes / tablet": self._number_range(backend_counts),
            "alive replicas / tablet": self._number_range(
                placement["alive_replicas"].astype(int).tolist()
            ),
            "version-complete / tablet": self._number_range(
                placement["version_complete"].astype(int).tolist()
            ),
        }])
        show_frame(title or f"{table_name} replica health", frame)
        return frame

    def tablet_replica_backend_summary(
        self,
        table_name: str,
        *,
        title: str | None = None,
    ) -> pd.DataFrame:
        """Show whether each BE has caught up every replica of one table."""
        table_name = self._safe_table_name(table_name)
        tablets = self._metadata_rows(f"SHOW TABLETS FROM `{table_name}`")
        backends = self._metadata_rows("SHOW BACKENDS")
        if not tablets:
            raise RuntimeError(f"SHOW TABLETS returned no rows for {table_name}.")

        alive_by_id = {
            str(row["BackendId"]): str(row["Alive"]).lower() == "true"
            for row in backends
        }
        target_by_tablet: dict[str, int] = {}
        for row in tablets:
            tablet_id = str(row["TabletId"])
            target_by_tablet[tablet_id] = max(
                target_by_tablet.get(tablet_id, -1), int(row["Version"])
            )

        replicas_by_backend: dict[str, list[dict[str, object]]] = {}
        for row in tablets:
            replicas_by_backend.setdefault(str(row["BackendId"]), []).append(row)

        rows = []
        for backend_id, replicas in sorted(
            replicas_by_backend.items(), key=lambda item: int(item[0])
        ):
            current = sum(
                str(row.get("State", "")).upper() == "NORMAL"
                and int(row["Version"]) == target_by_tablet[str(row["TabletId"])]
                and int(row["Version"]) == int(row["LstSuccessVersion"])
                and int(row["LstFailedVersion"]) == -1
                for row in replicas
            )
            versions = [int(row["Version"]) for row in replicas]
            rows.append({
                "backend_id": backend_id,
                "alive": alive_by_id.get(backend_id, False),
                "stored replicas": len(replicas),
                "current-version replicas": current,
                "replica versions": self._number_range(versions),
            })

        frame = pd.DataFrame(rows)
        show_frame(title or f"{table_name} replica versions by BE", frame)
        return frame

    def wait_for_tablet_rows(
        self,
        table_name: str,
        *,
        expected_rows: int,
        timeout_seconds: int = 180,
    ) -> None:
        """Validate committed rows immediately, then wait only for tablet reports."""
        table_name = self._safe_table_name(table_name)
        if not self._metadata_rows(f"SHOW TABLES LIKE '{table_name}'"):
            raise RuntimeError(
                f"{table_name} is unavailable. Create the Module table and complete "
                "its insert before checking Tablet metadata."
            )
        query_rows = int(
            self._metadata_rows(
                f"SELECT COUNT(*) AS row_count FROM `{table_name}`"
            )[0]["row_count"]
        )
        if query_rows != expected_rows:
            raise AssertionError(
                f"{table_name} contains {query_rows:,} committed rows; expected "
                f"{expected_rows:,}. Complete the preceding insert cell first."
            )

        deadline = time.monotonic() + timeout_seconds
        metadata_rows = None
        while time.monotonic() < deadline:
            tablets = self._metadata_rows(f"SHOW TABLETS FROM `{table_name}`")
            per_tablet: dict[str, int] = {}
            for row in tablets:
                tablet_id = str(row["TabletId"])
                # SHOW TABLETS returns one row per replica. Replica statistics are
                # reported asynchronously, so an earlier row can temporarily be
                # older than another replica of the same logical tablet.
                per_tablet[tablet_id] = max(
                    per_tablet.get(tablet_id, 0), int(row["RowCount"])
                )
            metadata_rows = sum(per_tablet.values())
            if metadata_rows == expected_rows:
                return
            time.sleep(2)
        raise TimeoutError(
            f"{table_name} contains the expected {query_rows:,} committed rows, but "
            f"Tablet metadata reported {metadata_rows}; expected {expected_rows:,} "
            f"within {timeout_seconds} seconds."
        )

    def wait_for_replica_health(
        self,
        table_name: str,
        *,
        expected_alive: int,
        expected_complete: int,
        timeout_seconds: int = 120,
    ) -> pd.DataFrame:
        """Wait until every tablet has the requested alive and version-complete copies."""
        deadline = time.monotonic() + timeout_seconds
        placement = pd.DataFrame()
        while time.monotonic() < deadline:
            placement = self.tablet_replica_placement(table_name, show=False)
            if (
                not placement.empty
                and (placement["alive_replicas"].astype(int) == expected_alive).all()
                and (placement["version_complete"].astype(int) == expected_complete).all()
            ):
                return placement
            time.sleep(1)
        raise TimeoutError(
            f"Replica health for {table_name} did not reach alive={expected_alive}, "
            f"version_complete={expected_complete}; last placement={placement.to_dict('records')!r}"
        )

    def wait_for_node_state(
        self,
        statement: str,
        *,
        expected_total: int,
        expected_alive: int,
        expected_masters: int | None = None,
        expected_roles: Sequence[str] | None = None,
        require_same_version: bool = False,
        timeout_seconds: int = 120,
        title: str | None = None,
        show: bool = True,
    ) -> pd.DataFrame:
        """Poll SHOW FRONTENDS or SHOW BACKENDS until a bounded topology state appears."""
        normalized = " ".join(statement.upper().split())
        if normalized not in {"SHOW FRONTENDS", "SHOW BACKENDS"}:
            raise ValueError("Node state polling accepts SHOW FRONTENDS or SHOW BACKENDS only.")
        deadline = time.monotonic() + timeout_seconds
        rows: list[dict[str, object]] = []
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                rows = self._metadata_rows(normalized)
                last_error = None
            except Exception as exc:
                # FE election can briefly reject or forward metadata statements
                # to the former Master. Retry on the same published FE endpoint.
                last_error = exc
                try:
                    self._require_connection().ping(reconnect=True)
                except Exception:
                    self.connection = None
                time.sleep(1)
                continue
            alive = sum(str(row.get("Alive", "")).lower() == "true" for row in rows)
            masters = sum(str(row.get("IsMaster", "")).lower() == "true" for row in rows)
            roles_ready = (
                expected_roles is None
                or {str(row.get("Role", "")) for row in rows} == set(expected_roles)
            )
            versions = {str(row.get("Version", "")) for row in rows}
            versions_ready = not require_same_version or (
                len(versions) == 1 and "" not in versions and "NULL" not in versions
            )
            if (
                len(rows) == expected_total
                and alive == expected_alive
                and (expected_masters is None or masters == expected_masters)
                and roles_ready
                and versions_ready
            ):
                break
            time.sleep(1)
        else:
            raise TimeoutError(
                f"{normalized} did not reach total={expected_total}, alive={expected_alive}, "
                f"masters={expected_masters}, roles={expected_roles}, "
                f"same_version={require_same_version}; last rows={rows!r}; "
                f"last error={last_error!r}"
            )
        frame = pd.DataFrame(rows)
        columns = (
            ["Name", "Host", "Role", "IsMaster", "Join", "Alive", "Version"]
            if normalized == "SHOW FRONTENDS"
            else ["BackendId", "Host", "Alive", "SystemDecommissioned", "TabletNum", "Version"]
        )
        frame = frame[[column for column in columns if column in frame.columns]]
        if show:
            show_frame(title or normalized.title(), frame)
        return frame

    def wait_for_backend_storage(
        self,
        *,
        expected_backends: int,
        timeout_seconds: int = 120,
        title: str = "BE storage paths are ready",
        show: bool = True,
    ) -> pd.DataFrame:
        """Wait until every live BE has reported nonzero local storage capacity."""
        deadline = time.monotonic() + timeout_seconds
        rows: list[dict[str, object]] = []
        while time.monotonic() < deadline:
            rows = self._metadata_rows("SHOW BACKENDS")
            ready = [
                row for row in rows
                if str(row.get("Alive", "")).lower() == "true"
                and self._capacity_bytes(row.get("TotalCapacity", 0)) > 0
                and self._capacity_bytes(row.get("AvailCapacity", 0)) > 1024**2
            ]
            if len(rows) == expected_backends and len(ready) == expected_backends:
                break
            time.sleep(1)
        else:
            raise TimeoutError(
                f"Only {len(ready) if 'ready' in locals() else 0}/{expected_backends} BEs "
                f"reported usable storage; last rows={rows!r}"
            )
        frame = pd.DataFrame(rows)[
            ["BackendId", "Host", "Alive", "AvailCapacity", "TotalCapacity"]
        ]
        if show:
            show_frame(title, frame)
        return frame

    def environment_resource_summary(
        self,
        *,
        expected_backends: int = 3,
        minimum_cpus: int = 4,
        minimum_memory_bytes: int = 8_000_000_000,
        minimum_free_disk_bytes: int = 20 * 1024**3,
        title: str = "Current Docker resources and Lab minimums",
    ) -> pd.DataFrame:
        """Compare Docker allocation and the shared BE filesystem with Lab minimums."""
        docker = run(
            ["docker", "info", "--format", "{{.NCPU}}|{{.MemTotal}}"], check=False
        )
        if docker.returncode != 0:
            raise RuntimeError(f"Docker resource inspection failed: {docker.stderr.strip()}")
        cpu_text, memory_text = docker.stdout.strip().split("|", 1)
        cpus, memory_bytes = int(cpu_text), int(memory_text)
        storage = self.wait_for_backend_storage(
            expected_backends=expected_backends,
            title="BE storage paths are ready",
            show=False,
        )
        backends = storage.to_dict("records")
        free_values = [self._capacity_bytes(row.get("AvailCapacity", 0)) for row in backends]
        total_values = [self._capacity_bytes(row.get("TotalCapacity", 0)) for row in backends]
        if not free_values or min(free_values) <= 0:
            raise RuntimeError("BE storage capacity is not ready for resource validation.")
        shared_free = min(free_values)
        shared_total = min(total_values)
        rows = [
            {
                "resource": "Docker CPU allocation",
                "current": f"{cpus} cores",
                "Lab minimum": f"{minimum_cpus} cores",
                "status": "PASS" if cpus >= minimum_cpus else "BELOW MINIMUM",
                "scope": "shared by all FE and BE containers",
            },
            {
                "resource": "Docker memory allocation",
                "current": (
                    f"{memory_bytes / 1_000_000_000:.2f} GB / "
                    f"{memory_bytes / 1024**3:.2f} GiB"
                ),
                "Lab minimum": "8.00 GB / 7.45 GiB reported",
                "status": "PASS" if memory_bytes >= minimum_memory_bytes else "BELOW MINIMUM",
                "scope": "one shared memory pool; limits are not reservations",
            },
            {
                "resource": "BE data filesystem: free",
                "current": f"{shared_free / 1024**3:.2f} GiB",
                "Lab minimum": f"{minimum_free_disk_bytes / 1024**3:.0f} GiB",
                "status": "PASS" if shared_free >= minimum_free_disk_bytes else "BELOW MINIMUM",
                "scope": "one shared Docker filesystem; do not add the three BE rows",
            },
            {
                "resource": "BE data filesystem: total",
                "current": f"{shared_total / 1024**3:.2f} GiB",
                "Lab minimum": "informational",
                "status": "INFO",
                "scope": "reported separately by each BE but backed by the same host",
            },
        ]
        frame = pd.DataFrame(rows)
        show_frame(title, frame)
        failed = frame["status"] == "BELOW MINIMUM"
        if failed.any():
            missing = ", ".join(frame.loc[failed, "resource"])
            raise RuntimeError(f"The Docker environment is below the Lab minimum for: {missing}.")
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

    def compare_join_plans(
        self,
        cases: Sequence[tuple[str, str]],
        *,
        title: str = "Join plan comparison",
    ) -> pd.DataFrame:
        """Summarize physical Join evidence while keeping complete plans available."""
        connection = self._require_connection()
        rows: list[dict[str, str]] = []
        raw_plans: list[str] = []
        for label, statement in cases:
            normalized = statement.strip().rstrip(";")
            if not normalized.upper().startswith("EXPLAIN SHAPE PLAN"):
                raise ValueError(f"EXPLAIN SHAPE PLAN expected for {label!r}.")
            with connection.cursor() as cursor:
                cursor.execute(normalized)
                records = cursor.fetchall()
            plan = "\n".join(str(next(iter(record.values()))) for record in records)
            raw_plans.append(f"--- {label} ---\n{plan}")

            join_match = re.search(
                r"(?im)\b(hashJoin|nestedLoopJoin)\s*\[([^\]]+)\]([^\n]*)",
                plan,
            )
            if join_match:
                operator_token, attributes, remainder = join_match.groups()
                physical_join = (
                    "Hash Join" if operator_token.lower() == "hashjoin"
                    else "Nested Loop Join"
                )
                attribute_tokens = attributes.strip().split()
                join_type = attribute_tokens[0].replace("_", " ").title()
                strategy_names = {
                    "broadcast": "Broadcast",
                    "shuffle": "Partition Shuffle",
                    "shufflebucket": "Bucket Shuffle",
                    "bucket_shuffle": "Bucket Shuffle",
                    "colocate": "Colocate",
                }
                strategy = next(
                    (
                        strategy_names[token.lower()]
                        for token in attribute_tokens[1:]
                        if token.lower() in strategy_names
                    ),
                    "No Shuffle Strategy",
                )
                runtime_filter = (
                    "Generated"
                    if re.search(r"build\s*RFs:\s*RF\d+", remainder, re.IGNORECASE)
                    else "Not shown"
                )
            else:
                physical_join = "not shown"
                join_type = "not shown"
                strategy = "not shown"
                runtime_filter = "not shown"

            rows.append({
                "query": label,
                "physical join": physical_join,
                "join type": join_type,
                "distribution": strategy,
                "runtime filter": runtime_filter,
            })

        frame = pd.DataFrame(rows)
        show_frame(title, frame)
        show_log("View the complete EXPLAIN SHAPE PLAN output", "\n\n".join(raw_plans))
        return frame

    def explain_plan(self, statement: str, *, title: str = "EXPLAIN plan") -> str:
        """Display an EXPLAIN result verbatim as an expanded plan tree."""
        normalized = statement.strip().rstrip(";")
        if not normalized.upper().startswith("EXPLAIN"):
            raise ValueError("An EXPLAIN statement is required.")
        connection = self._require_connection()
        executable, _visible = self._expand_sql(normalized)
        with connection.cursor() as cursor:
            cursor.execute(executable)
            records = cursor.fetchall()
        plan = "\n".join(str(next(iter(record.values()))) for record in records)
        show_log(title, plan, opened=True)
        return plan

    def explain_selected_scans(
        self,
        statement: str,
        *,
        title: str = "Selected scans",
        expected_table: str | None = None,
        expected_index: str | None = None,
    ) -> str:
        """Execute EXPLAIN, verify an optional scan, and display selected TABLE lines."""
        normalized = statement.strip()
        if not normalized.upper().startswith("EXPLAIN"):
            raise ValueError("An EXPLAIN statement is required.")
        connection = self._require_connection()
        with connection.cursor() as cursor:
            cursor.execute(normalized)
            records = cursor.fetchall()
        plan = "\n".join(str(next(iter(record.values()))) for record in records)
        if expected_table is not None:
            table = self._safe_table_name(expected_table)
            index = self._safe_table_name(expected_index or expected_table)
            pattern = rf"TABLE:\s*(?:[\w`]+\.)?`?{table}`?\s*\(\s*{index}\s*\)"
            if not re.search(pattern, plan):
                raise AssertionError(f"Expected selected scan {table}({index}) was not found.")
        scans = [line for line in plan.splitlines() if re.match(r"\s*TABLE:", line)]
        show_log(title, "\n".join(scans) or "Selected TABLE lines are not shown.", opened=True)
        return plan

    def explain_colocate_join(
        self,
        statement: str,
        *,
        title: str = "Colocate Join evidence",
    ) -> str:
        """Verify and display the Join and scan lines that prove a Colocate plan."""
        normalized = statement.strip()
        if not normalized.upper().startswith("EXPLAIN"):
            raise ValueError("An EXPLAIN statement is required.")
        connection = self._require_connection()
        with connection.cursor() as cursor:
            cursor.execute(normalized)
            records = cursor.fetchall()
        plan = "\n".join(str(next(iter(record.values()))) for record in records)
        if not re.search(r"join op:\s*[^\n]*\bCOLOCATE\b", plan, re.IGNORECASE):
            raise AssertionError("The plan did not select a Colocate Join.")
        lines = [
            line for line in plan.splitlines()
            if re.search(r"join op:|equal join conjunct:|\bTABLE:", line, re.IGNORECASE)
        ]
        show_log(title, "\n".join(lines), opened=True)
        show_log(f"{title}: complete EXPLAIN", plan)
        return plan

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
        url = (
            f"http://{self._profile_http_host}:{self._profile_http_port}"
            f"/rest/v2/manager/query/profile/text/{profile_id}"
        )
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
        raise RuntimeError(f"The Query Profile was not ready: {last_error or 'timed out'}")

    def show_join_runtime_filter_profile(
        self,
        statement: str,
        *,
        probe_table: str,
        title: str = "Probe-side Runtime Filter Profile",
    ) -> str:
        """Run a Join query and display the relevant raw MergedProfile counters."""
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", probe_table):
            raise ValueError("probe_table must be an unqualified table name.")
        query = statement.strip().rstrip(";")
        if not query.upper().startswith("SELECT "):
            raise ValueError("A SELECT statement is required.")

        connection = self._require_connection()
        settings = {
            "enable_profile": "true",
            "profile_level": "2",
            "enable_condition_cache": "false",
            "enable_query_cache": "false",
            "enable_sql_cache": "false",
        }
        originals: dict[str, str] = {}
        try:
            with connection.cursor() as cursor:
                for name, value in settings.items():
                    cursor.execute(f"SHOW VARIABLES LIKE '{name}'")
                    row = cursor.fetchone()
                    if row is None:
                        raise RuntimeError(f"Doris did not expose the session variable {name}.")
                    originals[name] = str(row["Value"])
                    cursor.execute(f"SET {name} = {value}")

            existing_ids = {str(row["Profile ID"]) for row in self._query_profiles()}
            with connection.cursor() as cursor:
                cursor.execute(query)
                result = cursor.fetchone()

            profile_id = self._latest_profile_id(query, exclude=existing_ids)
            profile = self._profile_text(profile_id)
            merged = profile.split("MergedProfile:", 1)[-1].split("DetailProfile", 1)[0]
            scan_header = re.search(
                rf"(?m)^\s*OLAP_SCAN_OPERATOR\([^\n]*table_name={re.escape(probe_table)}\(",
                merged,
            )
            if scan_header is None:
                raise RuntimeError(f"The Profile has no merged Scan for {probe_table}.")

            join_header = merged.rfind("HASH_JOIN_OPERATOR(", 0, scan_header.start())
            join_block = merged[join_header:scan_header.start()] if join_header >= 0 else ""
            next_operator = re.search(
                r"(?m)^\s*[A-Z][A-Z_]+_OPERATOR\(",
                merged[scan_header.end():],
            )
            scan_end = (
                scan_header.end() + next_operator.start()
                if next_operator else len(merged)
            )
            scan_block = merged[scan_header.start():scan_end]
            join_lines = [
                line for line in join_block.splitlines()
                if "HASH_JOIN_OPERATOR(" in line or re.search(r"- ProbeRows:", line)
            ]
            scan_lines = [
                line for line in scan_block.splitlines()
                if "OLAP_SCAN_OPERATOR(" in line
                or re.search(r"- (?:RowsProduced|ScanRows):", line)
                or re.search(r"- RF\d+ (?:InputRows|FilterRows):", line)
            ]
            if not any(re.search(r"- RF\d+ FilterRows:", line) for line in scan_lines):
                raise RuntimeError("The probe Scan Profile has no Runtime Filter row counters.")
            excerpt = "\n".join(join_lines + scan_lines)
            result_text = ", ".join(f"{name}={value}" for name, value in (result or {}).items())
            print(f"Query result: {result_text}")
            show_log(title, excerpt, opened=True)
            return excerpt
        finally:
            with connection.cursor() as cursor:
                for name, value in originals.items():
                    cursor.execute(f"SET {name} = {value}")

    def compare_profiles(
        self,
        cases: Sequence[tuple[str, str]],
        *,
        title: str = "Query Profile scan evidence",
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
        """Match visible workload requirements to load methods."""
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
                "reason": "Correct. A Routine Load job continuously consumes a Kafka topic and commits consumed offsets together with each successful micro-batch transaction.",
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
            '<div class="doris-match-title">Match workload requirements to a load method</div>'
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
            "D": "This workload already has a write interface; it needs small-write batching rather than a new source connector.",
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

    def function_category_activity(self) -> None:
        """Match representative Doris expressions to their function categories."""
        items = [
            {
                "id": "A",
                "title": "Transform each input row",
                "detail": "Normalize an event type without changing the number of input rows.",
                "answer": "LOWER(event_type)",
                "reason": "LOWER is a scalar function: it produces one value for each input row.",
            },
            {
                "id": "B",
                "title": "Combine values across rows",
                "detail": "Calculate one revenue total for every group.",
                "answer": "SUM(revenue)",
                "reason": "SUM is an aggregate function: it combines values from multiple rows into one grouped value.",
            },
            {
                "id": "C",
                "title": "Adapt an aggregate for ARRAY positions",
                "detail": "Sum the first elements together, the second elements together, and so on.",
                "answer": "SUM_FOREACH(metric_array)",
                "reason": "SUM_FOREACH is an aggregate combinator: it applies SUM independently at each ARRAY position across rows.",
            },
            {
                "id": "D",
                "title": "Add a value while retaining result rows",
                "detail": "Rank products inside each region without first reducing the ranked rows.",
                "answer": "ROW_NUMBER() OVER (...) ",
                "reason": "ROW_NUMBER is a window function: it adds a value to each row in its window.",
            },
            {
                "id": "E",
                "title": "Expand a collection stored in one row",
                "detail": "Turn every tag in an event's ARRAY into a separate result row.",
                "answer": "EXPLODE(tags)",
                "reason": "EXPLODE is a table function: with LATERAL VIEW, it can produce zero to many rows for each input row.",
            },
            {
                "id": "F",
                "title": "Create a relation without an input table",
                "detail": "Generate four numbered rows that SELECT can use directly in FROM.",
                "answer": "NUMBERS(...) TVF",
                "reason": "NUMBERS is a table-valued function: the function itself supplies a temporary relation for FROM.",
            },
            {
                "id": "G",
                "title": "Classify text with an external model",
                "detail": "Send text through a configured Doris AI Resource and return a sentiment label.",
                "answer": "AI_SENTIMENT(resource, text)",
                "reason": "AI_SENTIMENT is an AI function. It has scalar row shape, but also depends on an external model configured through an AI Resource.",
            },
        ]
        methods = [
            "NUMBERS(...) TVF",
            "ROW_NUMBER() OVER (...) ",
            "EXPLODE(tags)",
            "LOWER(event_type)",
            "AI_SENTIMENT(resource, text)",
            "SUM_FOREACH(metric_array)",
            "SUM(revenue)",
        ]
        widget_id = "doris-function-match-" + uuid.uuid4().hex
        method_html = "".join(
            f'<button type="button" class="doris-method" draggable="true" data-method="{html.escape(method)}">'
            f'{html.escape(method)}</button>'
            for method in methods
        )
        cards = []
        for item in items:
            cards.append(
                f'<section class="doris-scenario" data-answer="{html.escape(item["answer"])}" '
                f'data-reason="{html.escape(item["reason"])}" tabindex="0" role="button">'
                f'<div class="doris-scenario-title"><span class="doris-scenario-letter">{item["id"]}</span>'
                f'<span>{html.escape(item["title"])}</span></div>'
                f'<p class="doris-match-help" style="margin:8px 0">{html.escape(item["detail"])}</p>'
                '<div class="doris-dropzone">Drop the matching expression here, or select an expression and click this card.</div>'
                '<div class="doris-match-feedback" aria-live="polite"></div></section>'
            )
        display(HTML(
            f'<div id="{widget_id}" class="doris-match">'
            '<div class="doris-match-head"><div><div class="doris-match-title">'
            'Match each requirement to a Doris function category</div>'
            '<p class="doris-match-help">Drag each expression onto one requirement. If dragging is unavailable, '
            'select an expression and then click a requirement card. A correct match explains the row-shape behavior.</p></div>'
            '<div class="doris-match-score"><span data-score>0</span>/7 matched</div></div>'
            f'<div class="doris-method-bank">{method_html}</div>'
            f'<div class="doris-scenario-grid">{"".join(cards)}</div>'
            '<div class="doris-match-actions"><button type="button" class="doris-match-reset">Reset matches</button></div>'
            '</div>'
        ))
        script = f"""
        (() => {{
          const root = document.getElementById({json.dumps(widget_id)});
          if (!root) return;
          const bank = root.querySelector('.doris-method-bank');
          const methods = [...root.querySelectorAll('.doris-method')];
          const cards = [...root.querySelectorAll('.doris-scenario')];
          let selected = null;
          const choose = (button) => {{
            if (button.disabled) return;
            methods.forEach(item => item.classList.remove('selected'));
            selected = button.dataset.method;
            button.classList.add('selected');
          }};
          const attempt = (card) => {{
            if (!selected || card.dataset.solved === 'true') return;
            const feedback = card.querySelector('.doris-match-feedback');
            if (selected === card.dataset.answer) {{
              card.dataset.solved = 'true';
              card.classList.remove('wrong'); card.classList.add('correct');
              const button = methods.find(item => item.dataset.method === selected);
              card.querySelector('.doris-dropzone').replaceChildren(button);
              button.disabled = true; button.draggable = false; button.classList.remove('selected');
              feedback.textContent = card.dataset.reason;
              selected = null;
              root.querySelector('[data-score]').textContent = String(cards.filter(item => item.dataset.solved === 'true').length);
            }} else {{
              card.classList.add('wrong');
              feedback.textContent = 'Not this expression. Compare the input, output row shape, and whether the operation depends on an existing input row or an external service.';
            }}
          }};
          methods.forEach(button => {{
            button.addEventListener('click', () => choose(button));
            button.addEventListener('dragstart', event => {{
              choose(button);
              event.dataTransfer.setData('text/plain', button.dataset.method);
              event.dataTransfer.effectAllowed = 'move';
            }});
          }});
          cards.forEach(card => {{
            card.addEventListener('dragover', event => {{
              event.preventDefault(); card.classList.add('over');
            }});
            card.addEventListener('dragleave', () => card.classList.remove('over'));
            card.addEventListener('drop', event => {{
              event.preventDefault(); card.classList.remove('over');
              const method = event.dataTransfer.getData('text/plain');
              if (method) selected = method;
              attempt(card);
            }});
            card.addEventListener('click', () => attempt(card));
            card.addEventListener('keydown', event => {{
              if (event.key === 'Enter' || event.key === ' ') {{ event.preventDefault(); attempt(card); }}
            }});
          }});
          root.querySelector('.doris-match-reset').addEventListener('click', () => {{
            methods.forEach(button => {{
              button.disabled = false; button.draggable = true; button.classList.remove('selected'); bank.appendChild(button);
            }});
            cards.forEach(card => {{
              card.dataset.solved = 'false'; card.classList.remove('correct', 'wrong');
              card.querySelector('.doris-dropzone').textContent = 'Drop the matching expression here, or select an expression and click this card.';
              card.querySelector('.doris-match-feedback').textContent = '';
            }});
            selected = null; root.querySelector('[data-score]').textContent = '0';
          }});
        }})();
        """
        display(Javascript(script))

    def expected_sql_error(
        self,
        statement: str,
        *,
        contains: str,
        title: str = "Expected query rejection",
    ) -> str:
        """Run an intentionally invalid query and render its expected diagnostic compactly."""
        connection = self._require_connection()
        executable, _visible = self._expand_sql(statement.strip())
        try:
            with connection.cursor() as cursor:
                cursor.execute(executable)
        except pymysql.MySQLError as exc:
            message = str(exc)
            if contains.lower() not in message.lower():
                raise
            detail = message.split("detailMessage =", 1)[-1].strip(" ')\n")
            card(detail, "warn", title)
            return message
        raise AssertionError("Doris accepted a query that this exercise expected it to reject.")

    def guided_analysis_builder(self) -> None:
        """Render a small guided query builder and execute the selected analysis."""
        try:
            import ipywidgets as widgets
            from IPython.display import clear_output
        except ImportError as exc:  # pragma: no cover - learner environment diagnostic
            raise RuntimeError("ipywidgets is required. Install the course requirements and restart the kernel.") from exc

        grains = {
            "Day": "TO_DATE(event_time)",
            "Week": "DATE_TRUNC(event_time, 'week')",
            "Month": "DATE_TRUNC(event_time, 'month')",
        }
        metrics = {
            "Event count": "COUNT(*)",
            "Active users": "COUNT(DISTINCT user_id)",
            "Revenue": "SUM(revenue)",
        }
        filters = {
            "All event types": "",
            "Views only": "  AND event_type = 'view'\n",
            "Carts only": "  AND event_type = 'cart'\n",
            "Purchases only": "  AND event_type = 'purchase'\n",
        }
        grain = widgets.Dropdown(options=list(grains), value="Day", description="Grain:")
        event_filter = widgets.Dropdown(options=list(filters), value="Purchases only", description="Rows:")
        metric = widgets.Dropdown(options=list(metrics), value="Revenue", description="Metric:")
        run_button = widgets.Button(description="Run guided query", button_style="success", icon="play")
        output = widgets.Output()

        def run_query(_button=None):
            period = grains[grain.value]
            metric_expression = metrics[metric.value]
            alias = {"Event count": "event_count", "Active users": "active_users", "Revenue": "total_revenue"}[metric.value]
            statement = f"""
SELECT
    {period} AS reporting_period,
    {metric_expression} AS {alias}
FROM events_modelled
WHERE event_time >= '2020-03-01 00:00:00'
  AND event_time <  '2020-03-09 00:00:00'
{filters[event_filter.value]}GROUP BY {period}
ORDER BY {alias} DESC, reporting_period
LIMIT 10
""".strip()
            with output:
                clear_output(wait=True)
                show_sql(statement, "Generated Doris SQL")
                self.sql(statement, title="Guided analysis result")

        run_button.on_click(run_query)
        display(widgets.VBox([
            widgets.HTML("<b>Choose the reporting grain, input rows, and metric.</b> The generated SQL remains visible."),
            widgets.HBox([grain, event_filter, metric]),
            run_button,
            output,
        ]))

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
                        secrets = load_env_file(self.lab_dir / "course_secrets.env")
                        access_key = secrets.get("S3_READ_ONLY_ACCESS_KEY", "")
                        secret_key = secrets.get("S3_READ_ONLY_SECRET_KEY", "")
                        if not access_key or not secret_key:
                            raise RuntimeError(
                                "Fill both read-only S3 credentials in course_secrets.env "
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

    def sync_mv_jobs(self, table, view, *, database="doris_course"):
        """Return build jobs for one synchronous materialized view."""
        table = self._safe_table_name(table)
        view = self._safe_table_name(view)
        database = self._safe_table_name(database)
        return [row for row in self._metadata_rows(
            f"SHOW ALTER TABLE MATERIALIZED VIEW FROM `{database}`"
        ) if row["TableName"] == table and row["RollupIndexName"] == view]

    def async_mv_tasks(self, view, *, database="doris_course"):
        """Return refresh tasks for one asynchronous materialized view."""
        view = self._safe_table_name(view)
        database = self._safe_table_name(database)
        return self._metadata_rows(f"""SELECT * FROM tasks("type"="mv")
            WHERE MvDatabaseName = '{database}' AND MvName = '{view}'""")

    def capture_query(self, statement, *, settings=None):
        """Capture the result, plan and fresh runtime Profile on this lab session."""
        from .profiles import capture_query
        return capture_query(self, statement, settings=settings)

    def verify_query_change(
        self,
        statement: str,
        baseline: pd.DataFrame,
        *,
        match: Mapping[str, object],
        expected_changes: Mapping[str, object],
        title: str = "Observed result change",
    ):
        """Run SQL and display only one matched row's verified changes."""
        from .profiles import show_result_change

        rows = self.query(statement)
        show_result_change(
            rows,
            title,
            baseline,
            match=match,
            metrics=tuple(expected_changes),
            expected_changes=expected_changes,
        )
        return rows

    def session_settings(self, settings):
        """Temporarily apply session settings and restore them on context exit."""
        from .profiles import session_settings
        return session_settings(self, settings)

    @staticmethod
    def _wait_mv_job(fetch, matches, id_key, state_key, before, success, failures, timeout):
        deadline = time.monotonic() + timeout
        last = []
        while time.monotonic() < deadline:
            last = [row for row in fetch() if matches(row) and str(row[id_key]) not in before]
            if len(last) > 1:
                raise RuntimeError(f"Multiple new jobs found; avoid concurrent operations on the same materialized view: {last}")
            if last:
                row = last[0]
                state = str(row[state_key]).upper()
                if state == success:
                    return row
                if state in failures:
                    raise RuntimeError(f"Background job failed: {row}")
            time.sleep(0.5)
        raise TimeoutError(f"Background job did not finish within {timeout}s. Last matching rows: {last}")

    def wait_for_sync_mv(self, table, view, before, *, database="doris_course", timeout=120):
        row = self._wait_mv_job(
            lambda: self.sync_mv_jobs(table, view, database=database),
            lambda r: True,
            "JobId", "State", {str(x) for x in before}, "FINISHED", {"CANCELLED", "FAILED"}, timeout,
        )
        show_frame("Synchronous materialized-view build", pd.DataFrame([{
            "Base table": row["TableName"],
            "Materialized view": row["RollupIndexName"],
            "Build state": row["State"],
        }]))
        show_log("Complete synchronous build task", json.dumps(row, indent=2, default=str))
        return row

    def wait_for_async_refresh(self, view, before, *, database="doris_course", timeout=120):
        row = self._wait_mv_job(
            lambda: self.async_mv_tasks(view, database=database), lambda r: True, "TaskId", "Status",
            {str(x) for x in before}, "SUCCESS", {"FAILED", "FAIL", "CANCELED", "CANCELLED"}, timeout,
        )
        show_frame("Completed manual refresh task", pd.DataFrame([{
            "TaskId": row.get("TaskId"),
            "MvName": row.get("MvName"),
            "Status": row.get("Status"),
            "RefreshMode": row.get("RefreshMode"),
            "Progress": row.get("Progress"),
        }]))
        return row

    def wait_for_mv_jobs(self, table, sync_view, async_view, *, database="doris_course", timeout=120):
        """Wait for earlier jobs on the explicitly named objects before resetting them."""
        deadline = time.monotonic() + timeout
        last = []
        while time.monotonic() < deadline:
            last = [r for r in self.sync_mv_jobs(table, sync_view, database=database)
                    if str(r["State"]).upper() not in {"FINISHED", "CANCELLED", "FAILED"}]
            last += [r for r in self.async_mv_tasks(async_view, database=database)
                     if str(r["Status"]).upper() not in {"SUCCESS", "FAILED", "FAIL", "CANCELED", "CANCELLED"}]
            if not last:
                return
            time.sleep(0.5)
        raise TimeoutError(f"Earlier materialized-view jobs are still active; objects were not reset: {last}")

    @staticmethod
    def assert_scan(evidence, table, index=None):
        """Check the chosen scan line, not an optimizer candidate/rewrite summary."""
        DorisLab._safe_table_name(table)
        index = DorisLab._safe_table_name(index or table)
        pattern = rf"TABLE:\s*(?:[\w`]+\.)?`?{table}`?\s*\(\s*{index}\s*\)"
        if not re.search(pattern, evidence.plan):
            raise AssertionError(
                f"Expected selected scan {table}({index}) was not found. "
                "Inspect the displayed EXPLAIN and current build/statistics before claiming a rewrite."
            )

    @staticmethod
    def assert_same_rows(left, right):
        """Compare complete result multisets, including duplicate multiplicities."""
        from collections import Counter

        if list(left.columns) != list(right.columns):
            raise AssertionError(f"Different result columns: {list(left.columns)} vs {list(right.columns)}")
        if Counter(left.itertuples(index=False, name=None)) != Counter(right.itertuples(index=False, name=None)):
            raise AssertionError("The complete grouped results differ; inspect both results before continuing.")


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
        """Publish real Kafka batches and render the producer/Routine Load timeline."""
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
                "waiting for Routine Load": max(0, kafka_messages - routine_loaded),
                "Routine Load committed": routine_loaded,
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
                f'{int(latest["waiting for Routine Load"]):,} published messages awaiting a Routine Load commit</div>'
                '<div class="doris-flow-arrow">→</div>'
                '<div class="doris-flow-step"><strong>Routine Load job</strong>'
                f'{int(latest["Routine Load committed"]):,} committed · '
                f'{html.escape(str(latest["Routine Load state"]))}</div>'
                '<div class="doris-flow-arrow">→</div>'
                '<div class="doris-flow-step"><strong>events_routine</strong>'
                f'{int(latest["events_routine rows"]):,} queryable rows</div>'
                '</div>'
            )
            return HTML(
                '<div class="doris-result">'
                '<div class="doris-result-title">Live producer-to-Routine-Load pipeline</div>'
                f'{pipeline}'
                '<div class="doris-result-title">Producer and Routine Load timeline '
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
                observed = snapshot(f"Routine Load job · waiting for {expected}", started_at)
                target_count = int(observed["events_routine rows"])
                if target_count >= expected:
                    observed["actor / action"] = f"Routine Load job · committed {expected}"
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
        container: str,
        *,
        wait_for_healthy: bool = True,
        timeout_seconds: int = 300,
    ) -> dict:
        """Idempotently make an existing course container available again."""
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", container):
            raise ValueError("container must be a simple Docker container name.")

        self.ensure_docker_ready()
        state = container_inspect(container)
        if state is None:
            raise RuntimeError(
                f"Container {container!r} does not exist. Run that module's environment "
                "preparation before using its restart cell."
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
        container_state = state.get("State", {})
        show_frame("Sandbox container", pd.DataFrame([{
            "container": container,
            "status": container_state.get("Status", "unknown"),
            "health": container_state.get("Health", {}).get("Status", "not configured"),
        }]))
        return state

    def connect(
        self,
        *,
        container: str = "doris",
        host: str = "127.0.0.1",
        port: int = 9030,
        http_host: str | None = None,
        http_port: int = 8030,
    ):
        wait_for_health(container, timeout_seconds=300, report=False)
        if self.connection is not None:
            try:
                self.connection.close()
            except Exception:
                pass
        self.DORIS_CONTAINER = container
        self._connection_host = host
        self._connection_port = port
        self._profile_http_host = http_host or host
        self._profile_http_port = http_port
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

    def load_s3_credentials(self, filename: str = "course_secrets.env") -> bool:
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

    @staticmethod
    def container_running(name: str) -> bool:
        """Return whether one Docker container currently has Running=true."""
        state = container_inspect(name)
        return bool(state and state.get("State", {}).get("Running", False))

    def table_exists(self, table_name: str) -> bool:
        """Return whether one safe table name exists in the current database."""
        table_name = self._safe_table_name(table_name)
        return bool(self._metadata_rows(f"SHOW TABLES LIKE '{table_name}'"))

    def table_replication_num(self, table_name: str) -> int:
        """Return the normalized replica count from SHOW CREATE TABLE."""
        table_name = self._safe_table_name(table_name)
        rows = self._metadata_rows(f"SHOW CREATE TABLE `{table_name}`")
        if len(rows) != 1:
            raise RuntimeError(f"Could not read the definition of {table_name}.")
        ddl = "\n".join(str(value) for value in rows[0].values())
        allocation = re.search(
            r'"replication_allocation"\s*=\s*"[^"]*:\s*(\d+)"', ddl
        )
        direct = re.search(r'"replication_num"\s*=\s*"(\d+)"', ddl)
        match = allocation or direct
        if match is None:
            raise RuntimeError(
                f"SHOW CREATE TABLE did not expose a replica count for {table_name}."
            )
        return int(match.group(1))

    def replica_distribution_summary(
        self,
        table_name: str,
        *,
        title: str | None = None,
        show: bool = True,
    ) -> pd.DataFrame:
        """Show the physical replica count and size reported for each BE."""
        table_name = self._safe_table_name(table_name)
        distribution = self._metadata_rows(
            f"SHOW REPLICA DISTRIBUTION FROM `{table_name}`"
        )
        backends = {
            str(row["BackendId"]): row for row in self._metadata_rows("SHOW BACKENDS")
        }
        rows = []
        for row in distribution:
            backend_id = str(row["BackendId"])
            backend = backends.get(backend_id, {})
            size = row.get("ReplicaSize", row.get("Size", 0))
            rows.append({
                "backend_id": backend_id,
                "host": backend.get("Host", "unknown"),
                "alive": str(backend.get("Alive", "")).lower() == "true",
                "stored replicas": int(row["ReplicaNum"]),
                "replica size": self._human_bytes(self._capacity_bytes(size)),
            })
        frame = pd.DataFrame(rows).sort_values("host").reset_index(drop=True)
        if show:
            show_frame(title or f"{table_name} replicas by BE", frame)
        return frame

    def wait_for_replica_distribution(
        self,
        table_name: str,
        *,
        expected_backends: int,
        expected_total_replicas: int,
        max_replica_spread: int | None = None,
        timeout_seconds: int = 300,
        title: str | None = None,
        show: bool = True,
    ) -> pd.DataFrame:
        """Wait for bounded automatic replica placement after a BE topology change."""
        deadline = time.monotonic() + timeout_seconds
        frame = pd.DataFrame()
        while time.monotonic() < deadline:
            frame = self.replica_distribution_summary(table_name, show=False)
            counts = (
                frame["stored replicas"].astype(int).tolist() if not frame.empty else []
            )
            spread_ready = (
                max_replica_spread is None
                or (counts and max(counts) - min(counts) <= max_replica_spread)
            )
            if (
                len(counts) == expected_backends
                and all(value > 0 for value in counts)
                and sum(counts) == expected_total_replicas
                and spread_ready
            ):
                if show:
                    show_frame(title or f"{table_name} replica placement is ready", frame)
                return frame
            time.sleep(1)
        raise TimeoutError(
            f"Replica distribution for {table_name} did not reach "
            f"backends={expected_backends}, total={expected_total_replicas}, "
            f"spread<={max_replica_spread}; last rows={frame.to_dict('records')!r}"
        )

    def wait_for_colocation_group(
        self,
        group_name: str,
        *,
        timeout_seconds: int = 180,
        title: str = "Colocation Group is stable",
    ) -> pd.DataFrame:
        """Wait for one named Colocation Group to become stable."""
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", group_name):
            raise ValueError(f"Unsafe Colocation Group name: {group_name!r}")
        deadline = time.monotonic() + timeout_seconds
        selected: dict[str, object] | None = None
        while time.monotonic() < deadline:
            rows = self._metadata_rows('SHOW PROC "/colocation_group"')
            matches = [
                row for row in rows
                if str(row.get("GroupName", "")).split(".")[-1] == group_name
            ]
            if len(matches) == 1:
                selected = matches[0]
                if str(selected.get("IsStable", "")).lower() == "true":
                    frame = pd.DataFrame([{
                        "group": group_name,
                        "buckets": selected.get("BucketsNum"),
                        "replication": selected.get("ReplicaAllocation"),
                        "stable": selected.get("IsStable"),
                    }])
                    show_frame(title, frame)
                    return frame
            time.sleep(1)
        raise TimeoutError(
            f"Colocation Group {group_name!r} did not become stable within "
            f"{timeout_seconds} seconds; last metadata={selected!r}"
        )

    @staticmethod
    def _proxy_stats_rows(stats_url: str, backend: str) -> list[dict[str, object]]:
        """Read HAProxy's CSV statistics for one named backend."""
        with urllib.request.urlopen(stats_url, timeout=5) as response:
            payload = response.read().decode("utf-8", errors="replace")
        lines = [line for line in payload.splitlines() if line.strip()]
        if not lines:
            raise RuntimeError(f"HAProxy returned no statistics from {stats_url}.")
        lines[0] = lines[0].lstrip("# ")
        reader = csv.DictReader(io.StringIO("\n".join(lines)))
        rows = []
        for row in reader:
            if row.get("pxname") != backend or row.get("svname") in {
                "BACKEND", "FRONTEND",
            }:
                continue
            rows.append(row)
        if not rows:
            raise RuntimeError(
                f"HAProxy backend {backend!r} was not present in {stats_url}."
            )
        return rows

    def proxy_backend_summary(
        self,
        stats_url: str,
        *,
        backend: str = "doris_fes",
        title: str = "FE targets visible through HAProxy",
        show: bool = True,
    ) -> pd.DataFrame:
        """Show HAProxy target health and connection counters without raw CSV noise."""
        rows = []
        for row in self._proxy_stats_rows(stats_url, backend):
            rows.append({
                "FE target": row.get("svname", "unknown"),
                "proxy status": row.get("status", "unknown"),
                "active connections": int(row.get("scur") or 0),
                "total connections": int(row.get("stot") or 0),
                "last check": row.get("check_status") or "not reported",
            })
        frame = pd.DataFrame(rows).sort_values("FE target").reset_index(drop=True)
        if show:
            show_frame(title, frame)
        return frame

    def wait_for_proxy_backend_status(
        self,
        stats_url: str,
        server_name: str,
        expected_status: str,
        *,
        backend: str = "doris_fes",
        timeout_seconds: int = 60,
        title: str | None = None,
        show: bool = True,
    ) -> pd.DataFrame:
        """Wait until HAProxy reports one FE target UP or DOWN."""
        expected = expected_status.upper()
        if expected not in {"UP", "DOWN"}:
            raise ValueError("expected_status must be UP or DOWN.")
        deadline = time.monotonic() + timeout_seconds
        frame = pd.DataFrame()
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                frame = self.proxy_backend_summary(
                    stats_url, backend=backend, show=False
                )
                last_error = None
            except (OSError, urllib.error.URLError, http.client.HTTPException) as exc:
                # Docker can publish the statistics port just before HAProxy's
                # HTTP listener is ready. Treat that startup race as a poll miss.
                last_error = exc
                time.sleep(1)
                continue
            selected = frame.loc[frame["FE target"] == server_name]
            if len(selected.index) == 1 and str(
                selected.iloc[0]["proxy status"]
            ).upper().startswith(expected):
                if show:
                    show_frame(title or f"HAProxy marks {server_name} {expected}", frame)
                return frame
            time.sleep(1)
        raise TimeoutError(
            f"HAProxy did not mark {server_name} {expected}; "
            f"last rows={frame.to_dict('records')!r}; last error={last_error!r}"
        )

    def expect_current_connection_failure(
        self,
        statement: str = "SELECT 1",
        *,
        title: str = "The direct FE connection has closed",
    ) -> str:
        """Verify that an already-open connection fails after its FE stops."""
        connection = self.connection
        if connection is None:
            raise RuntimeError("No open connection is available for the failure check.")
        try:
            with connection.cursor() as cursor:
                cursor.execute(statement)
                cursor.fetchall()
        except (OSError, pymysql.MySQLError) as exc:
            try:
                connection.close()
            except Exception:
                pass
            self.connection = None
            message = str(exc).splitlines()[0]
            show_frame(title, pd.DataFrame([{
                "expected outcome": "connection failed",
                "reason": message[:180],
            }]))
            return message
        raise AssertionError(
            "The direct FE connection still executed the probe; wait until that FE stops."
        )

    def explain_join_distribution(
        self,
        statement: str,
        *,
        expected_strategy: str,
        title: str = "Join distribution evidence",
    ) -> str:
        """Verify a distributed Join strategy and show only its relevant plan block."""
        normalized = statement.strip().rstrip(";")
        if not normalized.upper().startswith("EXPLAIN"):
            raise ValueError("An EXPLAIN statement is required.")
        strategy_patterns = {
            "bucket_shuffle": r"join op:\s*[^\n]*\bBUCKET_SHUFFLE\b",
            "colocate": r"join op:\s*[^\n]*\bCOLOCATE\b",
        }
        if expected_strategy not in strategy_patterns:
            raise ValueError("expected_strategy must be 'bucket_shuffle' or 'colocate'.")

        connection = self._require_connection()
        executable, _visible = self._expand_sql(normalized)
        with connection.cursor() as cursor:
            cursor.execute(executable)
            records = cursor.fetchall()
        plan = "\n".join(str(next(iter(record.values()))) for record in records)
        if not re.search(strategy_patterns[expected_strategy], plan, re.IGNORECASE):
            raise AssertionError(
                f"The plan did not select the expected {expected_strategy} Join strategy."
            )

        fragments = re.split(r"(?=^PLAN FRAGMENT \d+)", plan, flags=re.MULTILINE)
        join_fragment = next(
            (fragment for fragment in fragments if re.search(r"join op:", fragment, re.I)),
            plan,
        )
        evidence_patterns = (
            r"\bVHASH JOIN\b",
            r"join op:",
            r"equal join conjunct:",
            r"\bVEXCHANGE\b",
            r"\bVOlapScanNode\b",
            r"\bTABLE:",
            r"\bpartitions=",
        )
        evidence = [
            line for line in join_fragment.splitlines()
            if any(re.search(pattern, line, re.IGNORECASE) for pattern in evidence_patterns)
        ]
        # A Bucket Shuffle build-side scan can live in the next Fragment. Append
        # each selected table and partition line without printing the full plan.
        for line in plan.splitlines():
            if re.search(r"\bTABLE:|\bpartitions=", line, re.IGNORECASE) and line not in evidence:
                evidence.append(line)
        show_log(title, "\n".join(evidence), opened=True)
        return plan

    def wait_for_storage_reports(
        self,
        table_names: Sequence[str],
        *,
        expected_rows: int,
        timeout_seconds: int = 180,
    ) -> None:
        """Wait until SHOW DATA reports the committed rows and nonzero local bytes."""
        names = [self._safe_table_name(name) for name in table_names]
        if not names:
            raise ValueError("At least one table is required.")
        missing = [
            name for name in names
            if not self._metadata_rows(f"SHOW TABLES LIKE '{name}'")
        ]
        if missing:
            raise RuntimeError(
                "Create and load these Module tables before checking storage metadata: "
                + ", ".join(missing)
            )

        committed = {
            name: int(self._metadata_rows(
                f"SELECT COUNT(*) AS row_count FROM `{name}`"
            )[0]["row_count"])
            for name in names
        }
        wrong = {name: rows for name, rows in committed.items() if rows != expected_rows}
        if wrong:
            raise AssertionError(
                f"Committed row counts do not match {expected_rows:,}: {wrong!r}. "
                "Complete the preceding inserts before checking storage metadata."
            )

        deadline = time.monotonic() + timeout_seconds
        last: dict[str, dict[str, object]] = {}
        while time.monotonic() < deadline:
            ready = True
            for name in names:
                rows = self._metadata_rows(f"SHOW DATA FROM `{name}`")
                table_row = next(
                    (row for row in rows if str(row.get("TableName", "")) == name), None
                )
                if table_row is None:
                    ready = False
                    last[name] = {"RowCount": "missing", "Size": "missing"}
                    continue
                last[name] = table_row
                reported_rows = int(table_row.get("RowCount", 0) or 0)
                reported_bytes = self._capacity_bytes(table_row.get("Size", 0))
                if reported_rows != expected_rows or reported_bytes <= 0:
                    ready = False
            if ready:
                return
            time.sleep(2)
        raise TimeoutError(
            "Doris had not reported nonzero storage metadata for every table within "
            f"{timeout_seconds} seconds. Last SHOW DATA rows: {last!r}"
        )

    def compression_storage_summary(
        self,
        table_names: Sequence[str],
        *,
        baseline_table: str | None = None,
        title: str = "Compression declarations and current storage reports",
    ) -> pd.DataFrame:
        """Combine effective compression, logical rows, and compact storage metadata."""
        default_rows = self._metadata_rows(
            "SHOW FRONTEND CONFIG LIKE 'default_compression_type'"
        )
        default_compression = (
            str(default_rows[0].get("Value", "not shown")).upper()
            if default_rows else "not shown"
        )
        summary: list[dict[str, object]] = []
        for candidate in table_names:
            name = self._safe_table_name(candidate)
            create_rows = self._metadata_rows(f"SHOW CREATE TABLE `{name}`")
            if not create_rows:
                raise RuntimeError(f"SHOW CREATE TABLE returned no row for {name}.")
            ddl = str(create_rows[0].get("Create Table", ""))
            compression_match = re.search(
                r'"compression"\s*=\s*"([^"]+)"', ddl, re.IGNORECASE
            )
            if compression_match:
                compression = compression_match.group(1).upper()
                source = "table property"
            else:
                compression = default_compression
                source = "FE default"

            data_rows = self._metadata_rows(f"SHOW DATA FROM `{name}`")
            data_row = next(
                (row for row in data_rows if str(row.get("TableName", "")) == name), None
            )
            if data_row is None:
                raise RuntimeError(f"SHOW DATA returned no table row for {name}.")
            reported_bytes = self._capacity_bytes(data_row.get("Size", 0))
            partitions = self._metadata_rows(f"SHOW PARTITIONS FROM `{name}`")
            tablets = self._metadata_rows(f"SHOW TABLETS FROM `{name}`")
            tablet_ids = {str(row["TabletId"]) for row in tablets}
            replica_counts: dict[str, int] = {}
            for row in tablets:
                tablet_id = str(row["TabletId"])
                replica_counts[tablet_id] = replica_counts.get(tablet_id, 0) + 1
            summary.append({
                "table": name,
                "effective compression": compression,
                "resolved from": source,
                "logical rows": f"{int(data_row.get('RowCount', 0)):,}",
                "reported stored size": str(data_row.get("Size", "not shown")),
                "_reported_bytes": reported_bytes,
                "partitions": len(partitions),
                "tablets": len(tablet_ids),
                "replicas / tablet": self._number_range(list(replica_counts.values())),
            })
        if baseline_table is not None:
            baseline_table = self._safe_table_name(baseline_table)
            baseline_rows = [row for row in summary if row["table"] == baseline_table]
            if len(baseline_rows) != 1:
                raise ValueError(
                    f"Baseline table {baseline_table!r} is not in the comparison."
                )
            baseline_bytes = float(baseline_rows[0]["_reported_bytes"])
            if baseline_bytes <= 0:
                raise RuntimeError(
                    f"Baseline table {baseline_table} has no reported stored bytes."
                )
            for row in summary:
                saved = 1 - (float(row["_reported_bytes"]) / baseline_bytes)
                row["reported space saved vs baseline"] = f"{saved:.1%}"
        for row in summary:
            row.pop("_reported_bytes", None)
        frame = pd.DataFrame(summary)
        show_frame(title, frame)
        return frame

    @contextmanager
    def temporary_frontend_config(self, settings: Mapping[str, object]):
        """Apply mutable FE settings and restore every captured value on exit."""
        if not settings:
            yield {}
            return
        original: dict[str, str] = {}
        applied: list[str] = []
        try:
            for name, value in settings.items():
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                    raise ValueError(f"Unsafe FE configuration name: {name!r}")
                value_text = str(value)
                if not re.fullmatch(r"[A-Za-z0-9_.:+-]+", value_text):
                    raise ValueError(f"Unsafe FE configuration value for {name}: {value!r}")
                rows = self._metadata_rows(f"SHOW FRONTEND CONFIG LIKE '{name}'")
                if len(rows) != 1:
                    raise RuntimeError(f"FE configuration {name!r} was not found.")
                if str(rows[0].get("IsMutable", "")).lower() != "true":
                    raise RuntimeError(f"FE configuration {name!r} is not mutable.")
                original[name] = str(rows[0]["Value"])
                self.execute(
                    f"ADMIN SET FRONTEND CONFIG ('{name}' = '{value_text}')"
                )
                applied.append(name)
            yield original.copy()
        finally:
            for name in reversed(applied):
                self.execute(
                    f"ADMIN SET FRONTEND CONFIG ('{name}' = '{original[name]}')"
                )

    def wait_for_partition_count(
        self,
        table_name: str,
        *,
        expected_count: int,
        timeout_seconds: int = 60,
    ) -> pd.DataFrame:
        """Wait a bounded time for a dynamic table to expose the expected partitions."""
        table_name = self._safe_table_name(table_name)
        if not self._metadata_rows(f"SHOW TABLES LIKE '{table_name}'"):
            raise RuntimeError(
                f"{table_name} does not exist. Create it before waiting for partitions."
            )
        deadline = time.monotonic() + timeout_seconds
        rows: list[dict[str, object]] = []
        while time.monotonic() < deadline:
            rows = self._metadata_rows(
                f"SHOW PARTITIONS FROM `{table_name}` ORDER BY PartitionName"
            )
            if len(rows) == expected_count:
                return pd.DataFrame(rows)
            time.sleep(1)
        names = [str(row.get("PartitionName", "")) for row in rows]
        raise TimeoutError(
            f"{table_name} exposed {len(rows)} partitions after {timeout_seconds} seconds; "
            f"expected {expected_count}. Last names: {names!r}"
        )

    def wait_for_partition_removal(
        self,
        table_name: str,
        partition_name: str,
        *,
        timeout_seconds: int = 60,
    ) -> pd.DataFrame:
        """Show one live timer while the scheduler removes a named Partition."""
        table_name = self._safe_table_name(table_name)
        partition_name = self._safe_table_name(partition_name)
        if timeout_seconds < 1:
            raise ValueError("timeout_seconds must be positive.")
        if not self._metadata_rows(f"SHOW TABLES LIKE '{table_name}'"):
            raise RuntimeError(f"{table_name} does not exist.")

        def timer_html(elapsed: float, names: list[str], state: str) -> HTML:
            seconds = int(elapsed)
            elapsed_text = f"{seconds // 60:02d}:{seconds % 60:02d}"
            limit_text = f"{timeout_seconds // 60:02d}:{timeout_seconds % 60:02d}"
            label = {
                "running": "Waiting for the Dynamic Partition scheduler",
                "success": "The scheduler removed the expired Partition",
                "failure": "The Partition is still online",
            }[state]
            detail = (f"Elapsed {elapsed_text} / {limit_text} · "
                      f"target {partition_name} · online {len(names)} Partition(s)")
            return HTML(
                f'<div class="doris-status {state}">'
                f'<div class="doris-status-title">{html.escape(label)}</div>'
                f'<div class="doris-meta"><span class="doris-chip">'
                f'{html.escape(detail)}</span></div></div>'
            )

        started = time.monotonic()
        handle = display(timer_html(0, [], "running"), display_id=True)
        rows: list[dict[str, object]] = []
        while True:
            rows = self._metadata_rows(
                f"SHOW PARTITIONS FROM `{table_name}` ORDER BY PartitionName"
            )
            names = [str(row.get("PartitionName", "")) for row in rows]
            elapsed = time.monotonic() - started
            if partition_name not in names:
                handle.update(timer_html(elapsed, names, "success"))
                return pd.DataFrame(rows)
            if elapsed >= timeout_seconds:
                handle.update(timer_html(elapsed, names, "failure"))
                raise TimeoutError(
                    f"{partition_name} remains in {table_name} after "
                    f"{timeout_seconds} seconds; online Partitions: {names!r}"
                )
            handle.update(timer_html(elapsed, names, "running"))
            time.sleep(min(5.0, timeout_seconds - elapsed))

    def wait_for_hourly_partition_expiry(
        self,
        table_name: str,
        *,
        event_id: int,
        start_offset: int,
        timeout_seconds: int = 900,
    ) -> None:
        """Resume an hourly retention experiment after its real clock boundary."""
        table_name = self._safe_table_name(table_name)
        if not isinstance(event_id, int) or event_id < 0:
            raise ValueError("event_id must be a nonnegative integer.")
        if not isinstance(start_offset, int) or start_offset >= 0:
            raise ValueError("start_offset must be a negative number of hours.")
        if not self._metadata_rows(f"SHOW TABLES LIKE '{table_name}'"):
            raise RuntimeError(f"{table_name} does not exist. Run the setup first.")
        marker = self._metadata_rows(
            f"SELECT event_time FROM `{table_name}` WHERE event_id = {event_id}"
        )
        if not marker:
            card("The marked event is already absent; check the SQL answer and "
                 "current Partition window below.", "ok", "Hourly expiry already applied")
            return
        if len(marker) != 1:
            raise RuntimeError(f"Expected exactly one event {event_id} in {table_name}.")

        event_hour = pd.Timestamp(marker[0]["event_time"]).floor("h")
        expiry_at = event_hour + pd.Timedelta(hours=1 - start_offset)
        clock = self._metadata_rows("SELECT NOW() AS server_now")
        server_now = pd.Timestamp(clock[0]["server_now"])
        if server_now < expiry_at:
            remaining = expiry_at - server_now
            minutes = max(1, int(remaining.total_seconds() // 60) + 1)
            card(f"Return at or after {expiry_at:%Y-%m-%d %H:%M:%S} "
                 f"(Asia/Shanghai); about {minutes} minute(s) remain until the "
                 "whole hour becomes ineligible. Keep the container running and "
                 "rerun this cell then; do not rerun Section 2.",
                 "info", "The hourly retention boundary has not arrived")
            raise ReturnLater(
                f"rerun this cell at or after {expiry_at:%Y-%m-%d %H:%M} (Asia/Shanghai)."
            )

        partitions = self._metadata_rows(
            f"SHOW PARTITIONS FROM `{table_name}` ORDER BY PartitionName"
        )
        matches = []
        for partition in partitions:
            bounds = re.findall(
                r"\b\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\b",
                str(partition.get("Range", "")),
            )
            if len(bounds) >= 2 and pd.Timestamp(bounds[0]) <= event_hour < pd.Timestamp(bounds[1]):
                matches.append(str(partition["PartitionName"]))
        if len(matches) != 1:
            raise RuntimeError(
                f"Expected one Partition containing event {event_id} at {event_hour}; "
                f"found {matches!r}. Inspect SHOW PARTITIONS before continuing."
            )
        self.wait_for_partition_removal(
            table_name, matches[0], timeout_seconds=timeout_seconds
        )

    def dynamic_partition_status(
        self,
        table_name: str,
        *,
        title: str = "Dynamic Partition scheduler status",
    ) -> pd.DataFrame:
        """Report scheduler activity without repeating the table's DDL properties."""
        table_name = self._safe_table_name(table_name)
        rows = [
            row for row in self._metadata_rows("SHOW DYNAMIC PARTITION TABLES")
            if str(row.get("TableName", "")) == table_name
        ]
        if len(rows) != 1:
            raise RuntimeError(
                f"Expected one dynamic-partition status row for {table_name}; found {len(rows)}."
            )
        row = rows[0]
        state = str(row.get("State") or "not reported")
        last_run = str(row.get("LastSchedulerTime") or "not reported")
        card(
            f"State: {state} · Last scheduler run: {last_run}",
            "ok" if state.upper() == "NORMAL" else "fail",
            title,
        )
        if state.upper() != "NORMAL":
            details = "\n".join(
                f"{key}: {row.get(key) or 'not reported'}"
                for key in ("LastCreatePartitionMsg", "LastDropPartitionMsg")
            )
            show_log("Dynamic Partition scheduler diagnostics", details, opened=True)
        return pd.DataFrame([row])

    def partition_window_summary(
        self,
        table_name: str,
        *,
        title: str = "Current online Partition window",
    ) -> pd.DataFrame:
        """Show one row per Partition with its half-open bounds and logical row count."""
        table_name = self._safe_table_name(table_name)
        partitions = self._metadata_rows(
            f"SHOW PARTITIONS FROM `{table_name}` ORDER BY PartitionName"
        )
        if not partitions:
            raise RuntimeError(f"SHOW PARTITIONS returned no rows for {table_name}.")
        rows: list[dict[str, object]] = []
        for partition in partitions:
            name = self._safe_table_name(str(partition["PartitionName"]))
            bounds = re.findall(
                r"\b\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2}:\d{2})?\b",
                str(partition.get("Range", "")),
            )
            count_rows = self._metadata_rows(
                f"SELECT COUNT(*) AS row_count FROM `{table_name}` PARTITION (`{name}`)"
            )
            rows.append({
                "partition": name,
                "included from": bounds[0] if bounds else "not shown",
                "excluded at": bounds[1] if len(bounds) > 1 else "not shown",
                "logical rows": int(count_rows[0]["row_count"]),
            })
        frame = pd.DataFrame(rows)
        show_frame(title, frame)
        return frame

    def expect_statement_error(
        self,
        statement: str,
        *,
        contains: str,
        title: str,
    ) -> str:
        """Require a statement to fail for a specific, learner-visible reason."""
        try:
            self.execute(statement, show_errors=False)
        except Exception as exc:
            message = str(exc)
            if contains.lower() not in message.lower():
                raise AssertionError(
                    f"The statement failed, but not for the expected reason {contains!r}: "
                    f"{message}"
                ) from exc
            focused = next(
                (part.strip() for part in message.split(". ") if contains.lower() in part.lower()),
                contains,
            )
            card(focused, "ok", title)
            return message
        raise AssertionError("The statement succeeded; an expected failure was not observed.")

    def recycle_partition_summary(
        self,
        partition_name: str,
        *,
        partition_id: int,
        title: str = "Recoverable Partition in the catalog recycle bin",
    ) -> pd.DataFrame:
        """Display one exact recoverable Partition rather than the whole recycle bin."""
        partition_name = self._safe_table_name(partition_name)
        rows = [
            row for row in self._metadata_rows(
                f"SHOW CATALOG RECYCLE BIN WHERE NAME = '{partition_name}'"
            )
            if str(row.get("Type", "")).lower() == "partition"
            and int(row.get("PartitionId", -1)) == int(partition_id)
        ]
        if len(rows) != 1:
            raise RuntimeError(
                f"Expected Partition {partition_name} with ID {partition_id} in the "
                f"catalog recycle bin; found {len(rows)} matching rows."
            )
        frame = pd.DataFrame(rows)[["Type", "Name", "PartitionId", "DropTime"]]
        show_frame(title, frame)
        return frame
