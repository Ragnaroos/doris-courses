"""Result DataFrames that keep SQL NULL and integers intact, and their HTML tables."""

from __future__ import annotations

import html
from typing import Mapping, Sequence

import pandas as pd
from IPython.display import HTML, display


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
