"""Offline checks of the committed notebooks and of the data checks that the Labs rely on."""

import json
import re
import unittest
from pathlib import Path

import yaml

from doris_course import environment

ROOT = Path(__file__).resolve().parents[1]
LAB1 = ROOT / "level1/module01-observability-introduction/lab01_observability_introduction.ipynb"
LAB2 = ROOT / "level1/module02-data-ingest/lab02_ingest_observability_data.ipynb"
LAB4 = ROOT / "level2/module04-table-model/lab04_table_models.ipynb"
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

    def test_level2_labs_check_their_data_before_using_it(self):
        for path, table in ((LAB4, "FROM otel_logs"), (LAB6, "FROM otel_logs"), (LAB7, "FROM otel_traces"),
                            (LAB8, "FROM otel_metrics_gauge")):
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
        self.assertIn("AGGREGATE KEY(log_date, service_name)", text)
        self.assertRegex(text, r"log_date\s+DATE,")
        self.assertRegex(text, r"error_count\s+BIGINT SUM")
        self.assertIn("UNIQUE KEY(alarm_date, alarm_hash)", text)
        # REPLACE value columns would keep one arbitrary error message per key.
        self.assertNotIn("REPLACE", text.replace("REGEXP_REPLACE", ""))

    def test_module4_cells_can_be_rerun(self):
        cells = code_cells(LAB4)
        text = "\n".join(cells)
        tables = re.findall(r"CREATE TABLE (IF NOT EXISTS )?(\w+)", text)
        self.assertEqual({table for _, table in tables}, {"daily_log_counts", "error_alerts"})
        for if_not_exists, table in tables:
            with self.subTest(table=table):
                self.assertTrue(if_not_exists)
        # SUM adds every load again, so a cell that loads the counts empties the table first.
        for cell in cells:
            if "INSERT INTO daily_log_counts" in cell:
                self.assertLess(cell.index("TRUNCATE TABLE daily_log_counts"), cell.index("INSERT INTO daily_log_counts"))
        # Dates and partition names in the statements go stale.
        self.assertNotRegex(text, r"20\d\d-\d\d-\d\d|PARTITION p\d{8}")

    def test_labs_show_only_tables_that_exist(self):
        # A Lab may look at the exporter's tables and at the tables that it or an earlier Lab creates.
        created = set(EXPORTER_TABLES)
        for path in sorted(ROOT.glob("level*/module*/lab*.ipynb")):
            text = "\n".join(code_cells(path))
            created.update(re.findall(r"(?<!SHOW )CREATE TABLE (?:IF NOT EXISTS )?`?(\w+)", text))
            for table in re.findall(r"SHOW (?:CREATE TABLE|PARTITIONS FROM) `?(\w+)", text):
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
        quiz = yaml.safe_load(QUIZ8.read_text())
        self.assertIn("above 90% continuously for 10 minutes", quiz["questions"][1]["prompt"])
        # Every cell that reads the rule uses the name that the Lab tells the learner to give it.
        self.assertIn("**1. Enter alert rule name**: `Host CPU busy`", text)
        for cell in code_cells(LAB8):
            for name in re.findall(r'lab\.(?:alert_instances|wait_for_alert_state|export_alert_rule)\(\s*"([^"]+)"', cell):
                self.assertEqual(name, "Host CPU busy")

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

    def test_span_durations_are_converted_from_microseconds(self):
        # The Doris exporter stores duration in microseconds (end_time minus timestamp).
        text = "\n".join(code_cells(LAB7))
        self.assertNotIn("1000000", text)
        self.assertIn("duration / 1000.0", text)


if __name__ == "__main__":
    unittest.main()
