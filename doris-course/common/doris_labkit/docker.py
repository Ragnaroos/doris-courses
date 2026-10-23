"""Docker and process helpers that report progress and failures in the notebook."""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Sequence

from .ui import card, show_log


def env_port(name: str, default: int) -> int:
    """Return the host port set in environment variable ``name``, or ``default``.

    The value is also stored in ``os.environ`` so that shell cells and
    ``docker compose`` started from this kernel see the same port.
    """
    raw = os.environ.get(name, "").strip()
    if not raw:
        port = default
    elif raw.isdigit() and 0 < int(raw) < 65536:
        port = int(raw)
    else:
        raise ValueError(f"{name}={raw!r} is not a TCP port number (1-65535).")
    os.environ[name] = str(port)
    return port


def port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Return True when something already accepts connections on ``host:port``."""
    with socket.socket() as probe:
        probe.settimeout(0.25)
        return probe.connect_ex((host, port)) == 0


def run(
    command: Sequence[str],
    *,
    check: bool = True,
    timeout: int | None = None,
    show: bool = False,
    stream: bool = False,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a command. ``stream`` prints output as it arrives; ``show`` logs it afterwards."""
    command = [str(part) for part in command]
    if stream:
        print("$ " + " ".join(command), flush=True)
        process = subprocess.Popen(
            command,
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
        return_code = process.wait(timeout=timeout)
        output = "".join(lines)
        result = subprocess.CompletedProcess(command, return_code, output, "")
        if check and result.returncode != 0:
            raise RuntimeError(f"Command failed with exit code {result.returncode}: {' '.join(command)}")
        return result
    result = subprocess.run(command, text=True, capture_output=True, timeout=timeout, cwd=cwd)
    combined = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
    if show:
        show_log("$ " + " ".join(command), combined)
    if check and result.returncode != 0:
        show_log("Command failed", combined)
        raise RuntimeError(f"Command failed with exit code {result.returncode}: {' '.join(command)}")
    return result


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
        if state.get("Status") == "restarting":
            # Its restart policy brings the container back, for example after a download at
            # startup timed out; if it never becomes healthy, the timeout below still applies.
            time.sleep(2)
            continue
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


def ensure_docker_ready(*, timeout_seconds: int = 180) -> None:
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
    container: str,
    *,
    wait_for_healthy: bool = True,
    timeout_seconds: int = 300,
    missing_hint: str = "Run the environment preparation cell first.",
) -> dict:
    """Idempotently make an existing container available again and return its state."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", container):
        raise ValueError("container must be a simple Docker container name.")

    ensure_docker_ready()
    state = container_inspect(container)
    if state is None:
        raise RuntimeError(f"Container {container!r} does not exist. {missing_hint}")

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
