from __future__ import annotations

import base64
import http.client
import json
import os
import re
import shlex
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd
import pymysql

from doris_labkit.db import connect_doris, report_sql_error, sql
from doris_labkit.docker import (
    container_inspect,
    docker_exists,
    docker_preflight,
    port_in_use,
    run,
    wait_for_health,
    wait_for_port,
)
from doris_labkit import docker as labkit_docker
from doris_labkit.profiles import fetch_profile_text, find_profile, last_query_id, profile_row_sum
from doris_labkit.results import result_frame, show_frame
from doris_labkit.shell import run_shell
from doris_labkit.ui import card, install_styles, show_log, show_sql

from . import environment as env


LAB_DIR = Path(__file__).resolve().parent.parent

# Host ports published by each part of the environment: (port, variable, purpose).
CORE_PORTS = (
    (env.QUERY_PORT, "DORIS_OBS_QUERY_PORT", "Doris FE query port (MySQL protocol)"),
    (env.HTTP_PORT, "DORIS_OBS_HTTP_PORT", "Doris FE HTTP"),
    (env.BE_HTTP_PORT, "DORIS_OBS_BE_HTTP_PORT", "Doris BE HTTP"),
    (env.GRAFANA_PORT, "DORIS_OBS_GRAFANA_PORT", "Grafana"),
    (env.OTLP_GRPC_PORT, "DORIS_OBS_OTLP_GRPC_PORT", "Collector OTLP gRPC"),
    (env.OTLP_HTTP_PORT, "DORIS_OBS_OTLP_HTTP_PORT", "Collector OTLP HTTP"),
    (env.MAILPIT_PORT, "DORIS_OBS_MAILPIT_PORT", "Mailpit inbox for Grafana's emails"),
)
DEMO_PORTS = ((env.DEMO_PORT, "DORIS_OBS_DEMO_PORT", "Demo storefront"),)
TRACE_COLLECTOR_PORTS = (
    (env.TRACES_OTLP_HTTP_PORT, "DORIS_OBS_TRACES_OTLP_HTTP_PORT", "Module 2 trace collector OTLP HTTP"),
)
LITEFUSE_PORTS = ((env.LITEFUSE_PORT, "DORIS_OBS_LITEFUSE_PORT", "Litefuse web UI and API"),)
LITEFUSE_COMPOSE_FILE = "environments/litefuse/compose.litefuse.yml"
LITEFUSE_HINT = (f"Read the log with docker logs {env.LITEFUSE_WEB_CONTAINER}, start Litefuse again with "
                 "lab.start_litefuse(), then rerun this cell.")
LOCAL_MODEL_PORTS = ((env.LOCAL_MODEL_PORT, "DORIS_OBS_LLM_PORT", "Local model server (llama.cpp)"),)
LOCAL_MODEL_COMPOSE_FILE = "environments/llm/compose.llm.yml"

# Download the model file into the volume of the model server, once, and check it.
# It runs in the server's image, which has curl and sha256sum; $0 is the URL.
DOWNLOAD_LOCAL_MODEL = r"""
set -e
model=/models/$MODEL_FILE
if [ -f "$model" ]; then
  echo "Already downloaded: $model"
else
  curl -fsSL -o "$model.part" "$0" &
  download=$!
  while kill -0 "$download" 2>/dev/null; do
    sleep 5
    echo "Downloaded $(( $(stat -c %s "$model.part" 2>/dev/null || echo 0) / 1000000 )) MB of $MODEL_MB MB"
  done
  if ! wait "$download"; then
    echo "The download failed. If $0 cannot be reached, set DORIS_OBS_LLM_MODEL_URL to the same file on a mirror before starting Jupyter."
    exit 1
  fi
  mv "$model.part" "$model"
fi
echo "$MODEL_SHA256  $model" | sha256sum -c -
"""

# The override files replace upstream lists with the !override merge tag (Compose 2.24.4).
MIN_COMPOSE_VERSION = (2, 24, 4)

# Fetch only the pinned commit, and nothing when the checkout is already there.
CHECKOUT_STACK = r"""
if [ ! -d "$STACK_DIR/.git" ]; then
  git -c init.defaultBranch=main init --quiet "$STACK_DIR"
  git -C "$STACK_DIR" remote add origin "$STACK_REPOSITORY"
fi
if [ "$(git -C "$STACK_DIR" rev-parse --verify --quiet HEAD)" = "$STACK_COMMIT" ]; then
  echo "Reusing the DOG stack at commit $STACK_COMMIT"
else
  git -C "$STACK_DIR" fetch --depth 1 origin "$STACK_COMMIT"
  git -C "$STACK_DIR" -c advice.detachedHead=false checkout --force "$STACK_COMMIT"
fi
"""


# Row counters of a table scan in a Query Profile. For filters that Doris checks
# against zone maps, inverted indexes, and the values it reads, such as the
# access-log search of Module 6, each row of the scanned partitions is counted in
# exactly one of them. A filter on a column's value, such as service_name = 'cart',
# drops rows in RowsVectorPredFiltered; a filter expression, such as LIKE or a
# MATCH_PHRASE that Doris evaluates without the index, in RowsExprPredFiltered
# (SegmentIterator::_execute_common_expr in 4.1.3). Filters on leading key columns
# and bloom filters have counters of their own.
SCAN_FILTER_COUNTERS = (
    ("RowsStatsFiltered", "Skipped unread: the zone map (minimum and maximum) of their segment or page rules out a match"),
    ("RowsInvertedIndexFiltered", "Skipped unread: the inverted index shows that they do not match"),
    ("RowsVectorPredFiltered", "Read, then dropped: their values did not match a filter on a column"),
    ("RowsExprPredFiltered", "Read, then dropped: a filter expression, such as LIKE or a MATCH without its index, did not match"),
    ("RowsRead", "Read, and passed every filter"),
)


def _scan_reported(profile: str) -> bool:
    """True once the BEs have reported the table scan of a profile."""
    return "DetailProfile" in profile and "OLAP_SCAN_OPERATOR" in profile.split("DetailProfile", 1)[1]


# The sections in which an EXPLAIN plan lists the materialized views that Doris tried.
VIEW_REWRITE_RESULTS = {
    "MaterializedViewRewriteSuccessAndChose:": "chosen",
    "MaterializedViewRewriteSuccessButNotChose:": "usable, not chosen",
    "MaterializedViewRewriteFail:": "not usable",
}


def _plan_scans(lines: Sequence[str]) -> tuple[list[dict], list[dict]]:
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
            scans.append({"table": "", "reads": "", "partitions": "", "tablets": "", "predicates": ""})
        elif scans and result is None and text.startswith("TABLE:"):
            name = text[len("TABLE:"):].split(",")[0].strip()
            scans[-1]["table"], _, index = name.partition("(")
            scans[-1]["reads"] = index.rstrip(")")
        elif scans and result is None and text.startswith("PREDICATES:"):
            scans[-1]["predicates"] = text[len("PREDICATES:"):].strip()
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


# Grafana's rules API lists every Grafana-managed alert rule with the instances of
# its last evaluation. Grafana's anonymous viewer, which the DOG stack enables, may
# read it, so the Labs do not depend on the admin password.
GRAFANA_RULES_PATH = "/api/prometheus/grafana/api/v1/rules"
# The demo's flag service, flagd, answers through the storefront's proxy, which
# routes /flagservice/ to it; the flag page, /feature, edits FLAGS_FILE.
FLAGD_RESOLVE_ALL_PATH = "/flagservice/flagd.evaluation.v1.Service/ResolveAll"
FLAGS_FILE = "doris-opentelemetry-demo/src/flagd/demo.flagd.json"  # in the upstream checkout
GRAFANA_HINT = "Check that the DOG stack is running with the cells in Module 1, then rerun this cell."
MAILPIT_HINT = ("Mailpit starts with the DOG stack: run lab.prepare_environment() in Module 1 again, "
                "then rerun this cell.")


def _utc(timestamp: str | None) -> str:
    """A UTC timestamp from Grafana, such as 2026-10-20T09:04:10Z, as 2026-10-20 09:04:10."""
    return (timestamp or "").replace("T", " ").replace("Z", "")[:19]


