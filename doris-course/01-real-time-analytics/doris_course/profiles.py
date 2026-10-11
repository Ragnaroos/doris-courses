"""Profile-related entry points used by architecture and tuning labs."""

from contextlib import contextmanager
from dataclasses import dataclass
import re
from typing import Any, Mapping, Optional
from uuid import uuid4

import pandas as pd

from .ui import show_frame, show_log


def compare_profiles(lab: Any, *args: Any, **kwargs: Any):
    """Delegate a runtime-profile comparison to the shared lab session."""
    return lab.compare_profiles(*args, **kwargs)


@contextmanager
def session_settings(lab: Any, settings: Mapping[str, str]):
    """Apply temporary session settings, including restoration after partial setup."""
    connection = lab._require_connection()
    originals = {}
    try:
        with connection.cursor() as cursor:
            for name, value in settings.items():
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                    raise ValueError(f"Invalid session variable: {name!r}")
                cursor.execute("SHOW VARIABLES LIKE %s", (name,))
                rows = cursor.fetchall()
                row = next((r for r in rows if r["Variable_name"] == name), None)
                if row is None:
                    raise RuntimeError(f"Session variable {name} is unavailable on this Doris build.")
                originals[name] = str(row["Value"])
                cursor.execute(f"SET {name} = %s", (str(value),))
        yield
    finally:
        errors = []
        with connection.cursor() as cursor:
            for name, value in reversed(list(originals.items())):
                try:
                    cursor.execute(f"SET {name} = %s", (value,))
                except Exception as exc:
                    errors.append(f"{name}: {exc}")
        if errors:
            raise RuntimeError("Could not restore session settings: " + "; ".join(errors))


def scan_profile_excerpt(profile: str, *, detail: bool = False) -> str:
    """Select raw scan counters without adding merged and per-task values together.

    Preserve Fragment, host/Pipeline, PipelineTask and scan identity. Missing
    counters remain absent; this function never substitutes zeros or converts units.
    """
    if detail:
        if "DetailProfile" not in profile:
            return "DetailProfile is not present in this Query Profile."
        section = "DetailProfile" + profile.split("DetailProfile", 1)[1]
    else:
        if "MergedProfile:" not in profile:
            return "MergedProfile is not present in this Query Profile."
        section = profile.split("MergedProfile:", 1)[1].split("DetailProfile", 1)[0]
    context = {}
    selected = []
    scan_indent = None
    for line in section.splitlines():
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if re.match(r"Fragment\s+\d+", stripped):
            context = {"fragment": line}
        elif re.match(r"Pipeline\s+\d+", stripped):
            context.pop("task", None)
            context["pipeline"] = line
        elif stripped.startswith("PipelineTask("):
            context["task"] = line
        if scan_indent is not None and stripped and indent <= scan_indent:
            scan_indent = None
        if stripped.startswith("OLAP_SCAN_OPERATOR("):
            selected.extend(["", *context.values(), line])
            scan_indent = indent
        elif scan_indent is not None and re.match(
            r"- (?:RowsProduced|RowsRead|ScanRows|ScanBytes|RowsStatsFiltered|"
            r"RowsKeyRangeFiltered|RowsConditionsFiltered|RowsInvertedIndexFiltered|"
            r"RowsBloomFilterFiltered|ConditionCacheHit|ConditionCacheFilteredRows|"
            r"InvertedIndex[A-Za-z]+|ScannerCpuTime|IOTimer|CompressedBytesRead|"
            r"UncompressedBytesRead):", stripped
        ):
            selected.append(line)
    return "\n".join(selected).strip("\n") or "No OLAP scan counters are present in this section."


