"""Find Doris Query Profiles, fetch their text, and read values out of it."""

from __future__ import annotations

import base64
import re
import time
import urllib.parse
import urllib.request
from typing import Callable, Mapping


def normalize_statement(statement: str) -> str:
    """Return a statement in the form used to match it against SHOW QUERY PROFILE rows."""
    return " ".join(statement.strip().rstrip(";").split()).lower()


def last_query_id(connection) -> str:
    """Return the ID of the last query in the connection's session; a query's Profile ID is its query ID.

    Every statement that Doris runs as a query counts, this one too, so call it
    right after the query.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT last_query_id() AS query_id")
        row = cursor.fetchone()
    return str(row["query_id"] if isinstance(row, Mapping) else row[0])


def find_profile(connection, query_id: str, *, timeout_seconds: float = 10) -> dict | None:
    """Return the SHOW QUERY PROFILE row of the query ``query_id``, or None.

    SHOW QUERY PROFILE lists the FE's most recent profiles. A query that ran in a
    session with ``enable_profile = true`` appears there once it has finished;
    the list is read again until it does or the time is up.
    """
    deadline = time.monotonic() + timeout_seconds
    while True:
        with connection.cursor() as cursor:
            cursor.execute("SHOW QUERY PROFILE")
            rows = cursor.fetchall()
        for row in rows:
            if str(row.get("Profile ID")) == query_id:
                return row
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.5)


def fetch_profile_text(
    http_url: str,
    profile_id: str,
    *,
    user: str = "root",
    password: str = "",
    ready: Callable[[str], bool] = lambda text: True,
    timeout_seconds: float = 20,
) -> str:
    """Return the text of a Query Profile from the FE HTTP API, ``/api/profile/text``.

    The BEs report their part of a profile after the query has finished, so the
    first text can be incomplete. It is fetched again until ``ready`` accepts it
    or the time is up; the last text is returned either way.
    """
    url = f"{http_url}/api/profile/text?{urllib.parse.urlencode({'query_id': profile_id})}"
    token = base64.b64encode(f"{user}:{password}".encode()).decode("ascii")
    request = urllib.request.Request(url, headers={"Authorization": f"Basic {token}"})
    deadline = time.monotonic() + timeout_seconds
    while True:
        with urllib.request.urlopen(request, timeout=10) as response:
            text = response.read().decode("utf-8", errors="replace")
        if ready(text) or time.monotonic() >= deadline:
            return text
        time.sleep(0.5)


def profile_metric(profile: str, metric: str) -> str:
    """Return the first value of ``metric`` in a Profile, or "not shown"."""
    match = re.search(rf"(?im)^\s*-?\s*{re.escape(metric)}:\s*(?:sum\s+)?([^,\n]+)", profile)
    return match.group(1).strip() if match else "not shown"


def profile_row_sum(profile: str, metric: str) -> int | str:
    """Add up the exact values of a per-instance counter such as RowsRead.

    Doris prints large counters as ``1.234K (1234)``; the exact number in
    parentheses is used when present.
    """
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
