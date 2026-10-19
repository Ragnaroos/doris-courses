"""Styled notebook output: status cards, SQL blocks, logs, and step progress."""

from __future__ import annotations

import html
from typing import Mapping

from IPython.display import HTML, display


# Styles for every component in this package. A course adds styles for its own
# activities by passing them to install_styles().
BASE_CSS = """
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
  @media (max-width:700px) {.doris-workflow-list{grid-template-columns:1fr}}
"""


def install_styles(*extra_css: str) -> None:
    """Add the shared output styles, plus any course-specific rules, to the notebook."""
    display(HTML("<style>" + BASE_CSS + "".join(extra_css) + "</style>"))


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


def show_sql(title: str, statement: str) -> None:
    display(HTML(
        '<div class="doris-code">'
        f'<div class="doris-code-title">{html.escape(title)}</div>'
        f'<pre>{html.escape(statement.strip())}</pre></div>'
    ))


def workflow_html(
    title: str,
    steps: Mapping[int, str],
    current: int,
    state: str,
    detail: str,
) -> HTML:
    """Render a numbered step list with a progress bar.

    ``state`` is "running", "success", or "failure" and applies to step
    ``current``; earlier steps show as complete.
    """
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


class ReturnLater(RuntimeError):
    """Stop a cell whose observation needs the real clock to advance first.

    The card shown before raising says when to come back. Raising keeps
    "Run All" from continuing into checks that cannot pass yet, and IPython
    renders this exception as one line instead of a traceback.
    """

    def _render_traceback_(self) -> list[str]:
        return [f"Stopped on purpose: {self}"]
