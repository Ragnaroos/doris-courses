"""Read values out of Doris Query Profile text."""

from __future__ import annotations

import re


def normalize_statement(statement: str) -> str:
    """Return a statement in the form used to match it against SHOW QUERY PROFILE rows."""
    return " ".join(statement.strip().rstrip(";").split()).lower()


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
