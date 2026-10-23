"""Offline checks that the course data, its description, and the lesson agree."""

import csv
import hashlib
import importlib.util
import json
import re
import unittest
from collections import Counter
from decimal import Decimal
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DATASETS = ROOT / "datasets"
SPEC = yaml.safe_load((DATASETS / "events.yaml").read_text())
CSV_PATH = DATASETS / SPEC["file"]
LESSON = ROOT / "level1/module01-doris-mcp/course.md"
LAB = ROOT / "level1/module01-doris-mcp/lab01_connect_agent_to_doris.ipynb"


def read_rows():
    with CSV_PATH.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames, list(reader)


def weekly_activity(rows, start, end):
    counts, users = Counter(), {}
    for row in rows:
        if start <= row["event_time"] < end:
            counts[row["event_type"]] += 1
            users.setdefault(row["event_type"], set()).add(row["user_id"])
    ordered = sorted(counts, key=lambda kind: -counts[kind])
    return [{"event_type": kind, "event_count": counts[kind], "distinct_users": len(users[kind])}
            for kind in ordered]


def normalized_sql(text):
    return re.sub(r"\s+", " ", text.replace("ai_course.events", "events")).strip().rstrip(";").strip()


class DatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.columns, cls.rows = read_rows()

    def test_file_is_the_described_one(self):
        self.assertEqual(hashlib.sha256(CSV_PATH.read_bytes()).hexdigest(), SPEC["sha256"])
        self.assertEqual(self.columns, [column["name"] for column in SPEC["columns"]])

    def test_numbers_in_the_description_match_the_file(self):
        rows = self.rows
        self.assertEqual(len(rows), SPEC["row_count"])
        self.assertEqual(min(row["event_time"] for row in rows), SPEC["min_event_time"])
        self.assertEqual(max(row["event_time"] for row in rows), SPEC["max_event_time"])
        self.assertEqual(len({row["user_id"] for row in rows}), SPEC["distinct_users"])
        self.assertEqual(len({row["product_id"] for row in rows}), SPEC["distinct_products"])
        self.assertEqual(str(sum(Decimal(row["revenue"]) for row in rows)), SPEC["total_revenue"])
        self.assertEqual(dict(Counter(row["event_type"] for row in rows)), SPEC["event_counts"])
        self.assertEqual(sorted(int(row["event_id"]) for row in rows), list(range(1, len(rows) + 1)))

    def test_only_purchases_carry_revenue(self):
        for row in self.rows:
            if row["event_type"] != "purchase":
                self.assertEqual(row["revenue"], "0.00")
            else:
                self.assertGreater(Decimal(row["revenue"]), 0)

    def test_weekly_activity_matches_the_file(self):
        week = SPEC["weekly_activity"]
        self.assertEqual(weekly_activity(self.rows, week["start"], week["end"]), week["rows"])

    def test_generator_reproduces_the_file(self):
        spec = importlib.util.spec_from_file_location("generate_events", DATASETS / "generate_events.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        generated = [[str(value) for value in row] for row in module.generate()]
        self.assertEqual(generated, [[row[name] for name in self.columns] for row in self.rows])

    def test_lesson_and_lab_show_the_weekly_rows(self):
        expected = SPEC["weekly_activity"]["rows"]
        for path, text in ((LESSON, LESSON.read_text()),
                           (LAB, "\n".join("".join(cell["source"]) for cell in json.loads(LAB.read_text())["cells"]))):
            for row in expected:
                with self.subTest(file=path.name, event_type=row["event_type"]):
                    pattern = (rf"\|\s*`{row['event_type']}`\s*\|\s*{row['event_count']:,}\s*\|"
                               rf"\s*{row['distinct_users']:,}\s*\|")
                    plain = pattern.replace(",", ",?")
                    self.assertRegex(text, plain)

    def test_lesson_and_lab_use_the_same_sql(self):
        lesson_blocks = re.findall(r"```sql\n(.*?)```", LESSON.read_text(), re.S)
        lab_cells = ["".join(cell["source"]) for cell in json.loads(LAB.read_text())["cells"]]
        lab_sql = next(re.search(r'WEEKLY_ACTIVITY_SQL = """(.*?)"""', cell, re.S).group(1)
                       for cell in lab_cells if "WEEKLY_ACTIVITY_SQL = " in cell)
        weekly = [block for block in lesson_blocks if "COUNT(DISTINCT user_id)" in block]
        self.assertTrue(weekly, "the lesson shows the weekly SQL")
        for block in weekly:
            self.assertEqual(normalized_sql(block), normalized_sql(lab_sql))


if __name__ == "__main__":
    unittest.main()
