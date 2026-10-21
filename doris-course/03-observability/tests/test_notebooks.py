"""Offline checks of the committed notebooks and of the data checks that the Labs rely on."""

import ast
import json
import re
import unittest
from pathlib import Path

import yaml

from doris_course import environment

ROOT = Path(__file__).resolve().parents[1]
LAB1 = ROOT / "level1/module01-observability-introduction/lab01_observability_introduction.ipynb"
LAB2 = ROOT / "level1/module02-data-ingest/lab02_ingest_observability_data.ipynb"
LAB3 = ROOT / "level1/module03-data-visualization/lab03_data_visualization.ipynb"
LEVEL1_LABS = (LAB1, LAB2, LAB3)
# A failed order: the checkout span of the order has an error status.
FAILED_ORDER = ("service_name = 'checkout'", "span_name = 'oteldemo.CheckoutService/PlaceOrder'",
                "status_code = 'STATUS_CODE_ERROR'")
LAB4 = ROOT / "level2/module04-table-model/lab04_table_models.ipynb"
LAB5 = ROOT / "level2/module05-partition-bucket/lab05_partition_and_bucket.ipynb"
LAB6 = ROOT / "level2/module06-property-mv-index/lab06_properties_mv_index.ipynb"
LAB7 = ROOT / "level2/module07-data-analysis-litefuse/lab07_data_analysis_litefuse.ipynb"
OPTIONAL7 = ROOT / "level2/module07-data-analysis-litefuse/optional07_trace_a_real_model.ipynb"
LAB8 = ROOT / "level2/module08-alerting/lab08_alerting.ipynb"
QUIZ8 = ROOT / "level2/module08-alerting/quiz08_alerting_rules.yaml"
# The tables that the Doris exporter creates when a collector starts.
EXPORTER_TABLES = {
    "otel_logs", "otel_traces", "otel_traces_graph", "otel_metrics_gauge", "otel_metrics_sum",
    "otel_metrics_histogram", "otel_metrics_summary", "otel_metrics_exponential_histogram",
}


def code_cells(path):
    return ["".join(cell["source"]) for cell in json.loads(path.read_text())["cells"] if cell["cell_type"] == "code"]


def markdown_text(path):
    return "\n".join("".join(cell["source"]) for cell in json.loads(path.read_text())["cells"]
                     if cell["cell_type"] == "markdown")


