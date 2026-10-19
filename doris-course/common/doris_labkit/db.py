"""Run SQL against Doris from a notebook and show results or errors readably."""

from __future__ import annotations

from typing import Mapping, Sequence

import pymysql

from .docker import wait_for_port
from .results import result_frame, show_frame
from .ui import card, show_log, show_sql


def connect_doris(
    host: str = "127.0.0.1",
    port: int = 9030,
    *,
    user: str = "root",
    password: str = "",
    connect_timeout: int = 10,
):
    """Wait for the FE query port, then open an autocommit connection with dict rows."""
    wait_for_port(host, port)
    return pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=connect_timeout,
        cursorclass=pymysql.cursors.DictCursor,
    )


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
    A trailing semicolon is removed before the statement is sent.
    ``display_statement`` replaces the executed text in error details, so
    credentials expanded into ``statement`` are never shown.
    """
    clean = statement.strip().rstrip(";").rstrip()
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


def sql_string(value: str) -> str:
    """Escape a value for use inside a double-quoted SQL string literal."""
    return value.replace("\\", "\\\\").replace('"', '\\"')