def distributed_scan_tasks(profile: str) -> pd.DataFrame:
    """Return each raw DetailProfile OLAP scan task without merging its counters."""
    if "DetailProfile" not in profile:
        raise ValueError("DetailProfile is not present in this Query Profile.")
    section = "DetailProfile" + profile.split("DetailProfile", 1)[1]
    current_host = None
    scan_indent = None
    current = None
    scans = []

    def finish() -> None:
        nonlocal current
        if current is not None:
            scans.append(current)
            current = None

    for line in section.splitlines():
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        host_match = re.match(
            r"Pipeline\s+\d+\(host=TNetworkAddress\(hostname:([^,]+),", stripped
        )
        if host_match:
            current_host = host_match.group(1)
        if scan_indent is not None and stripped and indent <= scan_indent:
            finish()
            scan_indent = None
        if stripped.startswith("OLAP_SCAN_OPERATOR("):
            finish()
            table_match = re.search(r"table_name=(.+?)\)\(id=", stripped)
            current = {
                "be_host": current_host or "unknown",
                "table": table_match.group(1) if table_match else "unknown",
                "tablet_ids": [],
                "scan_rows": None,
            }
            scan_indent = indent
        elif current is not None:
            tablet_match = re.match(r"- TabletIds:\s*\[([^]]*)\]", stripped)
            if tablet_match:
                current["tablet_ids"] = [
                    value.strip() for value in tablet_match.group(1).split(",") if value.strip()
                ]
            row_match = re.match(r"- ScanRows:\s*(.+)$", stripped)
            if row_match:
                value = row_match.group(1)
                exact = re.search(r"\(([0-9,]+)\)\s*$", value)
                plain = re.fullmatch(r"[0-9,]+", value.strip())
                if exact:
                    current["scan_rows"] = int(exact.group(1).replace(",", ""))
                elif plain:
                    current["scan_rows"] = int(value.replace(",", ""))
    finish()
    if not scans:
        raise ValueError("No per-instance OLAP scan operators were found in DetailProfile.")
    return pd.DataFrame(scans)


def distributed_scan_summary(profile: str) -> pd.DataFrame:
    """Summarize DetailProfile scan instances by BE without mixing merged counters.

    Each DetailProfile OLAP scan belongs to one Pipeline on one BE. Tablet IDs
    are deduplicated per host, while ScanRows is summed only across those
    per-instance scan operators. The complete raw Profile remains the source of
    truth and should be retained beside this learner-facing summary.
    """
    tasks = distributed_scan_tasks(profile)

    rows = []
    for (host, table), group in tasks.groupby(["be_host", "table"], sort=True):
        tablets = sorted({tablet for values in group["tablet_ids"] for tablet in values})
        scan_rows = group["scan_rows"].dropna()
        rows.append({
            "be_host": host,
            "table": table,
            "scan_instances": len(group.index),
            "selected_tablets": len(tablets),
            "scan_rows": int(scan_rows.sum()) if len(scan_rows.index) else "not shown",
        })
    return pd.DataFrame(rows)


def distributed_scan_profile_excerpt(profile: str) -> str:
    """Keep the raw DetailProfile hierarchy and only essential scan lines."""
    if "DetailProfile" not in profile:
        return "DetailProfile is not present in this Query Profile."
    section = "DetailProfile" + profile.split("DetailProfile", 1)[1]
    fragment = pipeline = task = None
    emitted_fragment = emitted_pipeline = None
    scan_indent = None
    selected = []

    for line in section.splitlines():
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if scan_indent is not None and stripped and indent <= scan_indent:
            scan_indent = None
        if re.match(r"Fragment\s+\d+", stripped):
            fragment = line
            pipeline = task = None
        elif re.match(r"Pipeline\s+\d+\(host=", stripped):
            pipeline = line
            task = None
        elif stripped.startswith("PipelineTask("):
            task = line

        if stripped.startswith("OLAP_SCAN_OPERATOR("):
            if fragment != emitted_fragment:
                if selected:
                    selected.append("")
                selected.append(fragment or "Fragment unknown:")
                emitted_fragment = fragment
                emitted_pipeline = None
            if pipeline != emitted_pipeline:
                selected.append(pipeline or "  Pipeline(host=unknown):")
                emitted_pipeline = pipeline
            if task is not None:
                selected.append(task)
            selected.append(line)
            scan_indent = indent
        elif scan_indent is not None and (
            stripped.startswith("- TabletIds:") or stripped.startswith("- ScanRows:")
        ):
            selected.append(line)

    return "\n".join(selected) or "No OLAP scan operators are present in DetailProfile."