class NotebookTests(unittest.TestCase):
    def test_notebooks_are_committed_without_outputs(self):
        for path in sorted(ROOT.glob("level*/module*/*.ipynb")):
            for index, cell in enumerate(json.loads(path.read_text())["cells"]):
                if cell["cell_type"] == "code":
                    with self.subTest(notebook=path.name, cell=index):
                        self.assertEqual(cell["outputs"], [])
                        self.assertIsNone(cell["execution_count"])

    def test_cells_do_not_show_a_helper_result_twice(self):
        # The helpers show their own result; Jupyter would show the returned DataFrame or
        # CompletedProcess again unless the cell ends with a semicolon (OB-18).
        helpers = {"sql", "execute", "wait_for_rows", "profile_query", "scan_filters", "explain_scan", "tablet_rows",
                   "show_create_table", "shell", "alert_instances", "wait_for_alert_state", "wait_for_email",
                   "export_alert_rule", "provision_alert_rule_group", "grafana_dashboard", "wait_for_feature_flag",
                   "litefuse_trace"}
        for path in sorted(ROOT.glob("level*/module*/*.ipynb")):
            for source in code_cells(path):
                body = ast.parse(source).body
                last = body[-1] if body else None
                if not (isinstance(last, ast.Expr) and isinstance(last.value, ast.Call)
                        and isinstance(last.value.func, ast.Attribute) and last.value.func.attr in helpers):
                    continue
                with self.subTest(notebook=path.name, call=last.value.func.attr):
                    self.assertTrue(source.rstrip().endswith(";"), source.rstrip().splitlines()[-1])

    def test_module1_checks_the_demo_telemetry_in_doris(self):
        cells = code_cells(LAB1)
        start = next(index for index, cell in enumerate(cells) if "lab.start_demo()" in cell)
        check = cells[start + 1]
        self.assertIn("lab.wait_for_rows(", check)
        for table in ("FROM otel_traces", "FROM otel_logs", "FROM otel_metrics_"):
            self.assertIn(table, check)
        # The exporter stores UTC; one row per signal that has recent rows.
        self.assertIn("UTC_TIMESTAMP()", check)
        self.assertIn("min_rows=3", check)

    def test_module1_starts_the_incident_and_waits_for_a_failed_order(self):
        cells = code_cells(LAB1)
        flag = next(index for index, cell in enumerate(cells) if "lab.wait_for_feature_flag(" in cell)
        # The flag of the course's incident, at the value that the later modules expect.
        self.assertIn('lab.wait_for_feature_flag("paymentFailure", "50%")', cells[flag])
        self.assertIn("http://127.0.0.1:28082/feature", markdown_text(LAB1))
        orders = next(index for index, cell in enumerate(cells) if "first_failure = lab.wait_for_rows(" in cell)
        self.assertLess(flag, orders)
        for condition in FAILED_ORDER:
            self.assertIn(condition, cells[orders])
        # The load generator places one or two orders a minute: the first failure can take minutes
        # (107 seconds after the flag in a clean run).
        self.assertIn("timeout_seconds=600", cells[orders])

    def test_module2_follows_one_failed_order_through_the_three_tables(self):
        cells = code_cells(LAB2)
        order = next(index for index, cell in enumerate(cells) if "failed_order = lab.wait_for_rows(" in cell)
        for condition in FAILED_ORDER:
            self.assertIn(condition, cells[order])
        self.assertIn('failed_trace = failed_order["trace_id"][0]', cells[order])
        for table in ("FROM otel_traces", "FROM otel_logs"):
            lookup = next(cell for cell in cells[order + 1:] if table in cell)
            self.assertIn("WHERE trace_id = '{failed_trace}'", lookup)
        metric = next(cell for cell in cells[order + 1:] if "FROM otel_metrics_sum" in cell)
        self.assertIn("metric_name = 'traces.span.metrics.calls'", metric)

    def test_exercises_have_a_collapsed_reference_solution(self):
        for path in sorted(ROOT.glob("level*/module*/lab*.ipynb")):
            cells = json.loads(path.read_text())["cells"]
            blank = [index for index, cell in enumerate(cells)
                     if cell["cell_type"] == "code" and "".join(cell["source"]).strip() == "# Your code here"]
            with self.subTest(notebook=path.name):
                self.assertEqual(len(blank), 1)
                solution = next(cell for cell in cells[blank[0] + 1:] if cell["cell_type"] == "code")
                self.assertIs(solution["metadata"]["jupyter"]["source_hidden"], True)
                self.assertEqual(solution["metadata"]["tags"], ["reference-solution"])

    def test_module3_searches_the_time_range_in_utc(self):
        cells = code_cells(LAB3)
        window = next(cell for cell in cells if "TIME_FROM = " in cell)
        # Doris stores UTC; the Doris App compares its range in the browser's time zone.
        self.assertIn("datetime.now(timezone.utc)", window)
        text = markdown_text(LAB3)
        self.assertIn("**Absolute time range**", text)
        self.assertIn("Unless your computer uses UTC", text)
        # Every check of a Discover search uses the range that the learner typed into Discover.
        for cell in cells:
            if "FROM otel_logs" in cell and "MATCH_PHRASE" in cell or "severity_number >= 17" in cell:
                self.assertIn("timestamp >= '{TIME_FROM}' AND timestamp < '{TIME_TO}'", cell)

    def test_module3_finds_every_failed_checkout_in_the_access_log(self):
        text = markdown_text(LAB3)
        # The storefront page sends /api/checkout?currencyCode=..., which one long phrase would miss.
        self.assertIn('body:"POST /api/checkout" AND body:"HTTP/1.1 500"', text)
        self.assertIn("body MATCH_PHRASE 'POST /api/checkout' AND body MATCH_PHRASE 'HTTP/1.1 500'", text)
        for cell in code_cells(LAB3):
            if "MATCH_PHRASE" in cell:
                self.assertIn("MATCH_PHRASE 'POST /api/checkout'\n", cell)
                self.assertIn("MATCH_PHRASE 'HTTP/1.1 500'", cell)
        self.assertNotIn("MATCH_PHRASE 'POST /api/checkout HTTP/1.1 500'", "\n".join(code_cells(LAB3)))

    def test_module3_measures_host_cpu_as_module8_does(self):
        query = next(cell for cell in code_cells(LAB3) if "system.cpu.utilization" in cell)
        for condition in ("attributes['state'] = 'idle'", "(1 - AVG(value)) * 100",
                          "scope_name LIKE '%hostmetricsreceiver%'", "resource_attributes['host.name'] IS NOT NULL"):
            self.assertIn(condition, query)
        # The dashboard panel uses the same conditions.
        text = markdown_text(LAB3)
        for condition in ("attributes['state'] = 'idle'", "(1 - AVG(value)) * 100", "IS NOT NULL"):
            self.assertIn(condition, text)
        # hostmetrics measures the Docker host, not a Doris node.
        for path in sorted(ROOT.glob("level1/module*/*")):
            if path.suffix in {".ipynb", ".yaml", ".md"}:
                with self.subTest(file=path.name):
                    self.assertNotIn("Doris node CPU", path.read_text())

    def test_module3_reads_back_the_dashboard_that_the_learner_saves(self):
        text = markdown_text(LAB3)
        self.assertIn("set **Title** to `Payment incident`", text)
        check = next(cell for cell in code_cells(LAB3) if "lab.grafana_dashboard(" in cell)
        self.assertIn('lab.grafana_dashboard("Payment incident")', check)
        for macro in ("$__timeFilter(timestamp)", "$__timeGroupAlias(timestamp, 1m)"):
            self.assertEqual(text.count(macro), 3, macro)

    def test_analysis_labs_check_their_data_before_using_it(self):
        for path, table in ((LAB3, "FROM otel_traces"), (LAB4, "FROM otel_traces"), (LAB5, "FROM otel_traces"), (LAB6, "FROM otel_logs"),
                            (LAB7, "FROM otel_traces"), (LAB8, "FROM otel_metrics_gauge")):
            cells = code_cells(path)
            with self.subTest(notebook=path.name):
                self.assertIn("lab = DorisLab(", cells[0])
                self.assertIn("lab.wait_for_rows(", cells[1])
                self.assertIn(table, cells[1])

    def test_fe_log_rows_name_their_service(self):
        config = yaml.safe_load((LAB2.parent / "otel_for_logs.yaml").read_text())
        self.assertIn("resource", config["service"]["pipelines"]["logs"]["processors"])
        attributes = {item["key"]: item["value"] for item in config["processors"]["resource"]["attributes"]}
        self.assertEqual(attributes, {"service.name": "doris-fe"})
        check = next(cell for cell in code_cells(LAB2) if "log.file.name" in cell)
        self.assertIn("service_name", check)

    def test_ddl_leaves_out_properties_that_doris_4_1_rejects(self):
        # Copied from SHOW CREATE TABLE on Doris 4.0; Doris 4.1.3 rejects it as an unknown property.
        for path in sorted(ROOT.glob("level*/module*/lab*.ipynb")):
            with self.subTest(notebook=path.name):
                self.assertNotIn("enable_single_replica_compaction", "\n".join(code_cells(path)))

    def test_module4_keys_are_the_reporting_grain(self):
        text = "\n".join(code_cells(LAB4))
        # A datetime(6) key would merge only the rows of the same microsecond.
        self.assertIn("AGGREGATE KEY(request_minute, service_name)", text)
        self.assertRegex(text, r"request_minute\s+DATETIME,")
        self.assertRegex(text, r"failed_requests\s+BIGINT SUM")
        self.assertIn("UNIQUE KEY(alert_date, alert_hash)", text)
        # REPLACE value columns would keep one arbitrary error message per key.
        self.assertNotIn("REPLACE", text.replace("REGEXP_REPLACE", ""))

    def test_module4_counts_each_request_in_the_minute_in_which_it_ended(self):
        # A span reaches Doris when it ends; a flag stream that started minutes earlier would be missed.
        load = next(cell for cell in code_cells(LAB4) if "INSERT INTO requests_per_minute" in cell)
        self.assertIn("SELECT DATE_TRUNC(end_time, 'minute'), service_name", load)
        self.assertIn("span_kind = 'SPAN_KIND_SERVER'", load)
        self.assertIn("MAX(end_time) - INTERVAL 60 SECOND AS second_batch_start", load)
        self.assertNotIn("timestamp <", load)
        # The alerts come from error spans: the incident leaves no error logs.
        alerts = next(cell for cell in code_cells(LAB4) if "INSERT INTO error_alerts" in cell)
        self.assertIn("FROM otel_traces", alerts)
        self.assertIn("status_code = 'STATUS_CODE_ERROR'", alerts)

    def test_module4_cells_can_be_rerun(self):
        cells = code_cells(LAB4)
        text = "\n".join(cells)
        tables = re.findall(r"CREATE TABLE (IF NOT EXISTS )?(\w+)", text)
        self.assertEqual({table for _, table in tables}, {"requests_per_minute", "error_alerts", "daily_log_counts"})
        for if_not_exists, table in tables:
            with self.subTest(table=table):
                self.assertTrue(if_not_exists)
        # SUM adds every load again, so a cell that loads the counts empties the table first.
        for table in ("requests_per_minute", "daily_log_counts"):
            loads = [cell for cell in cells if f"INSERT INTO {table}" in cell]
            self.assertTrue(loads, table)
            for cell in loads:
                self.assertLess(cell.index(f"TRUNCATE TABLE {table}"), cell.index(f"INSERT INTO {table}"))
        # Dates and partition names in the statements go stale.
        self.assertNotRegex(text, r"20\d\d-\d\d-\d\d|PARTITION p\d{8}")

    def test_module5_reads_the_plan_of_the_incident_window(self):
        cells = code_cells(LAB5)
        text = "\n".join(cells)
        # The window starts at the first failed order, and the query filters on the partition column.
        self.assertIn('INCIDENT_START = str(incident["first_failed_order"][0])', text)
        self.assertIn("AND timestamp >= '{start}'", text)
        for table in ("otel_traces", "spans_by_service"):
            self.assertIn(f'lab.explain_scan(INCIDENT_QUERY.format(table="{table}", start=INCIDENT_START)', text)
            self.assertIn(f'lab.tablet_rows("{table}")', text)
        # The copy is bucketed by the service that the incident query filters on, and partitioned by its data.
        copy = next(cell for cell in cells if "CREATE TABLE IF NOT EXISTS spans_by_service" in cell)
        self.assertIn("DISTRIBUTED BY HASH(service_name) BUCKETS 10", copy)
        self.assertIn("AUTO PARTITION BY RANGE (date_trunc(timestamp, 'day'))", copy)
        self.assertIn('"partition.retention_count" = "7"', copy)
        # Doris folds UTC_TIMESTAMP() when it plans, but not UTC_DATE(): a filter on it prunes nothing.
        self.assertNotIn("UTC_DATE()", text)

    def test_module5_cells_can_be_rerun(self):
        cells = code_cells(LAB5)
        text = "\n".join(cells)
        tables = re.findall(r"CREATE TABLE (IF NOT EXISTS )?(\w+)", text)
        self.assertEqual({table for _, table in tables}, {"spans_by_service", "spans_by_trace"})
        for if_not_exists, table in tables:
            self.assertTrue(if_not_exists, table)
            load = next(cell for cell in cells if f"INSERT INTO {table}" in cell)
            self.assertLess(load.index(f"TRUNCATE TABLE {table}"), load.index(f"INSERT INTO {table}"))
        # Dates and partition names go stale; the old hourly and monthly tables wrote down 242 partitions.
        self.assertNotRegex(text, r"20\d\d-\d\d-\d\d|PARTITION p\d{8}|history_partition_num")

    def test_labs_show_only_tables_that_exist(self):
        # A Lab may look at the exporter's tables and at the tables that it or an earlier Lab creates.
        created = set(EXPORTER_TABLES)
        for path in sorted(ROOT.glob("level*/module*/lab*.ipynb")):
            text = "\n".join(code_cells(path))
            created.update(re.findall(r"(?<!SHOW )CREATE TABLE (?:IF NOT EXISTS )?`?(\w+)", text))
            shown = re.findall(r"SHOW (?:CREATE TABLE|PARTITIONS FROM) `?(\w+)", text)
            shown += re.findall(r'lab\.(?:show_create_table|tablet_rows)\("(\w+)"', text)
            for table in shown:
                with self.subTest(notebook=path.name, table=table):
                    self.assertIn(table, created)

    def test_no_lab_writes_down_a_profile_id(self):
        # A Profile ID names one query on one FE; anywhere else, Doris answers "query id ... not found".
        for path in sorted(ROOT.glob("level*/module*/lab*.ipynb")):
            with self.subTest(notebook=path.name):
                self.assertNotRegex("\n".join(code_cells(path)), r"[0-9a-f]{16}-[0-9a-f]{16}")

    def test_module6_measures_the_index_in_the_profile_of_its_own_query(self):
        cells = code_cells(LAB6)
        settings = next(index for index, cell in enumerate(cells) if "SET enable_profile = true" in cell)
        query = next(index for index, cell in enumerate(cells) if "profile = lab.profile_query(INDEX_QUERY" in cell)
        self.assertLess(settings, query)
        # Without these, a repeated query can be answered from a cache, and its profile shows no or less scanning.
        for setting in ("profile_level = 2", "enable_sql_cache = false", "enable_condition_cache = false"):
            self.assertIn(setting, cells[settings])
        self.assertRegex(cells[query + 1], r'assert with_index\["RowsInvertedIndexFiltered"\] > 0')
        # The comparison turns the index off for the session, and on again even when a step fails.
        comparison = next(cell for cell in cells if "enable_inverted_index_query = false" in cell)
        self.assertLess(comparison.index("finally:"), comparison.index("enable_inverted_index_query = true"))

    def test_module6_measures_the_incident_search_with_and_without_the_index(self):
        query = next(cell for cell in code_cells(LAB6) if "INDEX_QUERY = " in cell)
        # The search of Module 3: two phrases, so that the storefront's ?currencyCode=USD requests match too.
        self.assertIn("body MATCH_PHRASE 'POST /api/checkout'\n", query)
        self.assertIn("body MATCH_PHRASE 'HTTP/1.1 500'", query)
        # A COUNT(*) alone is answered from the index (COUNT_ON_INDEX) and reads no rows.
        self.assertIn("GROUP BY service_name", query)
        # The plans and the screenshots of them are cells now.
        self.assertFalse((LAB6.parent / "images").exists())
        self.assertNotIn("<img", markdown_text(LAB6))

    def test_module6_builds_the_view_before_relying_on_it(self):
        cells = code_cells(LAB6)
        create = next(cell for cell in cells if "CREATE MATERIALIZED VIEW" in cell)
        # Doris 4.1.3 does not skip an existing synchronous view, even with IF NOT EXISTS.
        self.assertNotIn("IF NOT EXISTS server_minutes_mv", create)
        self.assertLess(create.index("DROP MATERIALIZED VIEW IF EXISTS server_minutes_mv ON otel_traces"),
                        create.index("CREATE MATERIALIZED VIEW server_minutes_mv"))
        # The build is a job; the cell waits for this run's job to finish (F-08).
        self.assertIn("State = 'FINISHED' AND CreateTime >= '{created_after}'", create)
        self.assertLess(create.index("CREATE MATERIALIZED VIEW"), create.index("lab.wait_for_rows("))
        # The view's columns cannot take the names of the table's columns.
        view = create.split("CREATE MATERIALIZED VIEW server_minutes_mv AS", 1)[1].split("FROM otel_traces")[0]
        for alias in re.findall(r"\bAS (\w+)", view):
            self.assertTrue(alias.startswith("mv_"), alias)
        later = cells[cells.index(create) + 1:]
        self.assertTrue(any("lab.explain_scan(MINUTES_QUERY" in cell for cell in later))

    def test_module6_compares_compression_on_the_same_rows(self):
        cells = code_cells(LAB6)
        load = next(cell for cell in cells if "logs_{algorithm}" in cell)
        # Two tables that differ only in compression, each loaded once with the same rows.
        self.assertIn('for algorithm in ("zstd", "lz4"):', load)
        self.assertIn('PROPERTIES ("compression" = "{algorithm}")', load)
        self.assertIn("DISTRIBUTED BY RANDOM BUCKETS 1", load)
        self.assertIn("WHERE timestamp < '{copy_limit}'", load)
        self.assertLess(load.index("TRUNCATE TABLE logs_{algorithm}"), load.index("INSERT INTO logs_{algorithm}"))
        # The sizes come from the BEs' reports, which lag: wait until both report every row.
        sizes = next(cell for cell in cells if "DATA_LENGTH" in cell)
        self.assertIn("lab.wait_for_rows(", sizes)
        self.assertIn("TABLE_ROWS = {copied}", sizes)
        self.assertIn("min_rows=2", sizes)
        # ZSTD is the default of Doris 4.x (F-01).
        text = markdown_text(LAB6)
        self.assertIn("ZSTD is the default in Doris 4.x", text)
        self.assertNotRegex(text, r"default compression algorithm,? LZ4")

    def test_module8_alert_query_measures_how_busy_each_host_is(self):
        query = next(cell for cell in code_cells(LAB8) if "HOST_CPU_QUERY = " in cell)
        # A row is the share of time that one core spent in one state: the busy share is 1 - idle.
        self.assertIn("attributes['state'] = 'idle'", query)
        self.assertIn("(1 - AVG(value)) * 100", query)
        # One source per host, and one alert instance per host.
        self.assertIn("scope_name LIKE '%hostmetricsreceiver%'", query)
        self.assertIn("resource_attributes['host.name'] IS NOT NULL", query)
        self.assertIn("GROUP BY host", query)
        # The window ends now: a host that stops reporting leaves the result.
        self.assertIn("timestamp >= UTC_TIMESTAMP() - INTERVAL 1 MINUTE", query)

    def test_module8_rule_uses_the_threshold_of_the_quiz(self):
        text = markdown_text(LAB8)
        self.assertIn("keep **IS ABOVE**, and enter `90`", text)
        self.assertIn("**Pending period**: `1m`", text)
        self.assertIn("such as 10 minutes", text)
        quiz = {question["id"]: question for question in yaml.safe_load(QUIZ8.read_text())["questions"]}
        # The quiz asks about the pending period and the threshold that the Lab sets.
        self.assertIn("a pending period of 1 minute", quiz["predict_pending_states"]["prompt"])
        self.assertIn("1 and compare it with the threshold", quiz["choose_alert_expression"]["options"][3]["text"])
        # Every cell that reads a rule uses the name that the Lab gives it: in the form, or in the rule's JSON.
        self.assertIn("**1. Enter alert rule name**: `Host CPU busy`", text)
        self.assertIn('"title": "Failed orders",', "\n".join(code_cells(LAB8)))
        for cell in code_cells(LAB8):
            for name in re.findall(r'lab\.(?:alert_instances|wait_for_alert_state|export_alert_rule)\(\s*"([^"]+)"', cell):
                self.assertIn(name, ("Host CPU busy", "Failed orders"))

    def test_module8_alerts_on_the_incident_and_ends_it(self):
        cells = code_cells(LAB8)
        rule = next(cell for cell in cells if "FAILED_ORDERS_RULE = {" in cell)
        # A fixed uid, so that a rerun updates the same rule; the policy of section 5 routes it.
        self.assertIn('"uid": "failed-orders"', rule)
        self.assertIn('"labels": {"team": "doris-course", "severity": "critical"}', rule)
        self.assertIn('"evaluator": {"type": "gt", "params": [10]}', rule)
        # No order in the window means no failed order, not an alert.
        self.assertIn('"noDataState": "OK"', rule)
        self.assertIn('lab.provision_alert_rule_group("Doris course", "orders", [FAILED_ORDERS_RULE]', rule)
        self.assertIn('GRAFANA_ADMIN_PASSWORD = "admin"', rule)
        query = next(cell for cell in cells if "FAILED_ORDERS_QUERY = " in cell)
        for condition in ("service_name = 'checkout'", "span_name = 'oteldemo.CheckoutService/PlaceOrder'",
                          "end_time >= UTC_TIMESTAMP() - INTERVAL 5 MINUTE"):
            self.assertIn(condition, query)
        # The incident ends where it started: the flag page, then the alert resolves.
        flag = next(index for index, cell in enumerate(cells) if 'lab.wait_for_feature_flag("paymentFailure", "off")' in cell)
        resolve = next(index for index, cell in enumerate(cells) if '"Failed orders", "Normal"' in cell)
        self.assertLess(cells.index(rule), flag)
        self.assertLess(flag, resolve)
        self.assertIn("after=flag_off", cells[resolve])
        self.assertIn("http://127.0.0.1:28082/feature", markdown_text(LAB8))

    def test_module8_cpu_load_is_low_priority_and_stops_by_itself(self):
        load = next(cell for cell in code_cells(LAB8) if "docker run" in cell)
        self.assertIn(f"--rm --name {environment.CPU_LOAD_CONTAINER} busybox:1.37.0", load)
        self.assertIn("nice -n 19 yes", load)
        self.assertIn("sleep 300", load)
        stop = next(cell for cell in code_cells(LAB8) if "Stop the CPU load" in cell)
        self.assertIn(f"docker rm -f {environment.CPU_LOAD_CONTAINER}", stop)

    def test_module7_traces_an_llm_app_with_the_local_litefuse(self):
        cells = code_cells(LAB7)
        start = next(index for index, cell in enumerate(cells) if "lab.start_litefuse()" in cell)
        app = next(index for index, cell in enumerate(cells) if "from langfuse import" in cell)
        self.assertLess(start, app)
        # The SDK sends to the local Litefuse with the keys that Litefuse creates on its first start.
        self.assertIn(f'os.environ["LANGFUSE_PUBLIC_KEY"] = "{environment.LITEFUSE_PUBLIC_KEY}"', cells[app])
        self.assertIn(f'os.environ["LANGFUSE_SECRET_KEY"] = "{environment.LITEFUSE_SECRET_KEY}"', cells[app])
        self.assertIn('os.environ["LANGFUSE_BASE_URL"] = lab.litefuse_url', cells[app])
        self.assertIn("langfuse.flush()", cells[app])
        # No cloud account, no model API key, and no installs from the notebook.
        text = "\n".join(cells)
        for word in ("litefuse.cloud", "openai", "OPENAI", "%pip", "%env"):
            self.assertNotIn(word, text)
        # Litefuse creates the project's tables with its first trace; a query on a missing table fails at once.
        tables = f"litefuse.spans_{environment.LITEFUSE_PROJECT_ID}"
        wait = next(index for index, cell in enumerate(cells) if "information_schema.tables" in cell)
        first_query = next(index for index, cell in enumerate(cells) if tables in cell)
        self.assertLess(app, wait)
        self.assertLess(wait, first_query)
        self.assertIn("lab.wait_for_rows(", cells[wait])
        self.assertIn(f"LIKE '%{environment.LITEFUSE_PROJECT_ID}'", cells[wait])
        self.assertIn("lab.wait_for_rows(", cells[first_query])
        # The web steps sign in with the user that Litefuse creates, without screenshots of an account.
        markdown = markdown_text(LAB7)
        self.assertIn(f"`{environment.LITEFUSE_USER_EMAIL}`", markdown)
        self.assertIn(f"`{environment.LITEFUSE_USER_PASSWORD}`", markdown)
        self.assertNotIn("litefuse.cloud", markdown)
        self.assertNotIn("<img", markdown)

    def test_module7_optional_lab_traces_a_real_model_without_keys_in_the_notebook(self):
        cells = code_cells(OPTIONAL7)
        text = "\n".join(cells)
        litefuse = next(index for index, cell in enumerate(cells) if "lab.start_litefuse()" in cell)
        model = next(index for index, cell in enumerate(cells) if "lab.start_local_model()" in cell)
        choose = next(index for index, cell in enumerate(cells) if "MODEL_PROVIDER = " in cell)
        app = next(index for index, cell in enumerate(cells) if "from langfuse.openai import OpenAI" in cell)
        self.assertLess(litefuse, app)
        self.assertLess(model, choose)
        self.assertLess(choose, app)
        # The local model is the default, under the name that the server offers it.
        self.assertIn('MODEL_PROVIDER = "local"', cells[choose])
        self.assertIn(f'"{environment.LOCAL_MODEL}"', cells[choose])
        # An OpenAI key comes from the environment through the helper, never from the notebook.
        self.assertIn("lab.openai_api_key()", cells[choose])
        # (Litefuse's own key pair, sk-lf-..., is created by the course and may appear.)
        self.assertNotRegex(text, r"OPENAI_API_KEY\"?\]?\s*=|sk-(?!lf-)[A-Za-z0-9]")
        for word in ("%pip", "%env"):
            self.assertNotIn(word, text)
        # The wrapper records the call; the Lab reports nothing by hand.
        self.assertIn('name="llm-answer"', cells[app])
        self.assertNotIn("update_current_generation", text)
        self.assertIn(f'os.environ["LANGFUSE_PUBLIC_KEY"] = "{environment.LITEFUSE_PUBLIC_KEY}"', cells[app])
        self.assertIn("langfuse.flush()", cells[app])
        wait = next(index for index, cell in enumerate(cells) if "lab.wait_for_rows(" in cell)
        self.assertLess(app, wait)
        # Lab 7 leads to the optional Lab.
        self.assertIn(OPTIONAL7.name, markdown_text(LAB7))

    def test_module7_measures_the_incident_with_sql(self):
        cells = code_cells(LAB7)
        origin = next(cell for cell in cells if "NOT EXISTS" in cell)
        # A service where the failure starts: its server span failed, and none of its own calls did.
        self.assertIn("s.span_kind = 'SPAN_KIND_SERVER'", origin)
        self.assertIn("c.service_name = s.service_name", origin)
        self.assertIn("c.span_kind = 'SPAN_KIND_CLIENT'", origin)
        # The newest orders may still miss spans.
        self.assertIn("end_time < UTC_TIMESTAMP() - INTERVAL 1 MINUTE", origin)
        for condition in FAILED_ORDER:
            self.assertIn(condition, origin)
        window = next(cell for cell in cells if "ROWS BETWEEN 9 PRECEDING AND CURRENT ROW" in cell)
        self.assertIn("ROW_NUMBER() OVER (ORDER BY timestamp)", window)
        red = next(cell for cell in cells if "PERCENTILE_APPROX(duration, 0.99)" in cell)
        self.assertIn("timestamp >= '{INCIDENT_START}'", red)

    def test_span_durations_are_converted_from_microseconds(self):
        # The Doris exporter stores duration in microseconds (end_time minus timestamp).
        text = "\n".join(code_cells(LAB7))
        self.assertNotIn("1000000", text)
        self.assertRegex(text, r"PERCENTILE_APPROX\(duration, 0\.\d+\) / 1000\.0")
        self.assertIn("MAX(duration) / 1000.0", text)


if __name__ == "__main__":
    unittest.main()
