"""Offline checks of the committed notebooks and of the data checks that the Labs rely on."""

import json
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
LAB1 = ROOT / "level1/module01-observability-introduction/lab01_observability_introduction.ipynb"
LAB2 = ROOT / "level1/module02-data-ingest/lab02_ingest_observability_data.ipynb"
LAB6 = ROOT / "level2/module06-property-mv-index/lab06_properties_mv_index.ipynb"
LAB7 = ROOT / "level2/module07-data-analysis-litefuse/lab07_data_analysis_litefuse.ipynb"


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
        for path, table in ((LAB6, "FROM otel_logs"), (LAB7, "FROM otel_traces")):
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

    def test_span_durations_are_converted_from_microseconds(self):
        # The Doris exporter stores duration in microseconds (end_time minus timestamp).
        text = "\n".join(code_cells(LAB7))
        self.assertNotIn("1000000", text)
        self.assertIn("duration / 1000.0", text)


if __name__ == "__main__":
    unittest.main()
