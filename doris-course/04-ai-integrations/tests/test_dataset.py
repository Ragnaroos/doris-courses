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


TICKETS_SPEC = yaml.safe_load((DATASETS / "support_tickets.yaml").read_text())
LESSON_2 = ROOT / "level1/module02-doris-ai-functions/course.md"
LAB_2 = ROOT / "level1/module02-doris-ai-functions/lab02_doris_ai_functions.ipynb"


class SupportTicketTests(unittest.TestCase):
    """Module 2's tickets agree with their description and with what the lesson and the Lab say about them."""

    @classmethod
    def setUpClass(cls):
        with (DATASETS / TICKETS_SPEC["file"]).open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            cls.columns, cls.rows = reader.fieldnames, list(reader)
        cls.by_id = {int(row["ticket_id"]): row for row in cls.rows}

    def test_columns_are_the_described_ones(self):
        self.assertEqual(self.columns, [column["name"] for column in TICKETS_SPEC["columns"]])

    def test_numbers_in_the_description_match_the_file(self):
        self.assertEqual(len(self.rows), TICKETS_SPEC["row_count"])
        self.assertEqual(len(self.by_id), len(self.rows), "ticket ids must be unique")
        self.assertEqual((min(self.by_id), max(self.by_id)),
                         (TICKETS_SPEC["first_ticket"], TICKETS_SPEC["last_ticket"]))
        self.assertEqual(dict(Counter(row["language"] for row in self.rows)), TICKETS_SPEC["languages"])
        self.assertEqual(dict(Counter(row["expected_topic"] for row in self.rows)), TICKETS_SPEC["topic_counts"])
        self.assertEqual(dict(Counter(row["expected_sentiment"] for row in self.rows)),
                         TICKETS_SPEC["sentiment_counts"])

    def test_labels_are_the_ones_the_lab_offers(self):
        self.assertEqual(set(TICKETS_SPEC["topic_counts"]), set(TICKETS_SPEC["topics"]))
        self.assertEqual(set(TICKETS_SPEC["sentiment_counts"]), set(TICKETS_SPEC["sentiments"]))
        labels = "[" + ", ".join(f"'{topic}'" for topic in TICKETS_SPEC["topics"]) + "]"
        lab = "\n".join("".join(cell["source"]) for cell in json.loads(LAB_2.read_text())["cells"])
        self.assertIn(labels, lab)
        self.assertIn("IN (" + ", ".join(f"'{topic}'" for topic in TICKETS_SPEC["topics"]) + ")", lab)
        self.assertIn("IN (" + ", ".join(f"'{label}'" for label in TICKETS_SPEC["sentiments"]) + ")", lab)

    def test_addresses_in_the_tickets_are_reserved_for_examples(self):
        for row in self.rows:
            for address in re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", row["raw_text"]):
                with self.subTest(ticket=row["ticket_id"]):
                    self.assertTrue(address.endswith("@example.com"), address)

    def test_the_lesson_quotes_the_tickets(self):
        lesson = LESSON_2.read_text()
        for ticket in (1009, 1010, 1011):
            with self.subTest(ticket=ticket):
                self.assertIn(f"| {ticket} | {self.by_id[ticket]['raw_text']} |", lesson)

    def test_the_lab_extracts_order_numbers_that_are_in_the_text(self):
        # Section 7 relies on 1002 and 1012 naming an order and 1011 naming none.
        order = re.compile(r"\bA-\d{4}\b")
        self.assertEqual(order.findall(self.by_id[1002]["raw_text"]), ["A-3017"])
        self.assertEqual(order.findall(self.by_id[1012]["raw_text"]), ["A-2048"])
        self.assertEqual(order.findall(self.by_id[1011]["raw_text"]), [])


if __name__ == "__main__":
    unittest.main()
