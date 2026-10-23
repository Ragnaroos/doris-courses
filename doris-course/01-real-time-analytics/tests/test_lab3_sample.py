"""Offline checks that Lab 3's two load paths use one set of sample values."""

import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import yaml

from doris_course import DorisLab
import doris_course.doris_client as client


ROOT = Path(__file__).resolve().parents[1]
EXPECTED = yaml.safe_load((ROOT / "datasets/expected_results.yaml").read_text(encoding="utf-8"))
SAMPLE = EXPECTED["lab3_sample"]
LAB3 = ROOT / "level1/module03-loading-data/lab03_load_data.ipynb"


def sample_rows():
    """Return 1,024 CSV rows with the sample's IDs, time range, and revenue."""
    rows = []
    for index in range(SAMPLE["rows"]):
        event_id = 10027072 if index == SAMPLE["rows"] - 1 else index + 1
        event_time = SAMPLE["max_event_time"] if index == 5 else SAMPLE["min_event_time"]
        revenue = SAMPLE["total_revenue"] if index == 7 else "0.00"
        rows.append([event_time, str(event_id), "1", "view", "region_01", "2", revenue])
    return rows


def write_csv(directory, rows):
    path = Path(directory) / "stream_events.csv"
    path.write_text("\n".join("|".join(row) for row in rows) + "\n", encoding="utf-8")
    return path


class SampleConstantTests(unittest.TestCase):
    def test_baseline_constants_match_the_dataset_file(self):
        events = EXPECTED["events"]
        self.assertEqual(events["row_count"], DorisLab.EXPECTED_ROW_COUNT)
        self.assertEqual(events["distinct_users"], DorisLab.EXPECTED_DISTINCT_USERS)
        self.assertEqual(events["distinct_products"], DorisLab.EXPECTED_DISTINCT_PRODUCTS)
        self.assertEqual(Decimal(events["total_revenue"]), DorisLab.EXPECTED_TOTAL_REVENUE)
        self.assertEqual(events["event_counts"], DorisLab.EXPECTED_EVENT_COUNTS)

    def test_the_lab_reads_the_sample_from_the_dataset_file(self):
        self.assertEqual(DorisLab.LAB3_SAMPLE, SAMPLE)

    def test_a_file_with_the_sample_values_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_csv(directory, sample_rows())
            self.assertEqual(DorisLab._validate_fixture(path, "stream_csv"), SAMPLE["rows"])

    def test_a_file_with_another_latest_time_is_rejected(self):
        rows = sample_rows()
        rows[5][0] = "2020-03-03 12:12:47"
        with tempfile.TemporaryDirectory() as directory:
            path = write_csv(directory, rows)
            with self.assertRaisesRegex(ValueError, "latest event time 2020-03-03 12:12:47"):
                DorisLab._validate_fixture(path, "stream_csv")

    def test_a_json_file_with_another_total_is_rejected(self):
        records = [
            {
                "meta": {"occurred_at": row[0].replace(" ", "T"), "event_id": int(row[1])},
                "actor": {"user_id": 1},
                "event": {"type": "VIEW", "revenue": float(row[6])},
                "geo": {"region": "region_01"},
                "product_id": 2,
            }
            for row in sample_rows()
        ]
        records[7]["event"]["revenue"] = 1.0
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "routine_events.jsonl"
            path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "total revenue 1"):
                DorisLab._validate_fixture(path, "routine_json")


class LoadedSampleTests(unittest.TestCase):
    def lab_returning(self, row):
        lab = DorisLab.__new__(DorisLab)
        lab.sql = lambda statement, *, title: pd.DataFrame([row])
        return lab

    def test_matching_rows_show_a_green_check(self):
        lab = self.lab_returning({
            "loaded_rows": 1024, "distinct_events": 1024,
            "min_event_time": SAMPLE["min_event_time"], "max_event_time": SAMPLE["max_event_time"],
            "total_revenue": Decimal(SAMPLE["total_revenue"]),
        })
        with patch.object(client, "card") as card:
            lab.verify_lab3_sample("SELECT ...", title="Committed sample")
        self.assertEqual(card.call_args.args[1], "ok")

    def test_another_latest_time_fails(self):
        lab = self.lab_returning({
            "loaded_rows": 1024, "distinct_events": 1024,
            "min_event_time": SAMPLE["min_event_time"], "max_event_time": "2020-03-03 12:12:47",
            "total_revenue": Decimal(SAMPLE["total_revenue"]),
        })
        with patch.object(client, "card"), self.assertRaisesRegex(AssertionError, "max_event_time"):
            lab.verify_lab3_sample("SELECT ...", title="Committed sample")

    def test_both_load_paths_check_and_describe_the_same_values(self):
        cells = json.loads(LAB3.read_text(encoding="utf-8"))["cells"]
        checks = [
            "".join(cell["source"]) for cell in cells
            if cell["cell_type"] == "code" and "verify_lab3_sample" in "".join(cell["source"])
        ]
        self.assertEqual(len(checks), 2)
        self.assertTrue(any("FROM events_stream" in check for check in checks))
        self.assertTrue(any("FROM events_routine" in check for check in checks))
        by_id = {cell.get("id"): "".join(cell["source"]) for cell in cells}
        for result_id in ("e6460ae7", "680e9e58"):  # Stream Load and Routine Load results
            for value in (SAMPLE["min_event_time"], SAMPLE["max_event_time"]):
                self.assertIn(value, by_id[result_id])
        self.assertIn("23299.84", by_id["e6460ae7"])
        self.assertIn("23,299.84", by_id["680e9e58"])
        self.assertNotIn("2020-03-03 12:12:47", "\n".join(by_id.values()))


if __name__ == "__main__":
    unittest.main()
