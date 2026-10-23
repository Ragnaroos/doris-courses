"""Explicit connection and assertion helpers; never start or stop a cluster."""

import json
import os
import re
from contextlib import contextmanager
from contextvars import ContextVar
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pymysql
import requests

from doris_labkit.profiles import fetch_profile_text, last_query_id, profile_metric, profile_row_sum

from .environment import connection_settings
from .ui import card, in_notebook, install_styles, report_sql_error, result_frame, show_frame, show_log, show_sql

COURSE_ROOT = Path(__file__).resolve().parents[1]
# The row counters of a scan in the Query Profile: ScanRows = RowsRead + RowsVectorPredFiltered.
SCAN_COUNTERS = ("ScanRows", "RowsRead", "RowsKeyRangeFiltered", "RowsStatsFiltered", "RowsVectorPredFiltered")
# The sections in which an EXPLAIN plan lists the materialized views that Doris tried.
VIEW_REWRITE_RESULTS = {
    "MaterializedViewRewriteSuccessAndChose:": "chosen",
    "MaterializedViewRewriteSuccessButNotChose:": "usable, not chosen",
    "MaterializedViewRewriteFail:": "not usable",
}


def plan_scans(lines):
    """The table scans and the materialized views that a Doris EXPLAIN plan lists.

    A scan reads a table, or one of its materialized views, which TABLE: names in
    parentheses; its partitions= and tablets= lines say how many it reads of how
    many there are. Doris lists each materialized view that it considered under
    one of VIEW_REWRITE_RESULTS, with the reason when it could not use it.
    """
    scans, views, result = [], [], None
    for line in lines:
        text = line.strip()
        if "VOlapScanNode" in text:
            scans.append({"table": "", "reads": "", "partitions": "", "tablets": ""})
        elif scans and result is None and text.startswith("TABLE:"):
            name = text[len("TABLE:"):].split(",")[0].strip()
            scans[-1]["table"], _, index = name.partition("(")
            scans[-1]["reads"] = index.rstrip(")")
        elif scans and result is None and text.startswith("partitions="):
            scans[-1]["partitions"] = text[len("partitions="):]
        elif scans and result is None and text.startswith("tablets="):
            scans[-1]["tablets"] = text[len("tablets="):].split(",")[0]
        elif text in VIEW_REWRITE_RESULTS:
            result = VIEW_REWRITE_RESULTS[text]
        elif text.startswith("FailInfo:") and views:
            views[-1]["reason"] = text[len("FailInfo:"):].strip()
        elif result and text.startswith(("CBO.", "RBO.")):
            views.append({"materialized_view": text.split()[0].rsplit(".", 1)[-1], "result": result, "reason": ""})
        elif text.startswith("========== STATISTICS"):  # the plan and its materializations end here
            break
    return scans, views


def plan_joins(lines):
    """The joins of a Doris EXPLAIN plan: the join type, how the rows meet, and the condition.

    A join node prints "join op: INNER JOIN(BROADCAST)[]": the logical join, then in
    parentheses the distribution: BROADCAST (one side is sent to every instance),
    PARTITIONED (both sides are shuffled by the key), BUCKET_SHUFFLE, or COLOCATE.
    """
    joins = []
    for line in lines:
        text = line.strip().lstrip("|").strip()
        if text.startswith("join op:"):
            operation = text[len("join op:"):].strip()
            kind, _, rest = operation.partition("(")
            joins.append({"join": kind.strip(), "distribution": rest.split(")", 1)[0], "condition": ""})
        elif joins and not joins[-1]["condition"] and text.startswith("equal join conjunct:"):
            joins[-1]["condition"] = text[len("equal join conjunct:"):].strip()
    return joins


def identifier(value):
    if re.fullmatch(r"[a-z][a-z0-9_]*", value) is None:
        raise ValueError("Expected a lowercase SQL identifier")
    return value


def fixture(name):
    """Read only committed fixtures by basename."""
    if Path(name).name != name:
        raise ValueError("Fixture must be a basename")
    return json.loads((COURSE_ROOT / "datasets" / name).read_text())


def normalized(value):
    if isinstance(value, Decimal):
        return format(value, ".2f")
    if isinstance(value, (tuple, list)):
        return [normalized(item) for item in value]
    return value


_expected_failure = ContextVar("course_expected_failure", default=False)


class CourseCheckError(AssertionError):
    """A result mismatch, distinct from unrelated execution errors."""


@contextmanager
def expected_failure(title, message):
    """Show success only when a course result check detects an intended mismatch."""
    token = _expected_failure.set(True)
    detected = False
    try:
        yield
    except CourseCheckError:
        detected = True
    finally:
        _expected_failure.reset(token)
    if not detected:
        expect("Expected error not detected", "Expected error detected")
    if in_notebook():
        card(message, "ok", title)
    else:
        print(title + ": " + message)


