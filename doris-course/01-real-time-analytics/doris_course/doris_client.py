from __future__ import annotations

import html
import csv
import http.client
import io
import json
import os
import platform
import re
import socket
import subprocess
import textwrap
import time
import urllib.request
import urllib.parse
import urllib.error
import uuid
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd
import pymysql
import yaml
from IPython.display import HTML, Javascript, display

from doris_labkit.db import connect_doris, report_sql_error, sql, sql_string
from doris_labkit.docker import (
    container_inspect,
    docker_preflight,
    ensure_network,
    ensure_volume,
    run,
    wait_for_health,
)
from doris_labkit import docker as labkit_docker
from doris_labkit.profiles import (
    fetch_profile_text,
    last_query_id,
    normalize_statement,
    profile_metric,
    profile_row_sum,
)
from doris_labkit.results import result_frame, show_frame
from doris_labkit.shell import run_shell
from doris_labkit.ui import ReturnLater, card, progress_step, show_log, show_sql, workflow_html
from doris_labkit.ui import install_styles as install_shared_styles

from . import environment as env


# Every notebook uses the course root as its runtime workspace, even when the
# notebook file itself lives several module directories below it.
LAB_DIR = Path(__file__).resolve().parent.parent


def expected_results() -> dict:
    """Return datasets/expected_results.yaml: the numbers the Labs check."""
    return yaml.safe_load((LAB_DIR / "datasets/expected_results.yaml").read_text(encoding="utf-8"))

# Styles for the components only this course uses: the cover, flow diagrams,
# and the load-method matching activity. doris_labkit styles everything else.
ACTIVITY_CSS = """
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
    .doris-flow-step{flex-basis:100%}
    .doris-scenario-grid{grid-template-columns:1fr}.doris-match-head{display:block}
    .doris-match-score{display:inline-block;margin-top:8px}.doris-contract{grid-template-columns:82px 1fr}}
"""


def install_styles() -> None:
    install_shared_styles(ACTIVITY_CSS)


class EnvironmentNotReady(RuntimeError):
    """A step stopped because the environment or its data is not ready.

    The card shown before raising says why and what to do.
    """

    def _render_traceback_(self) -> list[str]:
        return [f"Stopped: {self}"]


class WaitTimedOut(TimeoutError):
    """A bounded wait ended before Doris reached the expected state.

    The card and table shown before raising describe the last state seen.
    """

    def _render_traceback_(self) -> list[str]:
        return [f"Timed out: {self}"]


# The tables each Lab reads from earlier Labs: table -> (rows when complete, the Lab that builds it).
PREREQUISITES = {
    2: {"events": (10_158_080, "Lab 1 (Start Doris and Build a Baseline Dataset)")},
    4: {"events": (10_158_080, "Lab 1 (Start Doris and Build a Baseline Dataset)")},
    5: {"events_modelled": (10_158_080, "Lab 4 (Model Data for Analytical Workloads)")},
    6: {"events_modelled": (10_158_080, "Lab 4 (Model Data for Analytical Workloads)")},
    8: {
        "events_modelled": (10_158_080, "Lab 4 (Model Data for Analytical Workloads)"),
        "dim_products": (204_231, "Lab 6 (Joining Data in Apache Doris)"),
    },
    10: {"events_modelled": (10_158_080, "Lab 4 (Model Data for Analytical Workloads)")},
}


def s3_tvf(config: Mapping[str, str]) -> str:
    """Return the S3 TVF that reads the course's public bucket without credentials.

    ANONYMOUS stops the BE from trying the AWS default credential chain (for
    example the EC2 metadata address) before it sends unsigned requests. The
    two timeouts replace Doris's defaults (1 s to connect, 3 s without data),
    which fail over a slow network or a proxy with "curlCode: 28".
    """
    properties = {
        "uri": config["uri"],
        "s3.endpoint": config["endpoint"],
        "s3.region": config["region"],
        "s3.credentials_provider_type": "ANONYMOUS",
        "s3.connection.timeout": "10000",
        "s3.connection.request.timeout": "30000",
        "format": config["format"],
    }
    body = ",\n".join(f'    "{key}" = "{sql_string(value)}"' for key, value in properties.items())
    return f"S3(\n{body}\n)"