def show_result_change(
    current: pd.DataFrame,
    title: str,
    baseline: pd.DataFrame,
    *,
    match: Mapping[str, object],
    metrics: tuple[str, ...],
    expected_changes: Optional[Mapping[str, object]] = None,
) -> None:
    """Display and optionally verify changes for one matched result row."""
    before = baseline
    after = current
    for column, value in match.items():
        if column not in before.columns or column not in after.columns:
            raise ValueError(f"Match column {column!r} is missing from the result.")
        before = before.loc[before[column] == value]
        after = after.loc[after[column] == value]
    if len(before.index) != 1 or len(after.index) != 1:
        raise ValueError("The match must identify exactly one row before and after.")

    row = dict(match)
    for metric in metrics:
        if metric not in before.columns or metric not in after.columns:
            raise ValueError(f"Metric {metric!r} is missing from the result.")
        before_value = before.iloc[0][metric]
        after_value = after.iloc[0][metric]
        change = after_value - before_value
        row[f"{metric}_before"] = before_value
        row[f"{metric}_after"] = after_value
        row[f"{metric}_change"] = change
        if expected_changes is not None and metric in expected_changes:
            expected = expected_changes[metric]
            if change != expected:
                raise AssertionError(
                    f"Expected {metric!r} to change by {expected!r}, got {change!r}."
                )
    show_frame(title, pd.DataFrame([row]))


@dataclass
class QueryEvidence:
    """One fully fetched query, its plan, and its own runtime Profile."""

    rows: pd.DataFrame
    plan: str
    profile_id: str
    profile: str

    def show_result(self, title: str) -> None:
        """Display the already captured result without rerunning the query."""
        show_frame(title, self.rows)

    def show_change(
        self,
        title: str,
        baseline: pd.DataFrame,
        *,
        match: Mapping[str, object],
        metrics: tuple[str, ...],
        expected_changes: Optional[Mapping[str, object]] = None,
    ) -> None:
        """Display and optionally verify changes for one matched result row."""
        show_result_change(
            self.rows,
            title,
            baseline,
            match=match,
            metrics=metrics,
            expected_changes=expected_changes,
        )

    def show_scan_plan(self, title: str, *, include_complete: bool = True) -> None:
        """Highlight selected scan lines and optionally retain the complete plan folded."""
        scans = [line for line in self.plan.splitlines() if re.match(r"\s*TABLE:", line)]
        show_log(title, "\n".join(scans) or "Selected TABLE lines are not shown.", opened=True)
        if include_complete:
            show_log(f"{title}: complete EXPLAIN", self.plan)

    def show_profile_scan_rows(self, title: str) -> None:
        """Show raw merged scan row counters with their operator context."""
        excerpt = scan_profile_excerpt(self.profile)
        lines = [line for line in excerpt.splitlines()
                 if not line.lstrip().startswith("- ")
                 or re.match(r"\s*- (?:ScanRows|RowsProduced):", line)]
        show_log(f"{title} · MergedProfile", "\n".join(lines), opened=True)
        show_log(f"{title}: complete raw Query Profile · {self.profile_id}", self.profile)

    def show_scan_rows(self, title: str) -> None:
        """Backward-compatible alias for show_profile_scan_rows()."""
        self.show_profile_scan_rows(title)

    def show_distributed_scans(self, title: str) -> None:
        """Show the BE hosts and per-instance scan work from DetailProfile."""
        show_frame(title, self.distributed_scans())
        show_log(f"{title}: complete raw Query Profile · {self.profile_id}", self.profile)

    def show_distributed_scan_profile(self, title: str) -> None:
        """Show a cropped, structurally unchanged DetailProfile scan excerpt."""
        show_log(title, distributed_scan_profile_excerpt(self.profile), opened=True)
        show_log(f"{title}: complete raw Query Profile · {self.profile_id}", self.profile)

    def distributed_scans(self) -> pd.DataFrame:
        """Return the per-BE DetailProfile scan summary for assertions."""
        return distributed_scan_summary(self.profile)

    def distributed_scan_tasks(self) -> pd.DataFrame:
        """Return individual DetailProfile scan tasks for controlled comparisons."""
        return distributed_scan_tasks(self.profile)

    def show_distributed_plan(self, title: str) -> None:
        """Show the SQL-relevant distributed operators and scan scope from EXPLAIN."""
        keep = re.compile(
            r"^\s*(?:PLAN FRAGMENT\s+\d+|PARTITION:|VRESULT SINK|"
            r"STREAM DATA SINK|EXCHANGE ID:|HASH_PARTITIONED:|UNPARTITIONED$|"
            r"\d+:V(?:OlapScanNode|AGGREGATE|SORT|(?:MERGING-)?EXCHANGE)|"
            r"output:|group by:|order by:|TABLE:|partitions=|tablets=|"
            r"cardinality=.*numNodes=)"
        )
        excerpt = "\n".join(line for line in self.plan.splitlines() if keep.match(line))
        show_log(title, excerpt or "Distributed plan lines are not shown.", opened=True)
        show_log(f"{title}: complete EXPLAIN", self.plan)

    def show(self, title: str, *, detail: bool = False) -> None:
        show_frame(f"{title}: query result", self.rows)
        scans = [line for line in self.plan.splitlines() if re.match(r"\s*TABLE:", line)]
        show_log(
            f"{title}: EXPLAIN selected scans",
            "\n".join(scans) or "Selected TABLE lines are not shown.",
            opened=True,
        )
        show_log(
            f"{title}: MergedProfile scan counters · {self.profile_id}",
            scan_profile_excerpt(self.profile), opened=True,
        )
        if detail:
            show_log(
                f"{title}: DetailProfile scan counters (each PipelineTask)",
                scan_profile_excerpt(self.profile, detail=True), opened=True,
            )
        show_log(f"{title}: complete raw Query Profile · {self.profile_id}", self.profile)