def _received(message: Mapping) -> datetime:
    """When Mailpit received a message, as a timezone-aware time."""
    return datetime.fromisoformat(message["Created"].replace("Z", "+00:00"))


def _alert_frame(rule: Mapping) -> pd.DataFrame:
    """One row per instance of a rule from Grafana's rules API.

    An instance is named by the labels that its query result adds, such as host;
    the labels that every instance of the rule has are left out.
    """
    common = set(rule.get("labels") or {}) | {"alertname", "grafana_folder"}
    rows = []
    for alert in rule.get("alerts") or []:
        labels = {key: value for key, value in (alert.get("labels") or {}).items() if key not in common}
        rows.append({
            "instance": ", ".join(f"{key}={value}" for key, value in sorted(labels.items())) or "(no labels)",
            "state": alert.get("state", ""),
            "since_utc": _utc(alert.get("activeAt")),
            "summary": (alert.get("annotations") or {}).get("summary", ""),
        })
    return pd.DataFrame(rows, columns=["instance", "state", "since_utc", "summary"])


class EnvironmentNotReady(RuntimeError):
    """A step stopped because the environment or its data is not ready.

    The card shown before raising says why and what to do.
    """

    def _render_traceback_(self) -> list[str]:
        return [f"Stopped: {self}"]