def expect(actual, expected, *, title=None):
    """Raise on mismatch even when Python runs with optimization enabled."""
    if normalized(actual) != normalized(expected):
        if in_notebook() and not _expected_failure.get():
            card("The actual result differs from the expected result. See the exception details below.", "fail", "Validation failed")
        raise CourseCheckError(f"Expected {expected!r}, got {actual!r}")
    if in_notebook():
        if title is not None:
            card("The result matches the expectation.", "ok", title)
    else:
        print("PASS", normalized(expected))


class WarehouseLab:
    def __init__(self, *, allow_writes=False):
        if not allow_writes and os.environ.get("DW_ALLOW_WRITES") != "yes":
            raise RuntimeError("Read the reset scope, then set DW_ALLOW_WRITES=yes")
        self.database = identifier(os.environ.get("DW_DATABASE", "dw_course_l1_demo"))
        if not self.database.startswith("dw_course_l1_"):
            raise ValueError("Use a dedicated database with prefix dw_course_l1_")
        self.user = os.environ.get("DW_USER", "root")
        self.password = os.environ.get("DW_PASSWORD", "")
        self.connection = pymysql.connect(
            host=os.environ.get("DW_HOST", "127.0.0.1"),
            port=int(os.environ.get("DW_PORT", "9030")),
            user=self.user,
            password=self.password,
            charset="utf8mb4",
            autocommit=True,
            connect_timeout=5,
            read_timeout=120,
            write_timeout=120,
        )
        self.execute(f"CREATE DATABASE IF NOT EXISTS {self.database}")
        self._configure_session()
        if in_notebook():
            install_styles()
            card(self.database, "ok", "Connected to the lab database")

    def _configure_session(self):
        """Apply settings that are lost when the SQL connection is reopened."""
        self.execute(f"USE {self.database}")
        self.execute("SET time_zone = '+08:00'")
        self.execute("SET group_commit = 'off_mode'")

    def restore_session(self):
        """Reconnect after a Docker network change and restore the lab SQL session."""
        self.connection.ping(reconnect=True)
        self._configure_session()

    def query(self, sql, params=None):
        with self.connection.cursor() as cursor:
            cursor.execute(sql, params)
            return list(cursor.fetchall())

    def sql(self, statement, params=None, *, title="Query result", columns=None):
        """Display named columns like course 01; query() remains assertion-friendly.

        ``columns`` limits the shown and returned result to those columns, for
        statements such as SHOW TABLETS that return many.
        """
        with self.connection.cursor() as cursor:
            visible = statement
            if in_notebook():
                visible = cursor.mogrify(statement, params)
                show_sql(title, visible)
            try:
                cursor.execute(statement, params)
                rows = list(cursor.fetchall())
            except pymysql.MySQLError as error:
                if in_notebook():
                    report_sql_error(title, visible, error)
                raise
            names = [column[0] for column in cursor.description]
        frame = result_frame(rows, names)
        if columns:
            frame = frame.loc[:, [column for column in columns if column in frame.columns]]
        if in_notebook():
            show_frame(title, frame)
        else:
            print(frame.to_string(index=False))
        return frame

    def scan_profile(self, statement, *, title="Run the query, then read its Query Profile"):
        """Run a query and return how many rows its scans read and skipped, from its Query Profile.

        The session needs enable_profile = true. The Profile ID of a query is its
        query ID, which SELECT last_query_id() returns right after the query; the
        FE serves the Profile's text at /api/profile/text. The statements and the
        request are shown first.
        """
        rows = self.query(statement)
        query_id = last_query_id(self.connection)
        endpoint = (os.environ.get("DW_FE_HTTP_URL") or connection_settings()["DW_FE_HTTP_URL"]).rstrip("/")
        if in_notebook():
            show_sql(title, f"{statement};\nSELECT last_query_id();  -- {query_id}\n"
                            f"-- curl -u root: '{endpoint}/api/profile/text?query_id={query_id}'")
        # The BE reports its counters after the query ends; read until the scan's are there.
        text = fetch_profile_text(endpoint, query_id, user=self.user, password=self.password,
                                  ready=lambda profile: "ScanRows" in profile)
        return {"query": statement, "rows_returned": len(rows),
                **{counter: profile_row_sum(text, counter) for counter in SCAN_COUNTERS},
                "ScanBytes": profile_metric(text, "ScanBytes")}

    def explain_scan(self, statement, *, title="What the plan reads"):
        """Show what each table scan of a query reads, and the materialized views that Doris tried.

        Runs EXPLAIN, which plans the query without running it, shows one row per
        scan (the table, and in parentheses the table or materialized view that it
        reads), then the materialized views that Doris considered, with the result
        and the reason, and the whole plan in a collapsed box. Returns the scans
        and the views as two lists of dicts.
        """
        clean = statement.strip().rstrip(";")
        lines = [str(row[0]) for row in self.query("EXPLAIN " + clean)]
        scans, views = plan_scans(lines)
        if in_notebook():
            show_sql(title, "EXPLAIN " + clean)
            show_frame(f"{title} · {len(scans)} scan(s)",
                       pd.DataFrame(scans, columns=["table", "reads", "partitions", "tablets"]))
            if views:
                show_frame("The materialized views that Doris considered",
                           pd.DataFrame(views, columns=["materialized_view", "result", "reason"]))
            show_log("The whole plan", "\n".join(lines))
        else:
            print("\n".join(lines))
        return scans, views

    def explain_join(self, statement, *, title="How the plan joins the tables"):
        """Show the joins and the scans of a query's plan, and return the joins.

        Runs EXPLAIN, shows one row per join (the join type, the distribution, and
        the condition) and one per scan, then the whole plan in a collapsed box.
        """
        clean = statement.strip().rstrip(";")
        lines = [str(row[0]) for row in self.query("EXPLAIN " + clean)]
        joins = plan_joins(lines)
        scans, _ = plan_scans(lines)
        if in_notebook():
            show_sql(title, "EXPLAIN " + clean)
            show_frame(f"{title} · {len(joins)} join(s)", pd.DataFrame(joins, columns=["join", "distribution", "condition"]))
            show_frame(f"The scans · {len(scans)} scan(s)", pd.DataFrame(scans, columns=["table", "reads", "partitions", "tablets"]))
            show_log("The whole plan", "\n".join(lines))
        else:
            print("\n".join(lines))
        return joins

    def rowsets(self, table, *, title=None):
        """Show the rowsets of each tablet of ``table`` from the BE's compaction status, and return them.

        SHOW TABLETS gives each tablet's CompactionStatus URL with the BE's own
        address in the container, 127.0.0.1:8040; the same path is read from the
        host's BE HTTP port. ``rowsets`` are the ones that queries read; a rowset
        that compaction merged stays under ``stale_rowsets`` until the BE deletes it.
        """
        table = identifier(table)
        endpoint = (os.environ.get("DW_BE_HTTP_URL") or connection_settings()["DW_BE_HTTP_URL"]).rstrip("/")
        with self.connection.cursor() as cursor:
            cursor.execute(f"SHOW TABLETS FROM {table}")
            names = [column[0] for column in cursor.description]
            tablets = [dict(zip(names, row)) for row in cursor.fetchall()]
        rows = []
        for tablet in tablets:
            url = tablet["CompactionStatus"]
            url = endpoint + url[url.index("/api/"):]
            if in_notebook():
                show_sql(title or f"The rowsets of {table}", f"SHOW TABLETS FROM {table};  -- CompactionStatus column\n"
                                                             f"-- curl '{url}'")
            status = requests.get(url, timeout=10).json()
            for state, key in (("current", "rowsets"), ("stale: merged by compaction", "stale_rowsets")):
                for entry in status.get(key, []):
                    # "[2-11] 1 DATA NONOVERLAPPING <rowset id> 2.83 KB": versions, segments, ..., size.
                    versions, segments, _, overlap, _, *size = entry.split()
                    rows.append({"tablet": str(tablet["TabletId"]), "rowset": state, "versions": versions,
                                 "segments": int(segments), "overlap": overlap, "size": " ".join(size)})
        frame = pd.DataFrame(rows, columns=["tablet", "rowset", "versions", "segments", "overlap", "size"])
        if in_notebook():
            show_frame(title or f"The rowsets of {table}", frame)
        else:
            print(frame.to_string(index=False))
        return frame

    def execute(self, sql, params=None):
        with self.connection.cursor() as cursor:
            return cursor.execute(sql, params)

    def insert(self, table, columns, rows):
        table = identifier(table)
        columns = [identifier(col) for col in columns]
        statement = f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join(['%s'] * len(columns))})"
        with self.connection.cursor() as cursor:
            return cursor.executemany(statement, rows)

    def stream_load(self, table, path, label, columns=None, *, format="csv"):
        """Use an explicitly configured BE HTTP endpoint; do not forward secrets on redirects.

        A JSON file holds one array of objects whose keys name the columns.
        """
        table = identifier(table)
        if format not in ("csv", "parquet", "json"):
            raise ValueError("This lab supports CSV, Parquet, and JSON")
        headers = {
            "label": label, "format": format, "strict_mode": "true",
            "max_filter_ratio": "0", "group_commit": "off_mode",
        }
        if format == "csv":
            headers["column_separator"] = ","
        if format == "json":
            headers["strip_outer_array"] = "true"
        if columns is not None:
            headers["columns"] = columns
        endpoint = os.environ.get("DW_BE_HTTP_URL", "http://127.0.0.1:8040").rstrip("/")
        with Path(path).open("rb") as payload:
            response = requests.put(
                f"{endpoint}/api/{self.database}/{table}/_stream_load",
                auth=(self.user, self.password),
                headers=headers,
                data=payload,
                allow_redirects=False,
                timeout=120,
            )
        if 300 <= response.status_code < 400:
            raise RuntimeError("Set DW_BE_HTTP_URL to the trusted BE HTTP endpoint, not FE")
        response.raise_for_status()
        return response.json()

    def close(self):
        self.connection.close()
