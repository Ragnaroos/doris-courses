"""Offline checks that the reference traces in the lesson match the data and the Server."""

import json
import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
LESSON = ROOT / "level1/module01-doris-mcp/course.md"
SPEC = yaml.safe_load((ROOT / "datasets/events.yaml").read_text())
FIXTURE = json.loads((ROOT / "tests/fixtures/reference_results.json").read_text())


def json_blocks():
    return [json.loads(block) for block in re.findall(r"```json\n(.*?)```", LESSON.read_text(), re.S)]


def result_of(child):
    return next(block for block in json_blocks() if block.get("mode") == "result" and block.get("child_tool") == child)


class LessonTraceTests(unittest.TestCase):
    def test_every_json_block_is_valid(self):
        blocks = re.findall(r"```json\n(.*?)```", LESSON.read_text(), re.S)
        self.assertGreaterEqual(len(blocks), 6)
        for block in blocks:
            json.loads(block)

    def test_table_context_matches_the_dataset(self):
        data = result_of("get_table_context")["data"]["data"]
        columns = data["schema"]["data"]["columns"]
        self.assertEqual([column["column_name"] for column in columns],
                         [column["name"] for column in SPEC["columns"]])
        self.assertEqual([column["comment"] for column in columns],
                         [column["comment"] for column in SPEC["columns"]])
        self.assertEqual([column["data_type"] for column in columns],
                         [column["type"].lower().replace(", ", ",") for column in SPEC["columns"]])
        self.assertEqual(data["comments"]["data"]["table"]["comment"], SPEC["comment"])
        self.assertEqual(data["basic"]["data"]["row_count"], SPEC["row_count"])
        recorded = FIXTURE["doris_catalog.get_table_context"]["data"]["data"]["schema"]["data"]["columns"]
        self.assertEqual(columns, [{key: column[key] for key in ("column_name", "data_type", "is_nullable", "key",
                                                                 "default_value", "comment")}
                                   for column in recorded])

    def test_query_rows_match_the_dataset(self):
        result = result_of("execute_query")
        expected = [{"event_type": row["event_type"], "event_count": row["event_count"],
                     "distinct_users": row["distinct_users"]} for row in SPEC["weekly_activity"]["rows"]]
        self.assertEqual(result["data"]["data"]["rows"], expected)
        recorded = FIXTURE["doris_query.execute_query"]["data"]
        self.assertEqual(result["data"]["metadata"]["limits"], recorded["metadata"]["limits"])

    def test_query_request_sends_the_lesson_sql(self):
        request = next(block for block in json_blocks() if block.get("child_tool") == "execute_query"
                       and "arguments" in block)
        lesson_sql = next(block for block in re.findall(r"```sql\n(.*?)```", LESSON.read_text(), re.S)
                          if "COUNT(DISTINCT user_id)" in block)
        self.assertEqual(request["arguments"]["sql"], lesson_sql.strip().rstrip(";"))

    def test_memory_evidence_fields(self):
        result = result_of("get_memory_stats")
        self.assertEqual(result["data"]["metadata"], {"source": "doris_be_metrics", "invented_values": False})
        self.assertEqual((result["data"]["status"], result["data"]["warnings"]), ("success", []))
        recorded = FIXTURE["doris_cluster.get_memory_stats"]["data"]["data"]["nodes"][0]["metrics"]
        self.assertTrue(set(result["data"]["data"]["nodes"][0]["metrics"]) <= set(recorded))
        self.assertIn(f"four of its {len(recorded)} metrics", LESSON.read_text())

    def test_manifest_versions_come_from_the_recorded_run(self):
        text = LESSON.read_text()
        for domain in ("doris_catalog", "doris_query", "doris_cluster"):
            version = FIXTURE[f"{domain}.discovery"]["manifest_version"]
            with self.subTest(domain=domain):
                self.assertIn(version, text)
        self.assertEqual(set(re.findall(r"\b(?:catalog|query|cluster)\.[0-9a-f]{12}\b", text)),
                         {FIXTURE[f"{domain}.discovery"]["manifest_version"]
                          for domain in ("doris_catalog", "doris_query", "doris_cluster")})

    def test_discovery_counts_in_the_text_match_the_recorded_run(self):
        words = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven"]
        children = FIXTURE["doris_cluster.discovery"]["children"]
        callable_children = sum(child["availability"]["callable"] for child in children)
        self.assertRegex(LESSON.read_text(),
                         rf"returns {words[len(children)]} children; {words[callable_children]}\s+are callable")

if __name__ == "__main__":
    unittest.main()