class ObservabilityLab:
    """Learner-facing facade for the DOG and Doris observability labs."""

    DORIS_IMAGE = env.DORIS_IMAGE
    DORIS_CONTAINER = env.DORIS_CONTAINER
    DOG_NETWORK = env.NETWORK
    STACK_REPOSITORY = env.STACK_REPOSITORY
    STACK_COMMIT = env.STACK_COMMIT
    RUNTIME_DIRECTORY = ".runtime"
    STACK_DIRECTORY = "ai-observe-stack"
    DORIS_LOG_DIRECTORY = "doris-logs"
    # Where the Module 2 log collector keeps its read position (file_storage).
    COLLECTOR_STATE_DIRECTORY = "collector-state"
    DEMO_PORT = env.DEMO_PORT

    def __init__(
        self,
        lab_dir: Path | None = None,
        *,
        ready_title: str = "Observability lab tools are ready",
        ready_message: str = "Run the environment cells in order, then use lab.sql(...) or lab.shell(...).",
    ) -> None:
        self.lab_dir = (lab_dir or LAB_DIR).resolve()
        self.connection = None
        self.stack_dir = self.lab_dir / self.RUNTIME_DIRECTORY / self.STACK_DIRECTORY
        self.doris_log_dir = self.lab_dir / self.RUNTIME_DIRECTORY / self.DORIS_LOG_DIRECTORY
        install_styles()
        card(ready_message, "ok", ready_title)

    def _failure(self, title: str, message: str, log: str = "") -> None:
        card(message, "fail", title)
        if log:
            show_log("Diagnostic details", log, opened=True)

    def _require_connection(self):
        if self.connection is None:
            try:
                self.connection = connect_doris(port=env.QUERY_PORT, connect_timeout=5)
                try:
                    with self.connection.cursor() as cursor:
                        cursor.execute("USE otel")
                except pymysql.MySQLError:
                    pass
            except (OSError, pymysql.MySQLError) as exc:
                raise RuntimeError(
                    f"No running Doris server is reachable on 127.0.0.1:{env.QUERY_PORT}. "
                    "Run the prepare-environment cell in Module 1, then retry."
                ) from exc
        return self.connection

    @property
    def fe_http_url(self) -> str:
        """The FE HTTP address on this host, for REST requests such as Query Profile text."""
        return f"http://127.0.0.1:{env.HTTP_PORT}"

    @property
    def grafana_url(self) -> str:
        return f"http://127.0.0.1:{env.GRAFANA_PORT}"

    @property
    def otlp_http_url(self) -> str:
        """The DOG Collector's OTLP/HTTP receiver on this host."""
        return f"http://127.0.0.1:{env.OTLP_HTTP_PORT}"

    @property
    def trace_collector_url(self) -> str:
        """The OTLP/HTTP receiver of the Module 2 trace collector on this host."""
        return f"http://127.0.0.1:{env.TRACES_OTLP_HTTP_PORT}"

    @property
    def demo_url(self) -> str:
        """The demo storefront on this host."""
        return f"http://127.0.0.1:{env.DEMO_PORT}"

    @property
    def mailpit_url(self) -> str:
        """The Mailpit inbox on this host, which receives every email that Grafana sends."""
        return f"http://127.0.0.1:{env.MAILPIT_PORT}"

    @property
    def litefuse_url(self) -> str:
        """The Litefuse web UI and API on this host."""
        return f"http://127.0.0.1:{env.LITEFUSE_PORT}"

    @property
    def local_model_url(self) -> str:
        """The local model server on this host; its OpenAI-compatible API is under /v1."""
        return f"http://127.0.0.1:{env.LOCAL_MODEL_PORT}"

    def sql(
        self,
        statement: str,
        *,
        title: str | None = None,
        final: bool = False,
        columns: Sequence[str] | None = None,
    ):
        """Run a statement and show its result; ``columns`` limits the result to those columns."""
        return sql(
            self._require_connection(),
            statement,
            title=title,
            show_statement=True,
            final=final,
            columns=columns,
        )

    def execute(self, statement: str, *, title: str | None = None) -> int:
        if title:
            show_sql(title, statement)
        return sql(
            self._require_connection(),
            statement,
            title=title,
            show_statement=False,
        )

    def query(self, statement: str) -> pd.DataFrame:
        connection = self._require_connection()
        clean = statement.strip().rstrip(";")
        with connection.cursor() as cursor:
            try:
                cursor.execute(clean)
                rows = cursor.fetchall() if cursor.description else []
            except pymysql.MySQLError as error:
                report_sql_error(None, clean, error)
                raise
            if cursor.description is None:
                raise ValueError("query() requires a statement that returns rows.")
            columns = [column[0] for column in cursor.description]
        if rows and isinstance(rows[0], Mapping):
            columns = list(rows[0])
        return result_frame(rows, columns)

    def wait_for_rows(
        self,
        statement: str,
        *,
        title: str,
        hint: str,
        min_rows: int = 1,
        timeout_seconds: int = 60,
    ) -> pd.DataFrame:
        """Rerun a query until it returns at least ``min_rows`` rows, then show them.

        Collectors export telemetry in batches, and Doris makes each load visible
        a few seconds after it arrives, so a check right after sending can still
        be empty. The statement is shown first so it can be rerun in any MySQL
        client; ``hint`` says what to check when the rows do not arrive in time.
        """
        clean = statement.strip().rstrip(";")
        show_sql(f"{title} (rerun every 2 seconds for up to {timeout_seconds} seconds)", clean)
        started = time.monotonic()
        while True:
            frame = self.query(clean)
            elapsed = time.monotonic() - started
            if len(frame) >= min_rows:
                show_frame(f"{title} · rows found after {elapsed:.0f} seconds", frame)
                return frame
            if elapsed >= timeout_seconds:
                break
            time.sleep(2)
        show_frame(title, frame)
        found = "No rows" if frame.empty else f"Only {len(frame)} of {min_rows} rows"
        self._failure(f"{found} after {timeout_seconds} seconds", hint)
        raise EnvironmentNotReady(f"{title} did not return {min_rows} row(s) within {timeout_seconds} seconds.")

    def profile_query(self, statement: str, *, title: str | None = None, timeout_seconds: int = 20) -> str:
        """Run a query that scans a table, show its result, and return the text of its Query Profile.

        Run it in a session with enable_profile = true. Each step that finds the
        profile is shown, so that it can be repeated in a MySQL client and a
        terminal: SELECT last_query_id() gives the ID of the query, SHOW QUERY
        PROFILE lists its profile, and the FE HTTP API returns the text, as the
        curl command shown would. The text is shown in a collapsed box.
        """
        self.sql(statement, title=title)
        connection = self._require_connection()
        show_sql("The ID of the query, which is also the ID of its profile", "SELECT last_query_id()")
        profile_id = last_query_id(connection)
        show_sql(f"Find the profile {profile_id}", "SHOW QUERY PROFILE")
        row = find_profile(connection, profile_id)
        if row is None:
            self._failure(
                "SHOW QUERY PROFILE does not list the query",
                f"Doris collected no profile of the query {profile_id}: it does so only in a session with "
                "enable_profile = true. Run the cell that sets the session variables, then rerun this cell.",
            )
            raise EnvironmentNotReady("SHOW QUERY PROFILE does not list the query.")
        show_frame("The profile of the query in SHOW QUERY PROFILE", pd.DataFrame(
            [{name: row.get(name) for name in ("Profile ID", "Start Time", "Total", "Sql Statement")}]
        ))
        show_sql(
            "Fetch the profile text from the FE HTTP API (the same request with curl)",
            f'curl -u root: "{self.fe_http_url}/api/profile/text?query_id={profile_id}"',
        )
        try:
            text = fetch_profile_text(
                self.fe_http_url,
                profile_id,
                ready=lambda answer: _scan_reported(answer) or "Is Cached: Yes" in answer,
                timeout_seconds=timeout_seconds,
            )
        except OSError as error:
            self._failure(
                "The FE HTTP API does not answer",
                f"Could not fetch {self.fe_http_url}/api/profile/text ({error}). Check that the DOG stack "
                "is running with the cells in Module 1, then rerun this cell.",
            )
            raise EnvironmentNotReady("the FE HTTP API does not answer.")
        if "Is Cached: Yes" in text:
            self._failure(
                "The result came from the SQL cache",
                "Doris answered the query from the SQL cache, without scanning the table. Run the cell "
                "that sets the session variables, which turns the SQL cache off, then rerun this cell.",
            )
            raise EnvironmentNotReady("the query was answered from the SQL cache.")
        if not _scan_reported(text):
            self._failure(
                "The profile has no table scan",
                f"The profile of {profile_id} shows no scan of a table after {timeout_seconds} seconds. "
                "Rerun this cell.",
            )
            raise EnvironmentNotReady("the profile shows no table scan.")
        show_log(f"Query Profile {profile_id}", text)
        return text

    def scan_filters(self, profile: str, *, title: str = "How the table scan filtered its rows") -> pd.Series:
        """Show how many rows the table scan of a profile skipped, dropped, and kept.

        Adds up each counter of SCAN_FILTER_COUNTERS over the scan instances in
        the profile's DetailProfile, and returns the totals by counter name.
        """
        detail = profile.split("DetailProfile", 1)[-1]
        totals = {name: profile_row_sum(detail, name) for name, _ in SCAN_FILTER_COUNTERS}
        missing = [name for name, total in totals.items() if not isinstance(total, int)]
        if missing:
            self._failure(
                "The profile does not show the scan counters",
                f"Missing: {', '.join(missing)}. Profiles show these counters at profile_level 2 or 3. "
                "Run the cell that sets the session variables, then rerun the cell that runs the query "
                "and this cell.",
            )
            raise EnvironmentNotReady(f"the profile does not show {', '.join(missing)}.")
        show_frame(title, pd.DataFrame(
            [{"counter": name, "rows": totals[name], "what happened to these rows": meaning}
             for name, meaning in SCAN_FILTER_COUNTERS]
        ))
        return pd.Series(totals, name="rows")

    def show_create_table(self, table: str) -> str:
        """Show the statement that SHOW CREATE TABLE returns for ``table``, as text, and return it."""
        statement = str(self.query(f"SHOW CREATE TABLE {table}").iloc[0, 1])
        show_sql(f"SHOW CREATE TABLE {table} returns", statement)
        return statement

    def explain_scan(self, statement: str, *, title: str = "Which partitions and tablets the query reads") -> pd.DataFrame:
        """Show which partitions and tablets each table scan of a query reads, and return the scans.

        Runs EXPLAIN, which plans the query without running it, and shows one row
        per scan, then the whole plan in a collapsed box. When Doris considered
        materialized views for the query, a second table lists them with the
        result and the reason.
        """
        clean = statement.strip().rstrip(";")
        show_sql(title, f"EXPLAIN {clean}")
        lines = [str(line) for line in self.query(f"EXPLAIN {clean}").iloc[:, 0]]
        scans, views = _plan_scans(lines)
        frame = pd.DataFrame(scans, columns=["table", "reads", "partitions", "tablets", "predicates"])
        if frame.empty:
            card("The plan reads no table: the partitions that the query's filters select hold no rows, "
                 "so Doris answers without reading any data.", "info", "No table scan")
        else:
            show_frame(f"{title} · {len(frame)} scan(s)", frame)
        if views:
            show_frame("The materialized views that Doris considered",
                       pd.DataFrame(views, columns=["materialized_view", "result", "reason"]))
        show_log("The whole plan", "\n".join(lines))
        return frame

    def tablet_rows(self, table: str, *, title: str | None = None) -> pd.DataFrame:
        """Count the rows of each tablet in the partitions of ``table`` that have data, and return them.

        SHOW TABLETS shows a tablet's row count only after its BE reports it, so
        each tablet is counted with SELECT COUNT(*) ... TABLET(<id>), which reads
        that tablet now. The statements are shown first.
        """
        show_sql(title or f"Count the rows in each tablet of {table}", "\n".join((
            f"SHOW PARTITIONS FROM {table}",
            f"SHOW TABLETS FROM {table} PARTITION (<partition>)",
            f"SELECT COUNT(*) FROM {table} TABLET(<tablet id>)",
        )))
        partitions = self.query(f"SHOW PARTITIONS FROM {table}")
        rows = []
        for partition, version in zip(partitions["PartitionName"], partitions["VisibleVersion"]):
            if int(version) <= 1:  # every load adds a version: version 1 has no data
                continue
            for tablet in self.query(f"SHOW TABLETS FROM {table} PARTITION ({partition})")["TabletId"]:
                count = self.query(f"SELECT COUNT(*) AS row_count FROM {table} TABLET({tablet})")["row_count"].iloc[0]
                rows.append({"partition": partition, "tablet": str(tablet), "rows": int(count)})
        frame = pd.DataFrame(rows, columns=["partition", "tablet", "rows"])
        totals = frame.groupby("partition")["rows"].transform("sum")
        frame["percent_of_partition"] = (100 * frame["rows"] / totals.where(totals > 0)).round(1)
        show_frame(f"Rows in each tablet of {table} · {len(frame)} tablet(s) in "
                   f"{frame['partition'].nunique()} partition(s) with data", frame)
        return frame

    def _read(self, url: str, service: str, hint: str, *, auth: tuple[str, str] | None = None) -> str:
        """GET a page from Grafana, Mailpit, or Litefuse; stop with a card when the service does not answer.

        ``auth`` is a user name and password for HTTP basic authentication.
        """
        headers = {}
        if auth:
            headers["Authorization"] = "Basic " + base64.b64encode(":".join(auth).encode()).decode()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=10) as response:
                return response.read().decode("utf-8")
        except (OSError, http.client.HTTPException) as error:
            self._failure(f"{service} does not answer", f"Could not read {url} ({error}). {hint}")
            raise EnvironmentNotReady(f"{service} does not answer.")

    def _send(self, method: str, url: str, body: Mapping | None = None, *, auth: tuple[str, str],
              headers: Mapping[str, str] | None = None, missing_ok: bool = False) -> str | None:
        """Send a request with a JSON body to Grafana as a signed-in user; stop with a card when Grafana refuses it.

        With ``missing_ok``, a 404 answer returns None instead.
        """
        request_headers = {"Content-Type": "application/json", **(headers or {}),
                           "Authorization": "Basic " + base64.b64encode(":".join(auth).encode()).decode()}
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            if missing_ok and error.code == 404:
                return None
            if error.code in (401, 403):
                self._failure(
                    "Grafana refused the admin password",
                    f"Grafana answered {error.code}. Set GRAFANA_ADMIN_PASSWORD to the password of the user admin: "
                    "admin, unless you set a new one when you first signed in. Then rerun this cell.",
                )
                raise EnvironmentNotReady("Grafana refused the admin password.")
            detail = error.read().decode("utf-8", "replace")
            self._failure(f"Grafana refused the request ({error.code})", f"{method} {url}: {detail}")
            raise EnvironmentNotReady(f"Grafana refused the request ({error.code}).")
        except (OSError, http.client.HTTPException) as error:
            self._failure("Grafana does not answer", f"Could not reach {url} ({error}). {GRAFANA_HINT}")
            raise EnvironmentNotReady("Grafana does not answer.")

    def _no_rule(self, rule: str) -> None:
        self._failure(
            f"Grafana has no alert rule named {rule!r}",
            "Create the rule in Grafana (Alerting > Alert rules > New alert rule), save it with exactly "
            "this name, then rerun this cell.",
        )
        raise EnvironmentNotReady(f"Grafana has no alert rule named {rule!r}.")

    def _grafana_rule(self, rule: str) -> dict:
        """The rule named ``rule`` in Grafana's rules API, with the instances of its last evaluation."""
        data = json.loads(self._read(self.grafana_url + GRAFANA_RULES_PATH, "Grafana", GRAFANA_HINT))
        for group in data.get("data", {}).get("groups", []):
            for found in group.get("rules", []):
                if found.get("name") == rule:
                    return found
        self._no_rule(rule)

    def alert_instances(self, rule: str) -> pd.DataFrame:
        """Show the instances of a Grafana alert rule: their labels, states, and summaries.

        Grafana evaluates the rule on its own schedule. This reads the result of the
        last evaluation from Grafana's rules API; the request is shown first, so that
        it can be repeated with curl.
        """
        url = self.grafana_url + GRAFANA_RULES_PATH
        show_sql(f"Read the state of the rule {rule!r} from Grafana's rules API", f'curl -s "{url}"')
        found = self._grafana_rule(rule)
        frame = _alert_frame(found)
        if frame.empty:
            card("Grafana has not evaluated the rule yet. It does so at the interval of the rule's "
                 "evaluation group: rerun this cell after that.", "info", "No instances yet")
            return frame
        show_frame(f"{rule} · last evaluated at {_utc(found.get('lastEvaluation'))} UTC · "
                   f"health {found.get('health')}", frame)
        return frame

    def wait_for_alert_state(self, rule: str, state: str, *, hint: str, timeout_seconds: int = 300) -> pd.DataFrame:
        """Reread a Grafana alert rule every 5 seconds until all its instances are in ``state``.

        Shows how the instances changed on the way, with the evaluation that
        changed them, then the instances. ``hint`` says what to check when the
        state does not come in time.
        """
        url = self.grafana_url + GRAFANA_RULES_PATH
        show_sql(f"Wait until every instance of {rule!r} is {state} "
                 f"(read every 5 seconds for up to {timeout_seconds} seconds)", f'curl -s "{url}"')
        started = time.monotonic()
        changes, last = [], None
        while True:
            found = self._grafana_rule(rule)
            frame = _alert_frame(found)
            elapsed = time.monotonic() - started
            instances = "; ".join(f"{name}: {current}" for name, current in zip(frame["instance"], frame["state"]))
            if instances != last:
                changes.append({"after_seconds": round(elapsed), "evaluated_at_utc": _utc(found.get("lastEvaluation")),
                                "instances": instances or "(none)"})
                last = instances
            done = not frame.empty and (frame["state"] == state).all()
            if done or elapsed >= timeout_seconds:
                break
            time.sleep(5)
        show_frame(f"How the instances of {rule} changed", pd.DataFrame(changes))
        if done:
            show_frame(f"{rule} · every instance is {state} after {elapsed:.0f} seconds", frame)
            return frame
        show_frame(rule, frame)
        self._failure(f"{rule} is not {state} after {timeout_seconds} seconds", hint)
        raise EnvironmentNotReady(f"{rule} did not become {state} within {timeout_seconds} seconds.")

    def wait_for_email(
        self,
        subject: str,
        *,
        hint: str,
        after: datetime | None = None,
        timeout_seconds: int = 120,
    ) -> dict:
        """Wait until Mailpit has received an email whose subject contains ``subject``, then show it.

        ``after``, a timezone-aware time, skips older emails, such as those of an
        earlier run of the same steps. The text of the email is in a collapsed box.
        """
        url = f"{self.mailpit_url}/api/v1/messages"
        show_sql(f"Wait for an email whose subject contains {subject!r} "
                 f"(read every 3 seconds for up to {timeout_seconds} seconds)", f'curl -s "{url}"')
        started = time.monotonic()
        while True:
            messages = json.loads(self._read(url, "Mailpit", MAILPIT_HINT)).get("messages") or []
            match = next((message for message in messages if subject in message.get("Subject", "")
                          and (after is None or _received(message) >= after)), None)
            elapsed = time.monotonic() - started
            if match is not None:
                break
            if elapsed >= timeout_seconds:
                self._failure(f"No email about {subject!r} after {timeout_seconds} seconds", hint)
                raise EnvironmentNotReady(f"no email whose subject contains {subject!r} arrived "
                                          f"within {timeout_seconds} seconds.")
            time.sleep(3)
        detail = json.loads(self._read(f"{self.mailpit_url}/api/v1/message/{match['ID']}", "Mailpit", MAILPIT_HINT))
        received = _received(match)
        sender = match.get("From") or {}
        show_frame(f"The email in Mailpit · found after {elapsed:.0f} seconds", pd.DataFrame([{
            "received_utc": received.strftime("%Y-%m-%d %H:%M:%S"),
            "from": f"{sender.get('Name', '')} <{sender.get('Address', '')}>",
            "to": ", ".join(item.get("Address", "") for item in match.get("To") or []),
            "subject": match.get("Subject", ""),
        }]))
        text = detail.get("Text", "")
        show_log(f"The text of the email (in the inbox at {self.mailpit_url})", text)
        return {"id": match["ID"], "subject": match.get("Subject", ""), "received": received, "text": text}

    def export_alert_rule(self, rule: str) -> str:
        """Show a Grafana alert rule as provisioning YAML, from Grafana's export API, and return it."""
        url = f"{self.grafana_url}/api/v1/provisioning/alert-rules"
        rules = json.loads(self._read(url, "Grafana", GRAFANA_HINT))
        uid = next((found.get("uid") for found in rules if found.get("title") == rule), None)
        if uid is None:
            self._no_rule(rule)
        export = f"{url}/{uid}/export?format=yaml"
        show_sql(f"Export the rule {rule!r} as provisioning YAML", f'curl -s "{export}"')
        text = self._read(export, "Grafana", GRAFANA_HINT)
        show_log(f"The rule {rule!r} as provisioning YAML", text, opened=True)
        return text

    def provision_alert_rule_group(self, folder: str, group: str, rules: Sequence[Mapping], *,
                                   interval_seconds: int, admin_password: str) -> dict:
        """Create or replace a Grafana alert rule group from code, with Grafana's provisioning API.

        Finds the folder by its title, creating it when it is missing. A rule with
        a fixed "uid" that Grafana does not have yet is created with POST, because
        a group's PUT only updates the rules whose uid exists. Then the group is
        sent with PUT: afterwards it holds exactly ``rules``, evaluated every
        ``interval_seconds``, and a rerun updates the same rules. The header
        X-Disable-Provenance keeps the rules editable in Grafana's web page.
        Writing needs the admin's password; the requests are shown first, without it.
        """
        auth = ("admin", admin_password)
        headers = {"X-Disable-Provenance": "true"}
        folders_url = f"{self.grafana_url}/api/folders"
        rules_url = f"{self.grafana_url}/api/v1/provisioning/alert-rules"
        group_url = f"{self.grafana_url}/api/v1/provisioning/folder/<folder uid>/rule-groups/{group}"
        show_sql(
            f"Create or replace the rule group {group!r} in the folder {folder!r}",
            f'curl -s -u admin:<password> "{folders_url}"\n'
            f'curl -s -u admin:<password> -X POST -H "Content-Type: application/json" '
            f'-H "X-Disable-Provenance: true" --data @rule.json "{rules_url}"   # once for each new rule\n'
            f'curl -s -u admin:<password> -X PUT -H "Content-Type: application/json" '
            f'-H "X-Disable-Provenance: true" --data @rule-group.json "{group_url}"',
        )
        folders = json.loads(self._send("GET", folders_url, auth=auth))
        uid = next((item.get("uid") for item in folders if item.get("title") == folder), None)
        if uid is None:
            uid = json.loads(self._send("POST", folders_url, {"title": folder}, auth=auth))["uid"]
        for rule in rules:
            if rule.get("uid") and self._send("GET", f"{rules_url}/{rule['uid']}", auth=auth, missing_ok=True) is None:
                self._send("POST", rules_url, {**rule, "folderUID": uid, "ruleGroup": group}, auth=auth, headers=headers)
        body = {"title": group, "interval": interval_seconds, "rules": list(rules)}
        answer = json.loads(self._send("PUT", group_url.replace("<folder uid>", uid), body, auth=auth, headers=headers))
        show_frame(f"The rule group {group!r} in {folder!r}, evaluated every {interval_seconds} seconds", pd.DataFrame([
            {"rule": rule.get("title"), "uid": rule.get("uid"), "pending_period": rule.get("for"),
             "labels": ", ".join(f"{key}={value}" for key, value in sorted((rule.get("labels") or {}).items()))}
            for rule in answer.get("rules") or []
        ], columns=["rule", "uid", "pending_period", "labels"]))
        return answer

    def grafana_dashboard(self, title: str) -> pd.DataFrame:
        """Show the panels of a saved Grafana dashboard, with the SQL of each, and return them.

        Reads the dashboard from Grafana's API as Grafana's anonymous viewer, so
        it does not depend on the admin password; the requests are shown first,
        so that they can be repeated with curl.
        """
        search = f"{self.grafana_url}/api/search?type=dash-db&query={urllib.parse.quote(title)}"
        show_sql(
            f"Find the dashboard {title!r}, then read it, from Grafana's API",
            f'curl -s "{search}"\ncurl -s "{self.grafana_url}/api/dashboards/uid/<uid of the dashboard>"',
        )
        found = [item for item in json.loads(self._read(search, "Grafana", GRAFANA_HINT)) if item.get("title") == title]
        if not found:
            self._failure(
                f"Grafana has no dashboard named {title!r}",
                "Save the dashboard in Grafana: click Save dashboard, enter exactly this title, and click Save. "
                "Then rerun this cell.",
            )
            raise EnvironmentNotReady(f"Grafana has no dashboard named {title!r}.")
        uid = found[0]["uid"]
        dashboard = json.loads(self._read(f"{self.grafana_url}/api/dashboards/uid/{uid}", "Grafana",
                                          GRAFANA_HINT)).get("dashboard") or {}
        rows = [
            {"panel": panel.get("title"), "visualization": panel.get("type"),
             "format": target.get("format"), "sql": target.get("rawSql", "")}
            for panel in dashboard.get("panels") or []
            for target in panel.get("targets") or [{}]
        ]
        frame = pd.DataFrame(rows, columns=["panel", "visualization", "format", "sql"])
        show_frame(f"The panels of {title} · {self.grafana_url}/d/{uid}", frame)
        return frame

    def connect(
        self,
        *,
        container: str = DORIS_CONTAINER,
        host: str = "127.0.0.1",
        port: int = env.QUERY_PORT,
    ):
        wait_for_health(container, timeout_seconds=300, report=False)
        self.DORIS_CONTAINER = container
        self.connection = connect_doris(host=host, port=port, connect_timeout=5)
        return self.connection

    def shell(self, script: str, *, title: str) -> subprocess.CompletedProcess[str]:
        """Run learner-visible Bash from the course root with live progress."""
        return run_shell(script, title=title, cwd=self.lab_dir)

    def ensure_docker_ready(self, *, timeout_seconds: int = 180) -> None:
        """Ensure the Docker daemon is reachable, starting Docker Desktop on macOS."""
        labkit_docker.ensure_docker_ready(timeout_seconds=timeout_seconds)

    def start_container(
        self,
        container: str = DORIS_CONTAINER,
        *,
        wait_for_healthy: bool = True,
        timeout_seconds: int = 300,
    ) -> dict:
        """Start or reuse an existing course container."""
        return labkit_docker.start_container(
            container,
            wait_for_healthy=wait_for_healthy,
            timeout_seconds=timeout_seconds,
            missing_hint="Run prepare_environment() first.",
        )

    def _compose_script(self, body: str) -> str:
        """Prefix ``body`` with the stack location and the course's two Compose commands."""
        header = f"""set -euo pipefail

COURSE_ROOT="$(pwd -P)"
STACK_DIR="$COURSE_ROOT/{self.RUNTIME_DIRECTORY}/{self.STACK_DIRECTORY}"
STACK_REPOSITORY={shlex.quote(env.STACK_REPOSITORY)}
STACK_COMMIT={env.STACK_COMMIT}
export DORIS_OBS_COURSE_ROOT="$COURSE_ROOT"

# The upstream Compose files with this course's overrides (environments/dog-stack/).
dog_compose() {{
  (cd "$STACK_DIR/docker" && docker compose -p {env.PROJECT} \\
    -f docker-compose.yaml -f "$COURSE_ROOT/environments/dog-stack/compose.dog.yml" "$@")
}}
demo_compose() {{
  local env_files=(--env-file .env)
  # Java workaround for recent Apple silicon (JDK-8345296), as in the demo's Makefile.
  if [ "$(uname -s)" = Darwin ] && [ "$(uname -m)" = arm64 ]; then
    env_files+=(--env-file .env.arm64)
  fi
  (cd "$STACK_DIR/doris-opentelemetry-demo" && docker compose -p {env.DEMO_PROJECT} "${{env_files[@]}}" \\
    -f docker-compose.yml -f "$COURSE_ROOT/environments/dog-stack/compose.demo.yml" "$@")
}}
"""
        return header + body

    def _check_compose_version(self) -> None:
        result = run(["docker", "compose", "version", "--short"], check=False)
        found = result.stdout.strip() if result.returncode == 0 else ""
        numbers = tuple(int(part) for part in re.findall(r"\d+", found)[:3])
        if numbers < MIN_COMPOSE_VERSION:
            required = ".".join(map(str, MIN_COMPOSE_VERSION))
            self._failure(
                "Docker Compose is too old",
                f"This course needs Docker Compose {required} or later; found {found or 'no Compose plugin'}. "
                "Update Docker Desktop or the Docker Compose plugin, then rerun this cell.",
            )
            raise EnvironmentNotReady(f"Docker Compose {required} or later is required.")

    def _check_ports(self, ports: Sequence[tuple[int, str, str]], containers: Sequence[str]) -> None:
        """Show the host ports a step publishes; stop when another program holds one."""
        published: set[int] = set()
        for name in containers:
            state = container_inspect(name)
            # A running course container may already publish the port.
            if state and state.get("State", {}).get("Running"):
                for bindings in (state.get("HostConfig", {}).get("PortBindings") or {}).values():
                    published.update(int(item["HostPort"]) for item in bindings or [] if item.get("HostPort"))
        rows, blocked = [], []
        for port, variable, purpose in ports:
            if port in published:
                status = "used by this course"
            elif port_in_use(port):
                status = "in use"
                blocked.append(f"{port} ({variable})")
            else:
                status = "available"
            rows.append({"host_port": port, "purpose": purpose, "variable": variable, "status": status})
        show_frame("Host port check", pd.DataFrame(rows))
        if blocked:
            self._failure(
                "Required port is unavailable",
                f"Another program is using: {', '.join(blocked)}. Stop it, or set the variable "
                "to a free port before starting Jupyter, then rerun this cell.",
            )
            raise EnvironmentNotReady("a required host port is in use.")

    def prepare_environment(self) -> None:
        """Check out the pinned DOG stack and start Doris, the OTel Collector, Grafana, and Mailpit."""
        self.ensure_docker_ready()
        self._check_compose_version()
        self._check_ports(CORE_PORTS, (env.DORIS_CONTAINER, env.COLLECTOR_CONTAINER, env.GRAFANA_CONTAINER,
                                       env.MAILPIT_CONTAINER))
        script = self._compose_script(r"""
echo "[1/4] Prepare the local runtime directory"
mkdir -p .runtime/doris-logs/fe

echo "[2/4] Check out the pinned DOG stack"
""" + CHECKOUT_STACK + r"""
echo "[3/4] Start the DOG core services"
dog_compose up -d

echo "[4/4] Show the running stack"
dog_compose ps
""")
        self.shell(script, title="Prepare the DOG observability environment")
        self.connect()
        wait_for_health(env.GRAFANA_CONTAINER, timeout_seconds=300, report=False)
        self.execute("CREATE DATABASE IF NOT EXISTS otel")
        self.execute("USE otel")
        nodes = [
            {"node": node, "host": row.get("Host"), "version": row.get("Version"), "alive": row.get("Alive")}
            for node, statement in (("FE", "SHOW FRONTENDS"), ("BE", "SHOW BACKENDS"))
            for row in self.query(statement).to_dict("records")
        ]
        show_frame("Doris nodes (SHOW FRONTENDS, SHOW BACKENDS)", pd.DataFrame(nodes))
        self.sql("SELECT DATABASE() AS current_database", title="Current database")
        card(
            f"Grafana: {self.grafana_url}/a/velodb-doris-app (user admin, password admin). "
            f"Doris: 127.0.0.1:{env.QUERY_PORT} for MySQL clients, {self.fe_http_url} for HTTP. "
            f"Mailpit, the inbox for Grafana's emails in Module 8: {self.mailpit_url}.",
            "ok",
            "The DOG stack is running",
        )

    def _dog_stack_running(self) -> bool:
        state = container_inspect(env.COLLECTOR_CONTAINER)
        return bool(
            state
            and state.get("State", {}).get("Running")
            and env.NETWORK in state.get("NetworkSettings", {}).get("Networks", {})
        )

    def start_demo(self, *, timeout_seconds: int = 180) -> None:
        """Start the OpenTelemetry demo storefront, which sends its telemetry to the DOG Collector.

        Returns once every demo container is running and the storefront answers.
        """
        self.ensure_docker_ready()
        if not self._dog_stack_running():
            self._failure(
                "The DOG stack is not running",
                "The demo sends its telemetry to the DOG Collector. Run lab.prepare_environment() "
                "in Module 1 first, then rerun this cell.",
            )
            raise EnvironmentNotReady("the DOG stack is not running.")
        self._check_compose_version()
        self._check_ports(DEMO_PORTS, (env.DEMO_PROXY_CONTAINER,))
        script = self._compose_script(r"""
echo "[1/2] Start the demo services"
demo_compose up -d

echo "[2/2] Show the demo services"
demo_compose ps
""")
        self.shell(script, title="Start the OpenTelemetry demo")
        self._wait_for_demo(timeout_seconds)

    def _demo_containers(self) -> pd.DataFrame:
        """Every container of the demo's Compose project, with its state and restart count."""
        listed = run(["docker", "ps", "--all", "--quiet", "--filter",
                      f"label=com.docker.compose.project={env.DEMO_PROJECT}"], check=False)
        ids = listed.stdout.split()
        # A container removed after the listing is reported on stderr; the others are still printed.
        inspected = json.loads(run(["docker", "container", "inspect", *ids], check=False).stdout or "[]") if ids else []
        rows = [
            {"container": state["Name"].lstrip("/"), "state": state["State"]["Status"],
             "restarts": state.get("RestartCount", 0)}
            for state in inspected
        ]
        return pd.DataFrame(rows, columns=["container", "state", "restarts"]).sort_values("container", ignore_index=True)

    @staticmethod
    def _http_status(url: str) -> int | None:
        """The HTTP status of a page, or None when the server does not answer."""
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                return response.status
        except urllib.error.HTTPError as error:
            return error.code
        except (OSError, http.client.HTTPException):
            return None

    def _storefront_status(self) -> int | None:
        """The HTTP status of the storefront page, or None when it does not answer."""
        # The proxy keeps the connection open while the frontend starts, so no answer is often a timeout.
        # Ask for the page "/", not the bare host: through an HTTP proxy, such as a system proxy on macOS
        # that does not exempt 127.0.0.1, urllib sends the URL as written, and Envoy rejects a request
        # target without a path with HTTP 400.
        return self._http_status(f"{self.demo_url}/")

    def _wait_for_demo(self, timeout_seconds: int) -> None:
        """Wait until every demo container is running and the storefront answers; stop with a card otherwise."""
        started = time.monotonic()
        while True:
            containers = self._demo_containers()
            not_running = containers[containers["state"] != "running"]
            status = self._storefront_status()
            elapsed = time.monotonic() - started
            if not containers.empty and not_running.empty and status == 200:
                break
            if elapsed >= timeout_seconds:
                if not not_running.empty:
                    show_frame("Demo containers that are not running", not_running)
                if containers.empty or not not_running.empty:
                    self._failure(
                        "The demo did not start",
                        f"Not every demo container is running after {timeout_seconds} seconds. Read a container's "
                        f"log with docker logs <container>, for example docker logs {env.DEMO_PROXY_CONTAINER}. "
                        "Containers that keep exiting often mean that Docker is short of memory: see Environment "
                        "in the course README. Then rerun this cell.",
                    )
                else:
                    answer = f"HTTP {status}" if status else "no answer"
                    self._failure(
                        "The storefront does not answer",
                        f"All demo containers are running, but {self.demo_url} gave {answer} for "
                        f"{timeout_seconds} seconds. Read the logs with docker logs {env.DEMO_PROXY_CONTAINER} "
                        f"and docker logs {env.DEMO_PROJECT}-frontend, then rerun this cell.",
                    )
                raise EnvironmentNotReady(f"the demo was not ready within {timeout_seconds} seconds.")
            time.sleep(3)
        restarted = containers[containers["restarts"] > 0]
        if not restarted.empty:
            show_frame("Demo containers that restarted at least once (all are running now)", restarted)
        card(
            f"All {len(containers)} demo containers are running, and the storefront at {self.demo_url} "
            f"answers (waited {elapsed:.0f} seconds).",
            "ok",
            "The demo is running",
        )

    def stop_demo(self) -> None:
        """Stop and remove the demo's containers and volumes.

        The telemetry already in Doris stays, and so do the demo's feature flags.
        """
        # Compose finds a project's containers, networks, and volumes by their labels, without the files.
        # The images of jaeger, kafka, and prometheus declare volumes that the demo's Compose file does
        # not name, so Docker creates anonymous ones; the next start creates new ones instead of reusing them.
        self.shell(f"docker compose -p {env.DEMO_PROJECT} down --volumes", title="Stop the OpenTelemetry demo")

    def _feature_flags(self, url: str) -> dict:
        """Every feature flag of the demo, as the flag service resolves it now."""
        request = urllib.request.Request(url, data=b'{"context": {}}', method="POST",
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return json.loads(response.read().decode("utf-8")).get("flags") or {}
        except (OSError, http.client.HTTPException, ValueError) as error:
            self._failure(
                "The demo's flag service does not answer",
                f"Could not read {url} ({error}). Check that the demo runs: run lab.start_demo() in "
                "Module 1, then rerun this cell.",
            )
            raise EnvironmentNotReady("the demo's flag service does not answer.")

    def wait_for_feature_flag(self, flag: str, variant: str, *, timeout_seconds: int = 180) -> pd.DataFrame:
        """Wait until the demo's flag service serves ``variant`` for ``flag``, then show the flag.

        Set the flag in the demo's flag page, {demo_url}/feature. This asks the
        flag service, flagd, through the storefront's proxy, as the storefront's
        pages do in the browser; the request is shown first, so that it can be
        repeated with curl.
        """
        url = self.demo_url + FLAGD_RESOLVE_ALL_PATH
        show_sql(
            f"Ask the demo's flag service for its flags until {flag} is {variant} "
            f"(every 2 seconds for up to {timeout_seconds} seconds)",
            f"curl -s -X POST -H 'Content-Type: application/json' -d '{{\"context\": {{}}}}' \"{url}\"",
        )
        started = time.monotonic()
        while True:
            found = self._feature_flags(url).get(flag)
            elapsed = time.monotonic() - started
            if found is not None and found.get("variant") == variant:
                break
            if elapsed >= timeout_seconds:
                if found is None:
                    message = f"The demo has no feature flag named {flag}. Check the name in {self.demo_url}/feature."
                else:
                    message = (f"{flag} is {found.get('variant')}, not {variant}. Open {self.demo_url}/feature, "
                               f"choose {variant} in the {flag} card, click save, then rerun this cell.")
                self._failure(f"{flag} is not {variant}", message)
                raise EnvironmentNotReady(f"{flag} was not {variant} within {timeout_seconds} seconds.")
            time.sleep(2)
        value = next((found[key] for key in ("doubleValue", "boolValue", "stringValue", "intValue") if key in found),
                     None)
        frame = pd.DataFrame([{"flag": flag, "variant": found.get("variant"), "value": value}])
        show_frame(f"{flag} in the demo's flag service · after {elapsed:.0f} seconds", frame)
        return frame

    def _set_be_private_endpoint(self) -> None:
        """Make the FE redirect Stream Loads from other containers to an address where they reach the BE.

        Clients such as Litefuse send a Stream Load to the FE, which redirects it
        to the BE. In the single-container Doris the BE is registered as
        127.0.0.1, which another container cannot reach. When a BE has a private
        endpoint, the FE redirects to the host that the client used for the FE,
        doris-obs, with the port of the endpoint. MODIFY BACKEND replaces all
        tags of the BE, so the statement repeats the ones it has.
        """
        for backend in self.query("SHOW BACKENDS").to_dict("records"):
            tags = json.loads(backend.get("Tag") or "{}")
            tags["private_endpoint"] = env.DORIS_BE_HTTP_ENDPOINT
            ordered = sorted(tags.items(), key=lambda item: item[0] != "location")
            assignments = ",\n     ".join(f'"tag.{name}" = "{value}"' for name, value in ordered)
            self.execute(
                f'ALTER SYSTEM MODIFY BACKEND "{backend["Host"]}:{backend["HeartbeatPort"]}"\n'
                f"SET ({assignments})",
                title="Give the BE an address that the other containers can reach",
            )

    def start_litefuse(self, *, timeout_seconds: int = 180) -> None:
        """Start Litefuse, which keeps its LLM traces in this course's Doris, in the database litefuse.

        Returns once its web UI and API answer and accept the course's API keys.
        """
        self.ensure_docker_ready()
        if not self._dog_stack_running():
            self._failure(
                "The DOG stack is not running",
                "Litefuse keeps its tables in the DOG stack's Doris. Run lab.prepare_environment() "
                "in Module 1 first, then rerun this cell.",
            )
            raise EnvironmentNotReady("the DOG stack is not running.")
        self._check_compose_version()
        self._check_ports(LITEFUSE_PORTS, (env.LITEFUSE_WEB_CONTAINER,))
        self._set_be_private_endpoint()
        compose = f"docker compose -p {env.LITEFUSE_PROJECT} -f {LITEFUSE_COMPOSE_FILE}"
        self.shell(f"""set -euo pipefail

echo "[1/2] Start Litefuse"
{compose} up -d

echo "[2/2] Show the Litefuse services"
{compose} ps
""", title="Start Litefuse")
        self._wait_for_litefuse(timeout_seconds)

    def _wait_for_litefuse(self, timeout_seconds: int) -> None:
        """Wait until Litefuse answers, then check its project with the course's API keys."""
        health = f"{self.litefuse_url}/api/public/health"
        projects = f"{self.litefuse_url}/api/public/projects"
        keys = (env.LITEFUSE_PUBLIC_KEY, env.LITEFUSE_SECRET_KEY)
        show_sql(
            f"Wait until Litefuse answers (every 3 seconds for up to {timeout_seconds} seconds), "
            "then read the project that the API keys belong to",
            f'curl -s "{health}"\ncurl -s -u {":".join(keys)} "{projects}"',
        )
        started = time.monotonic()
        while self._http_status(health) != 200:
            if time.monotonic() - started >= timeout_seconds:
                self._failure(
                    "Litefuse does not answer",
                    f"{health} did not answer with HTTP 200 within {timeout_seconds} seconds. On its first "
                    "start, Litefuse creates its database in Postgres and its tables in Doris before it "
                    f"answers. Read the log with docker logs {env.LITEFUSE_WEB_CONTAINER}, then rerun this cell.",
                )
                raise EnvironmentNotReady(f"Litefuse did not answer within {timeout_seconds} seconds.")
            time.sleep(3)
        elapsed = time.monotonic() - started
        found = json.loads(self._read(projects, "Litefuse", LITEFUSE_HINT, auth=keys)).get("data") or []
        project = next((item for item in found if item.get("id") == env.LITEFUSE_PROJECT_ID), None)
        if project is None:
            self._failure(
                "The API keys do not belong to the course's project",
                f"Litefuse answers, but the keys belong to no project with the ID {env.LITEFUSE_PROJECT_ID}. "
                f"Remove Litefuse with docker compose -p {env.LITEFUSE_PROJECT} down --volumes, then rerun "
                "this cell: Litefuse creates the project, its keys, and the user when it starts on empty volumes.",
            )
            raise EnvironmentNotReady("the course's Litefuse project is missing.")
        show_frame("The project that the API keys belong to", pd.DataFrame([{
            "organization": (project.get("organization") or {}).get("name"),
            "project": project.get("name"),
            "project_id": project.get("id"),
        }]))
        card(
            f"Litefuse answers at {self.litefuse_url} (waited {elapsed:.0f} seconds). Sign in with "
            f"{env.LITEFUSE_USER_EMAIL} and the password {env.LITEFUSE_USER_PASSWORD}. Its tables are in "
            f"the Doris database {env.LITEFUSE_DATABASE}.",
            "ok",
            "Litefuse is running",
        )

    def litefuse_trace(self, trace_id: str) -> dict:
        """Show a trace as Litefuse's public API returns it, one row per observation, and return it."""
        url = f"{self.litefuse_url}/api/public/traces/{trace_id}"
        show_sql(
            "Read the trace from Litefuse's public API",
            f'curl -s -u {env.LITEFUSE_PUBLIC_KEY}:{env.LITEFUSE_SECRET_KEY} "{url}"',
        )
        trace = json.loads(self._read(url, "Litefuse", LITEFUSE_HINT,
                                      auth=(env.LITEFUSE_PUBLIC_KEY, env.LITEFUSE_SECRET_KEY)))
        observations = sorted(trace.get("observations") or [], key=lambda item: item.get("startTime") or "")
        show_frame(
            f"Trace {trace.get('name')} ({trace_id}) · latency {trace.get('latency')} s · "
            f"total cost {trace.get('totalCost')} USD",
            pd.DataFrame([{
                "type": item.get("type"),
                "name": item.get("name"),
                "start_time_utc": _utc(item.get("startTime")),
                "latency_s": item.get("latency"),
                "model": item.get("model"),
                "usage": item.get("usageDetails"),
                "cost_usd": (item.get("costDetails") or {}).get("total"),
            } for item in observations], columns=["type", "name", "start_time_utc", "latency_s", "model",
                                                   "usage", "cost_usd"]),
        )
        return trace

    def stop_litefuse(self) -> None:
        """Stop and remove the Litefuse containers. Its user, keys, and traces stay for the next start."""
        self.shell(f"docker compose -p {env.LITEFUSE_PROJECT} down", title="Stop Litefuse")

    def start_local_model(self, *, timeout_seconds: int = 120) -> None:
        """Download the course's small open model once, then serve it with llama.cpp's server.

        Returns once the server answers and lists the model. The model file is
        checked against its SHA-256 at every start.
        """
        self.ensure_docker_ready()
        self._check_compose_version()
        self._check_ports(LOCAL_MODEL_PORTS, (env.LOCAL_MODEL_CONTAINER,))
        compose = f"docker compose -p {env.LOCAL_MODEL_PROJECT} -f {LOCAL_MODEL_COMPOSE_FILE}"
        self.shell(f"""set -euo pipefail

echo "[1/3] Download the model file once ({env.LOCAL_MODEL_FILE}, 491 MB)"
{compose} run --rm --no-deps --entrypoint sh \\
  -e MODEL_FILE={env.LOCAL_MODEL_FILE} -e MODEL_SHA256={env.LOCAL_MODEL_SHA256} -e MODEL_MB=491 \\
  llm -c {shlex.quote(DOWNLOAD_LOCAL_MODEL)} {shlex.quote(env.LOCAL_MODEL_URL)}

echo "[2/3] Start the model server"
{compose} up -d

echo "[3/3] Show the model server"
{compose} ps
""", title="Start the local model")
        self._wait_for_local_model(timeout_seconds)

    def _wait_for_local_model(self, timeout_seconds: int) -> None:
        """Wait until the model server answers, then show the models that it serves."""
        health = f"{self.local_model_url}/health"
        models = f"{self.local_model_url}/v1/models"
        show_sql(
            f"Wait until the model server answers (every 2 seconds for up to {timeout_seconds} seconds), "
            "then list its models",
            f'curl -s "{health}"\ncurl -s "{models}"',
        )
        started = time.monotonic()
        while self._http_status(health) != 200:
            if time.monotonic() - started >= timeout_seconds:
                self._failure(
                    "The model server does not answer",
                    f"{health} did not answer with HTTP 200 within {timeout_seconds} seconds. Read the log with "
                    f"docker logs {env.LOCAL_MODEL_CONTAINER}, then rerun this cell.",
                )
                raise EnvironmentNotReady(f"the model server did not answer within {timeout_seconds} seconds.")
            time.sleep(2)
        elapsed = time.monotonic() - started
        served = [item.get("id") for item in json.loads(self._read(
            models, "The model server", f"Read the log with docker logs {env.LOCAL_MODEL_CONTAINER}, "
            "then rerun this cell.")).get("data") or []]
        show_frame("Models that the server offers", pd.DataFrame({"model": served}))
        card(
            f"The model {env.LOCAL_MODEL} answers at {self.local_model_url}/v1, the OpenAI chat completions "
            f"API (waited {elapsed:.0f} seconds).",
            "ok",
            "The local model is running",
        )

    def stop_local_model(self) -> None:
        """Stop and remove the model server. The downloaded model file stays for the next start."""
        self.shell(f"docker compose -p {env.LOCAL_MODEL_PROJECT} down", title="Stop the local model")

    def openai_api_key(self) -> str:
        """The OpenAI API key from the environment variable OPENAI_API_KEY; stop with a card when it is not set.

        The key is read from the environment, not written in a notebook, so that
        it never ends up in a file that is saved or shared.
        """
        key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not key:
            self._failure(
                "OPENAI_API_KEY is not set",
                "Stop Jupyter, set the variable in the terminal, for example export OPENAI_API_KEY=sk-..., "
                "start Jupyter again from that terminal, and rerun the cells. Or choose the local model.",
            )
            raise EnvironmentNotReady("OPENAI_API_KEY is not set.")
        return key

    def check_trace_collector_port(self) -> None:
        """Show the host port of the Module 2 trace collector; stop when another program holds it."""
        self._check_ports(TRACE_COLLECTOR_PORTS, (env.TRACE_COLLECTOR_CONTAINER,))

    def teardown(self, *, keep_data: bool = False) -> None:
        """Remove every container and network of this course, and its volumes unless keep_data.

        With keep_data=True, prepare_environment() and start_litefuse() later
        start Doris, Grafana, and Litefuse again with the same data, and
        start_local_model() does not download the model again. Without it, the
        Module 2 log collector's read position goes too, since it describes how
        much of the FE log the removed Doris had loaded, and the demo's feature
        flags go back to off. The demo's volumes go in either case, as in
        stop_demo(): a later start does not reuse them. The Doris logs stay in
        .runtime/, given to the learner's user so that they can be deleted.
        """
        volumes = "" if keep_data else " --volumes"
        state = f"{self.RUNTIME_DIRECTORY}/{self.COLLECTOR_STATE_DIRECTORY}"
        stack = f"{self.RUNTIME_DIRECTORY}/{self.STACK_DIRECTORY}"
        logs = f"{self.RUNTIME_DIRECTORY}/{self.DORIS_LOG_DIRECTORY}"
        if keep_data:
            forget = ('echo "[7/7] Keep the Module 2 log collector\'s read position and the demo\'s feature flags"\n'
                      f'echo "Kept {state}/ and the flags for the next start."')
        else:
            # The flag page saves the flags to a file of the upstream checkout; the pinned commit has them all off.
            forget = f"""echo "[7/7] Forget where the Module 2 log collector stopped reading, and turn the demo's feature flags off"
rm -rf {state}
if [ -d {stack}/.git ]; then
  git -C {stack} checkout -- {FLAGS_FILE}
fi"""
        containers = " ".join((*env.MODULE2_COLLECTORS, env.CPU_LOAD_CONTAINER))
        # Compose finds each project's containers, networks, and volumes by their labels,
        # so this also works after .runtime/ was deleted. The demo Collector, Litefuse,
        # and the Module 2 collectors are attached to the doris-obs network: remove them first.
        # Step 6 gives the files that Doris wrote as root in the bind mount of its FE logs to the
        # owner of the directory, which prepare_environment() created as the learner. With Docker
        # Engine on Linux, they would otherwise stay root's, and the learner could not delete
        # .runtime/ without sudo; Docker Desktop already shows them as the learner's. --reference,
        # rather than the learner's uid, also leaves them alone with rootless Docker, where the
        # directory is root's inside the container. The Doris image is there whenever Doris ran.
        script = f"""set -euo pipefail

echo "[1/7] Remove the OpenTelemetry demo"
docker compose -p {env.DEMO_PROJECT} down --volumes

echo "[2/7] Remove Litefuse"
docker compose -p {env.LITEFUSE_PROJECT} down{volumes}

echo "[3/7] Remove the local model of Module 7's optional lab"
docker compose -p {env.LOCAL_MODEL_PROJECT} down{volumes}

echo "[4/7] Remove the Module 2 collectors and the Module 8 CPU load"
for name in {containers}; do
  if docker container inspect "$name" >/dev/null 2>&1; then
    # Stop first, so that the log collector saves its read position.
    docker stop -t 5 "$name" >/dev/null 2>&1 || true
    docker rm -f "$name" >/dev/null 2>&1 || true
    echo "$name"
  fi
done

echo "[5/7] Remove the DOG core services"
docker compose -p {env.PROJECT} down{volumes}

echo "[6/7] Give the Doris logs in {logs}/ to your user, so that you can delete them"
# Doris writes them as root; on Linux, they would stay root's files on this computer.
if [ -d {logs} ] && docker image inspect {env.DORIS_IMAGE} >/dev/null 2>&1; then
  docker run --rm --entrypoint chown -v "$(pwd -P)/{logs}:/logs" {env.DORIS_IMAGE} -R --reference=/logs /logs
fi

{forget}
"""
        self.shell(script, title="Remove the observability environment")
        self.connection = None
        kept = ("The volumes of Doris, Grafana, Litefuse, and the local model were kept, and so were the "
                "Module 2 log collector's read position and the demo's feature flags." if keep_data
                else "Their volumes were removed too, and so was the Module 2 log collector's read position; "
                "the demo's feature flags are off again.")
        card(
            f"Removed the course containers and networks. {kept} The upstream checkout and the "
            f"Doris logs stay in {self.RUNTIME_DIRECTORY}/; delete that directory if you no longer need them.",
            "ok",
            "Environment removed",
        )

    def show_containers(self) -> None:
        """Display the containers of this course: the DOG stack, the collectors, the demo, Litefuse, and the model."""
        self.shell(
            f'docker ps -a --filter name={env.PROJECT} '
            '--format "table {{.Names}}\\t{{.Image}}\\t{{.Status}}\\t{{.Ports}}"',
            title="Course containers",
        )


DorisLab = ObservabilityLab

__all__ = [
    "DorisLab",
    "ObservabilityLab",
    "card",
    "connect_doris",
    "container_inspect",
    "docker_exists",
    "docker_preflight",
    "install_styles",
    "run",
    "show_frame",
    "show_log",
    "show_sql",
    "sql",
    "wait_for_health",
    "wait_for_port",
]