def capture_query(lab: Any, statement: str, *, settings=None) -> QueryEvidence:
    """Capture fresh BE execution evidence on the existing local course session.

    Reuses DorisLab's local FE endpoint and bounded Profile lookup. A unique SQL
    comment disambiguates concurrent copies of the same query. Caches controlled
    here are SQL, query and condition caches, not OS/storage/index caches.
    """
    query = statement.strip().rstrip(";")
    if not re.match(r"SELECT\b", query, re.I):
        raise ValueError("capture_query requires a SELECT statement.")
    controlled = dict(settings or {})
    controlled.update({
        "enable_profile": "true", "profile_level": "2",
        "enable_sql_cache": "false", "enable_query_cache": "false",
        "enable_condition_cache": "false",
    })
    with session_settings(lab, controlled):
        before = {str(row["Profile ID"]) for row in lab._query_profiles()}
        tagged_query = f"{query} /* course_profile_{uuid4().hex} */"
        with lab._require_connection().cursor() as cursor:
            cursor.execute("EXPLAIN " + query)
            plan = "\n".join(str(next(iter(row.values()))) for row in cursor.fetchall())
            cursor.execute(tagged_query)
            records = cursor.fetchall()
            columns = [column[0] for column in cursor.description]
        profile_id = lab._latest_profile_id(tagged_query, exclude=before)
        profile = lab._profile_text(profile_id)
        return QueryEvidence(pd.DataFrame(records, columns=columns), plan, profile_id, profile)


__all__ = [
    "compare_profiles", "capture_query", "session_settings", "QueryEvidence",
    "distributed_scan_profile_excerpt", "distributed_scan_summary", "distributed_scan_tasks",
    "scan_profile_excerpt", "show_result_change",
]