class DorisLab:
    """Learner-facing façade shared by the Doris course notebooks.

    The notebook keeps the SQL visible while this class owns environment
    branching, expected values, progress, and styled diagnostics.
    """

    DORIS_IMAGE = env.DORIS_IMAGE
    DORIS_CONTAINER = env.DORIS_CONTAINER
    DORIS_NETWORK = env.DORIS_NETWORK
    FE_VOLUME = env.FE_VOLUME
    BE_VOLUME = env.BE_VOLUME
    # The course's public bucket; datasets/events.yaml describes the same objects.
    S3_CONFIG = {
        "uri": "s3://doris-courses-public-dataset/doris-course/events/v1/events-*.parquet",
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
    # The 1,024 records that Lab 3 loads with Stream Load and with Routine Load.
    LAB3_SAMPLE = expected_results()["lab3_sample"]

    def __init__(
        self,
        lab_dir: Path | None = None,
        *,
        connection_host: str = "127.0.0.1",
        connection_port: int = env.QUERY_PORT,
        profile_http_host: str | None = None,
        profile_http_port: int = env.HTTP_PORT,
        ready_title: str = "Lab tools are ready",
        ready_message: str = "You can now continue to Section 1 and run the remaining cells in order.",
    ) -> None:
        self.lab_dir = (lab_dir or LAB_DIR).resolve()
        self.connection = None
        self._connection_host = connection_host
        self._connection_port = connection_port
        self._profile_http_host = profile_http_host or connection_host
        self._profile_http_port = profile_http_port
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

    @staticmethod
    def _timed_out(title: str, message: str, last_state: pd.DataFrame | None = None,
                   hint: str = "") -> WaitTimedOut:
        """Show why a bounded wait ended and return the exception to raise."""
        card(f"{message} {hint}".strip(), "fail", title)
        if last_state is not None and not last_state.empty:
            show_frame("Last state seen", last_state)
        return WaitTimedOut(message)

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
                self.connection = None
                address = f"{self._connection_host}:{self._connection_port}"
                card(
                    f"Nothing answers on {address}. {self._start_hint()} "
                    "A kernel restart clears only the Python connection; containers, "
                    "volumes, and tables remain.",
                    "fail",
                    "Doris is not reachable",
                )
                raise EnvironmentNotReady(f"Doris is not reachable on {address}.") from exc
        return self.connection

    def _start_hint(self) -> str:
        """Say how to start the environment this Lab connects to."""
        if self._connection_port == env.QUERY_PORT and self._connection_host == "127.0.0.1":
            return (
                f"Start the sandbox with the Restart cell at the end of any Lab, or run "
                f"`docker start {env.DORIS_CONTAINER}`, then rerun this cell. A new sandbox "
                "comes from Lab 1, Section 2. If you set DORIS_RTA_QUERY_PORT, start Jupyter "
                "with the same value."
            )
        return "Start the Module 9 cluster with Section 1.1 of Lab 9, then rerun this cell."

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
        normalized = " ".join(statement.upper().split())
        if columns is None and normalized == "SHOW FRONTENDS":
            columns = ["Name", "Host", "Role", "IsMaster", "Join", "Alive", "Version"]
        elif columns is None and normalized == "SHOW BACKENDS":
            columns = [
                "BackendId", "Host", "Alive", "SystemDecommissioned", "TabletNum", "Version",
            ]
        return sql(
            connection,
            statement.strip(),
            title=title,
            show_statement=False,
            final=final,
            columns=columns,
        )

    def query(self, statement: str):
        """Execute a SQL query and return all rows without displaying them."""
        connection = self._require_connection()
        statement = statement.strip()
        with connection.cursor() as cursor:
            try:
                cursor.execute(statement)
                rows = cursor.fetchall() if cursor.description else []
            except pymysql.MySQLError as error:
                report_sql_error(None, statement, error)
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
        return sql(
            connection,
            statement.strip(),
            show_statement=False,
            quiet_success=True,
            show_errors=show_errors,
        )

    def insert(
        self,
        statement: str,
        *,
        title: str = "Insert completed",
        expected_rows: int | None = None,
        show: bool = True,
    ) -> int:
        """Run a learner-visible data insert and report its wall-clock duration."""
        started_at = time.perf_counter()
        affected = self.execute(statement)
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
        show_log(f"Complete SHOW CREATE TABLE {table_name} output", ddl)
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
        raw = pd.DataFrame(partitions)
        columns = [c for c in ("PartitionName", "State", "Range", "DistributionKey", "Buckets", "RowCount")
                   if c in raw.columns]
        show_log(f"Complete SHOW PARTITIONS FROM {table_name} output", raw[columns].to_string(index=False))
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
        raw = pd.DataFrame(tablets)
        columns = [c for c in ("TabletId", "BackendId", "Version", "RowCount", "VersionCount", "LocalDataSize")
                   if c in raw.columns]
        show_log(f"Complete SHOW TABLETS FROM {table_name} output", raw[columns].to_string(index=False))
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
            self.show_statements(f"SHOW TABLETS FROM {table_name}", "SHOW BACKENDS")
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
        self.show_statements(f"SHOW TABLETS FROM {self._safe_table_name(table_name)}", "SHOW BACKENDS")
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
        self.show_statements(f"SHOW TABLETS FROM {table_name}", "SHOW BACKENDS")
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

        started = time.monotonic()
        deadline = started + timeout_seconds
        metadata_rows = None
        partition_rows = None

        def progress(state: str = "running") -> HTML:
            label = ("Waiting for Tablet and Partition reports" if state == "running"
                     else "Tablet metadata wait stopped")
            reported = lambda value: "not yet polled" if value is None else f"{value:,}"
            details = (
                f"Table {table_name} · expected {expected_rows:,} committed rows · "
                f"Tablet rows {reported(metadata_rows)} · Partition rows {reported(partition_rows)} · "
                f"Elapsed {time.monotonic() - started:.0f}s / {timeout_seconds}s"
            )
            return HTML(
                f'<div class="doris-status {state}"><div class="doris-status-title">'
                f'{html.escape(label)}</div><div>{html.escape(details)}</div></div>'
            )

        handle = display(progress(), display_id=True)
        try:
            while time.monotonic() < deadline:
                tablets = self._metadata_rows(f"SHOW TABLETS FROM `{table_name}`")
                per_tablet: dict[str, int] = {}
                for row in tablets:
                    tablet_id = str(row["TabletId"])
                    # SHOW TABLETS has one row per replica. Keep the newest
                    # reported count of each logical Tablet instead of adding copies.
                    per_tablet[tablet_id] = max(
                        per_tablet.get(tablet_id, 0), int(row["RowCount"])
                    )
                metadata_rows = sum(per_tablet.values())
                partitions = self._metadata_rows(f"SHOW PARTITIONS FROM `{table_name}`")
                partition_rows = sum(max(int(row.get("RowCount", 0)), 0) for row in partitions)
                if handle is not None:
                    handle.update(progress())
                if metadata_rows == expected_rows and partition_rows == expected_rows:
                    if handle is not None:
                        handle.update(HTML(""))
                    card(
                        f"{len(per_tablet)} tablets and {len(partitions)} partition(s) report all "
                        f"{expected_rows:,} rows (waited {time.monotonic() - started:.0f} seconds)",
                        "ok",
                        f"Tablet reports for {table_name} are complete",
                    )
                    self.show_statements(
                        f"SELECT COUNT(*) AS row_count FROM {table_name}",
                        f"SHOW TABLETS FROM {table_name}",
                        f"SHOW PARTITIONS FROM {table_name}",
                        title="SQL behind this check (the two SHOW statements repeat until their counts match)",
                    )
                    return
                time.sleep(2)
        except Exception:
            if handle is not None:
                handle.update(progress("failure"))
            raise
        if handle is not None:
            handle.update(progress("failure"))
        raise self._timed_out(
            "Tablet reports are late",
            f"{table_name} has the expected {query_rows:,} committed rows, but after "
            f"{timeout_seconds} seconds its tablets report {metadata_rows} rows and its "
            f"partitions report {partition_rows} rows instead of {expected_rows:,}.",
            hint="Each BE reports tablet statistics about once a minute; rerun this cell.",
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
        raise self._timed_out(
            "Replicas did not become healthy",
            f"After {timeout_seconds} seconds, the tablets of {table_name} did not all have "
            f"{expected_alive} alive and {expected_complete} up-to-date replicas.",
            placement,
            hint="Check the containers with `docker compose --file level3/module09-sharding-replication/compose.multinode.yml ps` and read the logs of the one that is not running.",
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
            columns = ["Name", "Host", "Role", "IsMaster", "Alive", "Version", "BackendId"]
            last = pd.DataFrame(rows)
            last = last[[column for column in columns if column in last.columns]]
            expected = f"{expected_alive} of {expected_total} alive"
            if expected_masters is not None:
                expected += f", {expected_masters} Master"
            error = f" The last attempt failed: {last_error}." if last_error else ""
            raise self._timed_out(
                "The cluster did not reach the expected state",
                f"After {timeout_seconds} seconds, {normalized} did not show {expected}.{error}",
                last,
                hint="Check the containers with `docker compose --file level3/module09-sharding-replication/compose.multinode.yml ps` and read the logs of the one that is not running.",
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
            last = pd.DataFrame(rows)
            last = last[[c for c in ("BackendId", "Host", "Alive", "AvailCapacity", "TotalCapacity")
                         if c in last.columns]]
            raise self._timed_out(
                "BE storage is not ready",
                f"After {timeout_seconds} seconds, not all {expected_backends} BEs reported usable storage.",
                last,
                hint="Check the containers with `docker compose --file level3/module09-sharding-replication/compose.multinode.yml ps` and read the logs of the one that is not running.",
            )
        frame = pd.DataFrame(rows)[
            ["BackendId", "Host", "Alive", "AvailCapacity", "TotalCapacity"]
        ]
        if show:
            show_frame(title, frame)
            self.show_statements("SHOW BACKENDS")
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
        self.show_statements(*(
            statement for name in table_names
            for statement in (f"SHOW PARTITIONS FROM {name}", f"SHOW TABLETS FROM {name}")
        ))
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
        with connection.cursor() as cursor:
            cursor.execute(normalized)
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

    _normalize_statement = staticmethod(normalize_statement)

    # Session settings for reading a query's scan work from its Query Profile:
    # collect the Profile and stop the caches from answering without a scan.
    PROFILE_SETTINGS = {
        "enable_profile": "true",
        "profile_level": "2",
        "enable_sql_cache": "false",
        "enable_query_cache": "false",
        "enable_condition_cache": "false",
    }

    _profile_metric = staticmethod(profile_metric)

    _profile_row_sum = staticmethod(profile_row_sum)

    def show_statements(self, *statements: str, title: str = "SQL behind this result") -> None:
        """Show, folded, the statements a step ran, ready to paste into a MySQL client."""
        text = "\n\n".join(
            statement.strip().rstrip(";") + ";" for statement in statements if statement.strip()
        )
        show_log(title, text)

    def profile_command(self, profile_id: str) -> str:
        """Return the curl command that prints one query's Profile text."""
        return f'curl -u root: "{self.fe_http_url}/api/profile/text?query_id={profile_id}"'

    def _profile_text(self, profile_id: str, *, timeout_seconds: int = 20) -> str:
        """Return the Profile text of one finished query from the FE HTTP API.

        The BEs report their part after the query ends, so the text is read
        again until it contains a scan operator.
        """
        deadline = time.monotonic() + timeout_seconds
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                profile = fetch_profile_text(self.fe_http_url, profile_id, timeout_seconds=0)
            except (OSError, urllib.error.URLError, http.client.HTTPException) as exc:
                last_error = exc
            else:
                if "OLAP_SCAN_OPERATOR" in profile:
                    return profile
                if "Is Cached: Yes" in profile:
                    raise RuntimeError(
                        "The query used SQL Cache, so Doris did not run a new BE scan operator."
                    )
            time.sleep(0.4)
        raise RuntimeError(
            f"The Query Profile {profile_id} was not ready: {last_error or 'no scan operator yet'}"
        )

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
        with self.session_settings(self.PROFILE_SETTINGS):
            with connection.cursor() as cursor:
                cursor.execute(query)
                result = cursor.fetchone()
            profile_id = last_query_id(connection)
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
        self._show_profile_statements(query, profile_id)
        return excerpt

    def _show_profile_statements(self, query: str, profile_id: str) -> None:
        """Show the SQL and the command used to capture one query's Profile."""
        settings = [f"SET {name} = {value}" for name, value in self.PROFILE_SETTINGS.items()]
        self.show_statements(
            *settings, query, "SELECT last_query_id()",
            title="SQL run to capture this Profile; the settings then return to their earlier values",
        )
        show_log(f"Command that prints this Profile · {profile_id}", self.profile_command(profile_id))

    def compare_profiles(
        self,
        cases: Sequence[tuple[str, str]],
        *,
        title: str = "Query Profile scan evidence",
    ) -> pd.DataFrame:
        """Run comparable queries and summarize only their OLAP scan evidence."""
        connection = self._require_connection()
        rows: list[dict[str, object]] = []
        commands: list[str] = []
        executed: list[str] = []
        with self.session_settings(self.PROFILE_SETTINGS):
            for label, statement in cases:
                query = statement.strip().rstrip(";")
                with connection.cursor() as cursor:
                    cursor.execute(query)
                    result = cursor.fetchone() or {}
                profile_id = last_query_id(connection)
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
                executed += [f"-- {label}\n{textwrap.dedent(statement).strip()}", "SELECT last_query_id()"]
                commands.append(f"# {label}\n{self.profile_command(profile_id)}")
        frame = pd.DataFrame(rows)
        show_frame(title, frame)
        self.show_statements(
            *(f"SET {name} = {value}" for name, value in self.PROFILE_SETTINGS.items()),
            *executed,
            title="SQL run by this comparison; the settings then return to their earlier values",
        )
        show_log("Commands that print each Query Profile", "\n\n".join(commands))
        return frame

    def shell(self, script: str, *, title: str) -> subprocess.CompletedProcess[str]:
        """Run learner-visible Bash from the course root with live progress.

        A failing script already shows its log, so the stop is one line.
        """
        try:
            return run_shell(script, title=title, cwd=self.lab_dir)
        except RuntimeError as exc:
            raise EnvironmentNotReady(f"{title} failed; the log above shows why.") from exc

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
              feedback.textContent = selected === 'SUM(revenue)' && card.dataset.answer === 'LOWER(event_type)'
                ? 'SUM combines multiple input rows into one value per group. This task must keep every event row and return one normalized value for each row.'
                : 'Not this expression. Compare the input, output row shape, and whether the operation depends on an existing input row or an external service.';
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
        try:
            with connection.cursor() as cursor:
                cursor.execute(statement.strip())
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
            widgets.HTML(
                "<b>Fixed input range:</b> 2020-03-01 00:00:00 (included) to "
                "2020-03-09 00:00:00 (excluded). Changing Grain keeps this input range. "
                "Week labels are Monday week starts, which can precede March 1; "
                "Month summarizes only the part of March inside the range."
            ),
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
        sample = DorisLab.LAB3_SAMPLE
        if kind in {"stream_csv", "stream_malformed_csv"}:
            expected_rows = {
                "stream_csv": sample["rows"],
                "stream_malformed_csv": sample["malformed_rows"],
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
                DorisLab._check_sample(
                    path.name,
                    [row[1] for row in fields],
                    [row[0] for row in fields],
                    [Decimal(row[6]) for row in fields],
                )
            else:
                if fields[0][1] != "1" or fields[-1][1] != "10":
                    raise ValueError("The malformed fixture is not the authored ten-row sample.")
                if sum(row[6] == "not-a-number" for row in fields) != sample["malformed_filtered_rows"]:
                    raise ValueError("The malformed fixture must contain one invalid revenue value.")
            return len(fields)
        if kind == "routine_json":
            if len(lines) != sample["rows"]:
                raise ValueError(f"{path.name} must contain {sample['rows']} JSON messages.")
            records = [json.loads(line) for line in lines]
            if records[0]["meta"]["event_id"] != 1 or records[-1]["meta"]["event_id"] != 10027072:
                raise ValueError("The Routine Load fixture is not the authored Lab 1/2 sample.")
            if any(not isinstance(record["event"]["revenue"], (int, float)) for record in records):
                raise ValueError("The Routine Load fixture must contain only valid numeric revenue values.")
            DorisLab._check_sample(
                path.name,
                [record["meta"]["event_id"] for record in records],
                [record["meta"]["occurred_at"].replace("T", " ") for record in records],
                [Decimal(str(record["event"]["revenue"])) for record in records],
            )
            return len(records)
        raise ValueError(f"Unknown fixture kind: {kind!r}")

    @staticmethod
    def _check_sample(name: str, event_ids: list, event_times: list[str], revenues: list[Decimal]) -> None:
        """Require a Lab 3 file to hold exactly the records in datasets/expected_results.yaml."""
        sample = DorisLab.LAB3_SAMPLE
        observed = {
            "distinct events": (len(set(event_ids)), sample["distinct_events"]),
            "earliest event time": (min(event_times), sample["min_event_time"]),
            "latest event time": (max(event_times), sample["max_event_time"]),
            "total revenue": (sum(revenues, Decimal("0")), Decimal(sample["total_revenue"])),
        }
        wrong = [
            f"{label} {actual}, expected {expected}"
            for label, (actual, expected) in observed.items() if actual != expected
        ]
        if wrong:
            raise ValueError(f"{name} is not the Lab 3 sample: " + "; ".join(wrong) + ".")

    def verify_lab3_sample(self, statement: str, *, title: str) -> pd.DataFrame:
        """Run the visible validation query and compare it with the Lab 3 sample."""
        result = self.sql(statement, title=title)
        row = result.iloc[0]
        sample = self.LAB3_SAMPLE
        observed = {
            "loaded_rows": (int(row["loaded_rows"]), sample["rows"]),
            "distinct_events": (int(row["distinct_events"]), sample["distinct_events"]),
            "min_event_time": (str(row["min_event_time"]), sample["min_event_time"]),
            "max_event_time": (str(row["max_event_time"]), sample["max_event_time"]),
            "total_revenue": (Decimal(str(row["total_revenue"])), Decimal(sample["total_revenue"])),
        }
        wrong = [
            f"{column} is {actual}, expected {expected}"
            for column, (actual, expected) in observed.items() if actual != expected
        ]
        if wrong:
            raise AssertionError(
                "The loaded rows differ from the sample in datasets/expected_results.yaml: "
                + "; ".join(wrong) + "."
            )
        card(
            f"{sample['rows']:,} rows from {sample['min_event_time']} to {sample['max_event_time']}, "
            f"total revenue {Decimal(sample['total_revenue']):,}",
            "ok",
            "The loaded rows match the 1,024-record sample",
        )
        return result

    def fetch_fixtures(
        self,
        fixtures: Sequence[tuple[str, str, str, str]],
    ) -> pd.DataFrame:
        """Download validated course fixtures using a same-directory atomic rename.

        The files are public objects in the course bucket, so a plain HTTPS
        GET is enough; no credentials are involved.
        """
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
                    with urllib.request.urlopen(remote_url, timeout=60) as response:
                        temporary.write_bytes(response.read())
                    row_count = self._validate_fixture(temporary, kind)
                    os.replace(temporary, destination)
                except OSError as exc:
                    temporary.unlink(missing_ok=True)
                    host = urllib.parse.urlsplit(remote_url).hostname
                    card(
                        f"Could not download {remote_url}: {getattr(exc, 'reason', exc)}. Check that this "
                        f"computer can reach {host} over HTTPS (a proxy, VPN, or firewall can block it), "
                        "then rerun this cell.",
                        "fail",
                        f"{label} was not downloaded",
                    )
                    raise EnvironmentNotReady(f"{label} was not downloaded.") from exc
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
        if kind in {"stream_csv", "stream_malformed_csv"}:
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
                f"127.0.0.1:{parsed.port or env.BE_HTTP_PORT}",
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

    def _sync_mv_jobs_sql(self, table, view, database="doris_course"):
        table = self._safe_table_name(table)
        view = self._safe_table_name(view)
        database = self._safe_table_name(database)
        return (f"SHOW ALTER TABLE MATERIALIZED VIEW FROM `{database}`\n"
                f"WHERE TableName = '{table}' AND RollupIndexName = '{view}'")

    def _async_mv_tasks_sql(self, view, database="doris_course"):
        view = self._safe_table_name(view)
        database = self._safe_table_name(database)
        return (f'SELECT * FROM tasks("type"="mv")\n'
                f"WHERE MvDatabaseName = '{database}' AND MvName = '{view}'")

    def sync_mv_jobs(self, table, view, *, database="doris_course"):
        """Return build jobs for one synchronous materialized view."""
        return self._metadata_rows(self._sync_mv_jobs_sql(table, view, database))

    def async_mv_tasks(self, view, *, database="doris_course"):
        """Return refresh tasks for one asynchronous materialized view."""
        return self._metadata_rows(self._async_mv_tasks_sql(view, database))

    def capture_query(self, statement, *, settings=None):
        """Capture the result, plan and fresh runtime Profile on this lab session."""
        from .profiles import capture_query
        return capture_query(self, statement, settings=settings)

    @staticmethod
    def show_lookup_comparison(evidence):
        """Show captured lookup counters, with one row per DetailProfile scan task."""
        from .profiles import lookup_scan_summary
        frame = lookup_scan_summary(evidence)
        show_frame("Lookup comparison (one row per DetailProfile scan task)", frame)
        return frame

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
        last_state = pd.DataFrame(last) if last else None
        raise DorisLab._timed_out(
            "The background job did not finish",
            f"The background job did not finish within {timeout}s; its last state was "
            f"{', '.join(str(row.get(state_key)) for row in last) or 'not listed yet'}.",
            last_state,
            hint="Rerun this cell to wait again.",
        )

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
        self.show_statements(
            self._sync_mv_jobs_sql(table, view, database),
            title="SQL that reads the build job (repeated until the job finishes)",
        )
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
        self.show_statements(
            self._async_mv_tasks_sql(view, database),
            title="SQL that reads the refresh task (repeated until the task finishes)",
        )
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
            "docker", "exec", env.KAFKA_CONTAINER, "/opt/kafka/bin/kafka-get-offsets.sh",
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
            "docker", "exec", env.KAFKA_CONTAINER, "/opt/kafka/bin/kafka-get-offsets.sh",
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
                "docker", "exec", "-i", env.KAFKA_CONTAINER,
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

    _workflow_html = staticmethod(workflow_html)

    def ensure_docker_ready(self, *, timeout_seconds: int = 180) -> None:
        """Ensure the Docker daemon is reachable, starting Docker Desktop on macOS."""
        labkit_docker.ensure_docker_ready(timeout_seconds=timeout_seconds)

    def start_container(
        self,
        container: str = env.DORIS_CONTAINER,
        *,
        wait_for_healthy: bool = True,
        timeout_seconds: int = 300,
    ) -> dict:
        """Idempotently make an existing course container available again.

        Without a name, this is the course's single-node Doris sandbox.
        """
        creator = (
            "Create it with Lab 1, Section 2 (Prepare the environment)."
            if container == env.DORIS_CONTAINER
            else "Create it with that module's environment preparation cell."
        )
        try:
            state = labkit_docker.start_container(
                container,
                wait_for_healthy=wait_for_healthy,
                timeout_seconds=timeout_seconds,
                missing_hint=creator,
            )
        except (RuntimeError, TimeoutError) as exc:
            if "does not exist" in str(exc):
                card(str(exc), "fail", "The container is missing")
                raise EnvironmentNotReady(f"Container {container} does not exist.") from exc
            card(
                f"{exc} Check Docker Desktop (or Docker Engine on Linux) and `docker logs --tail 100 "
                f"{container}`, then rerun this cell.",
                "fail",
                f"{container} did not start",
            )
            raise EnvironmentNotReady(f"{container} did not start.") from exc
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
        container: str = env.DORIS_CONTAINER,
        host: str = "127.0.0.1",
        port: int = env.QUERY_PORT,
        http_host: str | None = None,
        http_port: int = env.HTTP_PORT,
    ):
        """Wait for a healthy container, then connect to its FE.

        Without arguments, this is the course's single-node Doris sandbox.
        """
        self._connection_host = host
        self._connection_port = port
        state = container_inspect(container)
        status = (state or {}).get("State", {}).get("Status")
        if status != "running":
            problem = "does not exist" if state is None else f"is {status}"
            card(f"Container {container} {problem}. {self._start_hint()}", "fail",
                 "The Doris container is not running")
            raise EnvironmentNotReady(f"Container {container} {problem}.")
        try:
            wait_for_health(container, timeout_seconds=300, report=False)
        except (RuntimeError, TimeoutError) as exc:
            card(f"{exc}. Read `docker logs --tail 200 {container}`, then rerun this cell.",
                 "fail", "Doris did not become healthy")
            raise EnvironmentNotReady(f"{container} did not become healthy.") from exc
        if self.connection is not None:
            try:
                self.connection.close()
            except Exception:
                pass
        self.DORIS_CONTAINER = container
        self._profile_http_host = http_host or host
        self._profile_http_port = http_port
        self.connection = None
        try:
            self.connection = connect_doris(host=host, port=port)
        except (OSError, TimeoutError, pymysql.MySQLError) as exc:
            card(f"{container} is healthy, but nothing answers on {host}:{port}. {self._start_hint()}",
                 "fail", "Doris is not reachable")
            raise EnvironmentNotReady(f"Doris is not reachable on {host}:{port}.") from exc
        return self.connection

    def check_prerequisites(self, lab_number: int) -> pd.DataFrame:
        """Check that the tables this Lab reads from earlier Labs are complete."""
        rows = []
        statements = []
        for table, (expected, made_by) in PREREQUISITES[lab_number].items():
            exists = bool(self._metadata_rows(f"SHOW TABLES LIKE '{table}'"))
            count = None
            if exists:
                statement = f"SELECT COUNT(*) AS row_count FROM {table}"
                statements.append(statement)
                count = int(self._metadata_rows(statement)[0]["row_count"])
            rows.append({
                "table": table,
                "rows": "missing" if count is None else f"{count:,}",
                "expected rows": f"{expected:,}",
                "built by": made_by,
                "status": "missing" if count is None else ("ready" if count == expected else "incomplete"),
            })
        frame = pd.DataFrame(rows)
        missing = frame.loc[frame["status"] != "ready"]
        if not missing.empty:
            show_frame(f"Tables Lab {lab_number} reads from earlier Labs", frame)
            labs = list(dict.fromkeys(missing["built by"]))
            card(
                f"Complete {' and then '.join(labs)} in this sandbox, then rerun this cell. "
                "Nothing has been changed.",
                "fail",
                f"Lab {lab_number} needs data from an earlier Lab",
            )
            raise EnvironmentNotReady(
                f"{', '.join(missing['table'])} {'is' if len(missing) == 1 else 'are'} missing or incomplete."
            )
        card(
            ", ".join(f"{row['table']} ({row['rows']} rows)" for row in rows),
            "ok",
            f"The tables Lab {lab_number} reads are ready",
        )
        self.show_statements(*statements)
        return frame

    def check_module9_stopped(self) -> None:
        """Refuse to start the single-node sandbox while the Module 9 cluster runs."""
        running = run(
            ["docker", "ps", "--filter", f"label=com.docker.compose.project={env.M09_PROJECT}",
             "--format", "{{.Names}}"],
            check=False,
        )
        names = running.stdout.split()
        if names:
            card(
                f"{len(names)} container(s) of the Module 9 cluster are still running. Together with "
                f"the single-node sandbox they need more memory than the course minimum. Stop them "
                f"with `docker compose --file level3/module09-sharding-replication/compose.multinode.yml "
                f"stop` (or the Stop cell at the end of Lab 9), then rerun this cell.",
                "fail",
                "Stop the Module 9 cluster first",
            )
            raise EnvironmentNotReady("The Module 9 cluster is still running.")

    @property
    def fe_http_url(self) -> str:
        """The FE HTTP address on this host, for Stream Load and other REST requests."""
        return f"http://{self._profile_http_host}:{self._profile_http_port}"

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
        port_rows = [
            {
                "host_port": port,
                "purpose": purpose,
                "status": "in use" if labkit_docker.port_in_use(port) else "available",
            }
            for port, purpose in (
                (env.QUERY_PORT, "Doris"),
                (env.HTTP_PORT, "Doris"),
                (env.BE_HTTP_PORT, "Doris"),
                (env.METABASE_PORT, "optional Metabase"),
            )
        ]
        show_frame("Host port check", pd.DataFrame(port_rows))

        existing = container_inspect(self.DORIS_CONTAINER)
        busy_ports = [
            row["host_port"] for row in port_rows
            if row["purpose"] == "Doris" and row["status"] == "in use"
        ]
        if existing is None and busy_ports:
            self._failure(
                "Required port is unavailable",
                f"Another process is using: {', '.join(map(str, busy_ports))}. Stop it, or set "
                "DORIS_RTA_QUERY_PORT, DORIS_RTA_HTTP_PORT, and DORIS_RTA_BE_HTTP_PORT to free ports "
                "before starting Jupyter.",
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
                "-e", f"BE_HTTP_PORT={env.BE_HTTP_PORT}",
                "-e", f"BE_CONFIG_EXTRA=webserver_port = {env.BE_HTTP_PORT}",
                "-p", f"127.0.0.1:{env.QUERY_PORT}:9030",
                "-p", f"127.0.0.1:{env.HTTP_PORT}:8030",
                "-p", f"127.0.0.1:{env.BE_HTTP_PORT}:{env.BE_HTTP_PORT}",
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
                "9030/tcp": ("127.0.0.1", str(env.QUERY_PORT)),
                "8030/tcp": ("127.0.0.1", str(env.HTTP_PORT)),
                f"{env.BE_HTTP_PORT}/tcp": ("127.0.0.1", str(env.BE_HTTP_PORT)),
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
                    f"A container named {self.DORIS_CONTAINER} exists but does not match this Lab's image, "
                    "ports, volumes, or network. It was left unchanged.",
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
        self.connection = connect_doris(port=env.QUERY_PORT)
        self.sql(
            "SELECT VERSION() AS doris_version, CURRENT_USER() AS current_user",
            title="Connection",
        )
        self.sql("SHOW FRONTENDS", title="Frontend status")
        self.sql("SHOW BACKENDS", title="Backend status")
        card("Environment ready: Doris is healthy and both FE and BE are available.", "ok")
        return self.connection

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
            self.show_statements(f"SHOW REPLICA DISTRIBUTION FROM {table_name}", "SHOW BACKENDS")
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
                    self.show_statements(f"SHOW REPLICA DISTRIBUTION FROM {table_name}", "SHOW BACKENDS")
                return frame
            time.sleep(1)
        raise self._timed_out(
            "Replicas were not rebalanced in time",
            f"After {timeout_seconds} seconds, the {expected_total_replicas} replicas of {table_name} "
            f"were not spread over {expected_backends} BEs.",
            frame,
            hint="Doris moves replicas in the background; rerun this cell to wait again. " + "Check the containers with `docker compose --file level3/module09-sharding-replication/compose.multinode.yml ps` and read the logs of the one that is not running.",
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
                    self.show_statements('SHOW PROC "/colocation_group"')
                    return frame
            time.sleep(1)
        raise self._timed_out(
            "The Colocation Group is not stable yet",
            f"After {timeout_seconds} seconds, Colocation Group {group_name} was not stable.",
            pd.DataFrame([selected]) if selected else None,
            hint="Doris is still moving replicas into the group; rerun this cell to wait again.",
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
        error = f" The last read failed: {last_error}." if last_error else ""
        raise self._timed_out(
            "HAProxy did not report the expected FE state",
            f"After {timeout_seconds} seconds, HAProxy did not mark {server_name} {expected}.{error}",
            frame,
            hint="Check the containers with `docker compose --file level3/module09-sharding-replication/compose.multinode.yml ps` and read the logs of the one that is not running.",
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
        with connection.cursor() as cursor:
            cursor.execute(normalized)
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
        raise self._timed_out(
            "Storage reports are late",
            f"After {timeout_seconds} seconds, SHOW DATA did not yet report all rows and a nonzero "
            "size for every table.",
            pd.DataFrame([{"table": name, "RowCount": row.get("RowCount"), "Size": row.get("Size")}
                          for name, row in last.items()]),
            hint="The BE reports sizes about once a minute; rerun this cell.",
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
        self.show_statements(
            "SHOW FRONTEND CONFIG LIKE 'default_compression_type'",
            *(statement for name in table_names for statement in (
                f"SHOW CREATE TABLE {name}", f"SHOW DATA FROM {name}",
                f"SHOW PARTITIONS FROM {name}", f"SHOW TABLETS FROM {name}",
            )),
        )
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
        raise self._timed_out(
            "Partitions were not created in time",
            f"After {timeout_seconds} seconds, {table_name} had {len(rows)} partitions instead of "
            f"{expected_count}: {', '.join(names) or 'none'}.",
            hint="Read the table's row in SHOW DYNAMIC PARTITION TABLES for the scheduler's message.",
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
                raise WaitTimedOut(
                    f"{partition_name} is still in {table_name} after {timeout_seconds} seconds; "
                    "rerun this cell to wait again."
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
        clock = self._metadata_rows("SELECT NOW() AS server_now, @@time_zone AS time_zone")
        server_now = pd.Timestamp(clock[0]["server_now"])
        zone = clock[0]["time_zone"]
        if server_now < expiry_at:
            remaining = expiry_at - server_now
            minutes = max(1, int(remaining.total_seconds() // 60) + 1)
            card(f"Return at or after {expiry_at:%Y-%m-%d %H:%M:%S} "
                 f"({zone}); about {minutes} minute(s) remain until the "
                 "whole hour becomes ineligible. Keep the container running and "
                 "rerun this cell then; do not rerun Section 2.",
                 "info", "The hourly retention boundary has not arrived")
            raise ReturnLater(
                f"rerun this cell at or after {expiry_at:%Y-%m-%d %H:%M} ({zone})."
            )

        partition = self._partition_containing(table_name, event_hour, event_id)
        self.wait_for_partition_removal(
            table_name, partition, timeout_seconds=timeout_seconds
        )

    def _partition_containing(self, table_name: str, moment: pd.Timestamp, event_id: int) -> str:
        """Return the one Range Partition whose half-open bounds hold ``moment``."""
        partitions = self._metadata_rows(
            f"SHOW PARTITIONS FROM `{table_name}` ORDER BY PartitionName"
        )
        matches = []
        for partition in partitions:
            bounds = re.findall(
                r"\b\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\b",
                str(partition.get("Range", "")),
            )
            if len(bounds) >= 2 and pd.Timestamp(bounds[0]) <= moment < pd.Timestamp(bounds[1]):
                matches.append(str(partition["PartitionName"]))
        if len(matches) != 1:
            raise RuntimeError(
                f"Expected one Partition containing event {event_id} at {moment}; "
                f"found {matches!r}. Inspect SHOW PARTITIONS before continuing."
            )
        return matches[0]

    def partition_holding_event(self, table_name: str, *, event_id: int) -> str | None:
        """Show and return the Partition that holds one event, or None when the event is gone."""
        table_name = self._safe_table_name(table_name)
        if not isinstance(event_id, int) or event_id < 0:
            raise ValueError("event_id must be a nonnegative integer.")
        lookup = f"SELECT event_time FROM {table_name} WHERE event_id = {event_id}"
        marker = self._metadata_rows(lookup)
        if not marker:
            card(f"Event {event_id} is no longer in {table_name}.", "skip", "The event is already gone")
            return None
        event_time = pd.Timestamp(marker[0]["event_time"])
        partition = self._partition_containing(table_name, event_time, event_id)
        card(f"Event {event_id} at {event_time} is in Partition {partition}.", "info",
             "The Partition to watch")
        self.show_statements(lookup, f"SHOW PARTITIONS FROM {table_name} ORDER BY PartitionName")
        return partition

    @staticmethod
    def _session_time(value: str, system_zone: str, session_zone: str) -> str:
        """Express a time that the FE writes in its system time zone in the session's time zone.

        SHOW DYNAMIC PARTITION TABLES reports scheduler times in the FE's own
        time zone, while partition bounds follow the table's time zone.
        """
        try:
            moment = pd.Timestamp(value).tz_localize(system_zone).tz_convert(session_zone)
        except (ValueError, TypeError, KeyError):
            return f"{value} ({system_zone}, the FE's system time zone)"
        if moment.utcoffset() == pd.Timestamp(value).tz_localize(system_zone).utcoffset():
            return f"{moment:%Y-%m-%d %H:%M:%S} ({session_zone})"
        return (f"{moment:%Y-%m-%d %H:%M:%S} {session_zone} "
                f"(the FE reports {value} in its system time zone, {system_zone})")

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
        zones = self._metadata_rows(
            "SELECT @@system_time_zone AS system_time_zone, @@time_zone AS time_zone"
        )[0]
        card(
            f"State: {state} · Last scheduler run: "
            f"{self._session_time(last_run, zones['system_time_zone'], zones['time_zone'])}",
            "ok" if state.upper() == "NORMAL" else "fail",
            title,
        )
        self.show_statements(
            "SHOW DYNAMIC PARTITION TABLES",
            "SELECT @@system_time_zone AS system_time_zone, @@time_zone AS time_zone",
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
        self.show_statements(
            f"SHOW PARTITIONS FROM {table_name} ORDER BY PartitionName",
            *(f"SELECT COUNT(*) AS row_count FROM {table_name} PARTITION ({row['partition']})" for row in rows),
        )
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
        self.show_statements(f"SHOW CATALOG RECYCLE BIN WHERE NAME = '{partition_name}'")
        return frame
