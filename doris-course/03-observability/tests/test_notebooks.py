"""Offline checks of the committed notebooks and of the data checks that the Labs rely on."""

import json
import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
LAB1 = ROOT / "level1/module01-observability-introduction/lab01_observability_introduction.ipynb"
LAB2 = ROOT / "level1/module02-data-ingest/lab02_ingest_observability_data.ipynb"
LAB4 = ROOT / "level2/module04-table-model/lab04_table_models.ipynb"
LAB6 = ROOT / "level2/module06-property-mv-index/lab06_properties_mv_index.ipynb"
LAB7 = ROOT / "level2/module07-data-analysis-litefuse/lab07_data_analysis_litefuse.ipynb"
# The tables that the Doris exporter creates when a collector starts.
EXPORTER_TABLES = {
    "otel_logs", "otel_traces", "otel_traces_graph", "otel_metrics_gauge", "otel_metrics_sum",
    "otel_metrics_histogram", "otel_metrics_summary", "otel_metrics_exponential_histogram",
}


def code_cells(path):
    return ["".join(cell["source"]) for cell in json.loads(path.read_text())["cells"] if cell["cell_type"] == "code"]


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
        for path, table in ((LAB4, "FROM otel_logs"), (LAB6, "FROM otel_logs"), (LAB7, "FROM otel_traces")):
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

    def test_span_durations_are_converted_from_microseconds(self):
        # The Doris exporter stores duration in microseconds (end_time minus timestamp).
        text = "\n".join(code_cells(LAB7))
        self.assertNotIn("1000000", text)
        self.assertIn("duration / 1000.0", text)


if __name__ == "__main__":
    unittest.main()
