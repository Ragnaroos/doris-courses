"""Start the Doris MCP Server the way an MCP Host does, and record what it returns.

A Host such as Claude Desktop runs the launcher as a child process, with only
a few inherited environment variables, and exchanges MCP messages over the
process's standard input and output. ``run_host_session`` does the same with
the MCP Python SDK, so a notebook can check the launcher, the protected
environment file, and the Doris route before a Host uses them.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import anyio
from mcp import StdioServerParameters, stdio_client
from mcp.client.client import Client

# The protocol handshake that desktop Hosts use today (MCP initialize).
HOST_MODE = "legacy"


@dataclass
class ToolCall:
    """One tools/call request and the structured result the Server returned."""

    tool: str
    arguments: dict[str, Any]
    result: dict[str, Any]
    is_error: bool
    seconds: float


@dataclass
class HostSession:
    """What a Host would have seen: the handshake, the tool list, and each call."""

    server: str = ""
    protocol_version: str = ""
    tools: list[str] = field(default_factory=list)
    calls: list[ToolCall] = field(default_factory=list)
    error: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


def _innermost(error: BaseException) -> BaseException:
    """Return the first leaf of nested exception groups."""
    while isinstance(error, BaseExceptionGroup) and error.exceptions:
        error = error.exceptions[0]
    return error


def _structured(result) -> dict[str, Any]:
    if result.structured_content is not None:
        return dict(result.structured_content)
    for item in result.content:
        text = getattr(item, "text", None)
        if text:
            try:
                return json.loads(text)
            except ValueError:
                return {"text": text}
    return {}


async def _exchange(client: Client, requests: Sequence[tuple[str, str | None, dict]],
                    record: HostSession) -> None:
    info = client.server_info
    record.server = f"{info.name} {info.version}".strip() if info else "(not reported)"
    record.protocol_version = client.protocol_version
    record.tools = [tool.name for tool in (await client.list_tools()).tools]
    for domain, child, arguments in requests:
        started = time.perf_counter()
        discovery = await client.call_tool(domain, {})
        manifest = _structured(discovery)
        record.calls.append(ToolCall(domain, {}, manifest, bool(discovery.is_error),
                                     time.perf_counter() - started))
        if child is None or discovery.is_error:
            continue
        request = {
            "child_tool": child,
            "arguments": dict(arguments),
            "manifest_version": manifest.get("manifest_version", ""),
        }
        started = time.perf_counter()
        result = await client.call_tool(domain, request)
        record.calls.append(ToolCall(domain, request, _structured(result), bool(result.is_error),
                                     time.perf_counter() - started))


async def _session(launcher: Path, requests: Sequence[tuple[str, str | None, dict]],
                   record: HostSession, errlog, timeout_seconds: int) -> None:
    params = StdioServerParameters(command=str(launcher), cwd="/")
    with anyio.fail_after(timeout_seconds):
        async with Client(stdio_client(params, errlog=errlog), mode=HOST_MODE) as client:
            await _exchange(client, requests, record)


def run_host_session(
    launcher: Path,
    requests: Sequence[tuple[str, str | None, dict]] = (),
    *,
    timeout_seconds: int = 120,
) -> HostSession:
    """Start ``launcher`` over stdio, list its tools, and run ``requests``.

    Each request is ``(domain, child, arguments)``: the domain is called with
    ``{}`` to discover its children and manifest version, then, unless
    ``child`` is None, called again with that child, the arguments, and the
    manifest version. The working directory is ``/`` and only the MCP SDK's
    safe environment variables are inherited, as for a desktop Host. Errors
    are recorded in the returned session rather than raised.
    """
    record = HostSession()
    with tempfile.TemporaryFile("w+", encoding="utf-8") as errlog:
        def run() -> None:
            asyncio.run(_session(launcher, requests, record, errlog, timeout_seconds))

        # Jupyter already runs an event loop in this thread; use a fresh one.
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            try:
                pool.submit(run).result()
            except BaseException as error:  # noqa: BLE001 - reported to the learner
                leaf = _innermost(error)
                if isinstance(leaf, TimeoutError):
                    record.error = f"The Server did not answer within {timeout_seconds} seconds."
                else:
                    record.error = f"{type(leaf).__name__}: {leaf}"
        errlog.seek(0)
        record.stderr = errlog.read()
    return record
