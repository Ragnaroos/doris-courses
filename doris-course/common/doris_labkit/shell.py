"""Run learner-visible Bash from a notebook cell with live progress."""

from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path
from typing import Mapping

from IPython.display import display

from .ui import card, show_log, workflow_html

# Image downloads print these words; while one is running, its progress is a
# better step detail than the other lines Docker prints in between.
PULL_TOKENS = ("Pulling", "Downloading", "Download complete", "Pull complete")


def run_shell(script: str, *, title: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run ``script`` with Bash in ``cwd``.

    A script that announces its steps with ``echo "[N/TOTAL] label"`` gets a
    step panel that follows those lines; any other script streams its output.
    A non-zero exit status shows the full log and raises RuntimeError.
    """
    markers = {
        int(number): label
        for number, _total, label in re.findall(r'echo\s+"\[(\d+)/(\d+)\]\s+([^"\n]+)"', script)
    }
    if markers:
        return _run_with_steps(script, title=title, steps=markers, cwd=cwd)

    card("Command in progress", "info", title)
    started_at = time.perf_counter()
    process = subprocess.Popen(
        ["/bin/bash", "-lc", script.strip()],
        cwd=cwd,
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
    result = subprocess.CompletedProcess(["/bin/bash", "-lc", script.strip()], return_code, output, "")
    if return_code != 0:
        card(f"Bash exited with status {return_code} after {elapsed:.1f} seconds.", "fail", f"Failed: {title}")
        if output:
            show_log("Diagnostic details", output, opened=True)
        raise RuntimeError(f"{title} failed with exit status {return_code}.")
    card(f"Completed in {elapsed:.1f} seconds", "ok", f"Passed: {title}")
    if output:
        show_log("View full command log", output)
    return result


def _run_with_steps(
    script: str,
    *,
    title: str,
    steps: Mapping[int, str],
    cwd: Path,
) -> subprocess.CompletedProcess[str]:
    current = 1
    detail = "Starting..."
    handle = display(workflow_html(title, steps, current, "running", detail), display_id=True)
    started_at = time.perf_counter()
    process = subprocess.Popen(
        ["/bin/bash", "-lc", script.strip()],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )
    lines: list[str] = []
    last_update = 0.0
    pull_reported = False
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
            pull_reported = False
        elif clean:
            if any(token in clean for token in PULL_TOKENS):
                detail = clean
                pull_reported = True
            elif not pull_reported:
                detail = clean
        now = time.monotonic()
        if force_update or now - last_update >= 0.35:
            handle.update(workflow_html(title, steps, current, "running", detail))
            last_update = now

    process.stdout.close()
    return_code = process.wait()
    elapsed = time.perf_counter() - started_at
    output = "".join(lines)
    result = subprocess.CompletedProcess(["/bin/bash", "-lc", script.strip()], return_code, output, "")
    if return_code != 0:
        handle.update(workflow_html(title, steps, current, "failure", detail))
        show_log("View diagnostic log", output, opened=True)
        raise RuntimeError(f"{title} failed with exit status {return_code}.")

    handle.update(workflow_html(title, steps, max(steps), "success", ""))
    card(f"Completed in {elapsed:.1f} seconds", "ok", f"Passed: {title}")
    if output:
        show_log("View full command log", output)
    return result
