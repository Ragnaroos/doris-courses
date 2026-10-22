"""Offline checks that every Lab reads the public course data the same way."""

import io
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from doris_course import DorisLab
import doris_course.doris_client as client


ROOT = Path(__file__).resolve().parents[1]
DATASET = yaml.safe_load((ROOT / "datasets/events.yaml").read_text(encoding="utf-8"))
S3_LABS = (
    "level1/module01-introduction/lab01_start_doris_and_build_baseline.ipynb",
    "level1/module03-loading-data/lab03_load_data.ipynb",
    "level3/module09-sharding-replication/lab09_observe_sharding_and_replication.ipynb",
)
LAB3 = ROOT / "level1/module03-loading-data/lab03_load_data.ipynb"


def code_cells(relative_path):
    notebook = json.loads((ROOT / relative_path).read_text(encoding="utf-8"))
    return ["".join(cell["source"]) for cell in notebook["cells"] if cell["cell_type"] == "code"]


def s3_properties(sql_text):
    """Return the properties of every S3(...) call in a piece of SQL."""
    calls = []
    for match in re.finditer(r"\bS3\(\s*(.*?)\n\s*\)", sql_text, re.DOTALL):
        calls.append(dict(re.findall(r'"([^"]+)"\s*=\s*"([^"]*)"', match.group(1))))
    return calls


class DatasetSourceTests(unittest.TestCase):
    def test_dataset_description_matches_the_runtime(self):
        source = DATASET["source"]
        self.assertEqual(source["uri"], DorisLab.S3_CONFIG["uri"])
        self.assertEqual(source["endpoint"], DorisLab.S3_CONFIG["endpoint"])
        self.assertEqual(source["region"], DorisLab.S3_CONFIG["region"])
        self.assertEqual(source["format"], DorisLab.S3_CONFIG["format"])
        self.assertEqual(DATASET["row_count"], DorisLab.EXPECTED_ROW_COUNT)
        self.assertEqual(DATASET["min_event_time"], DorisLab.EXPECTED_MIN_TIME)
        self.assertEqual(DATASET["max_event_time"], DorisLab.EXPECTED_MAX_TIME)

    def test_course_tvf_reads_anonymously(self):
        properties = s3_properties(client.s3_tvf(DorisLab.S3_CONFIG))[0]
        self.assertEqual(properties["s3.credentials_provider_type"], "ANONYMOUS")
        self.assertNotIn("s3.access_key", properties)
        self.assertNotIn("s3.secret_key", properties)

    def test_course_tvf_raises_the_s3_timeouts(self):
        # Doris's defaults (1000 and 3000 ms) fail over a slow network or a proxy.
        properties = s3_properties(client.s3_tvf(DorisLab.S3_CONFIG))[0]
        self.assertEqual(properties["s3.connection.timeout"], str(DATASET["source"]["connection_timeout_ms"]))
        self.assertEqual(properties["s3.connection.request.timeout"], str(DATASET["source"]["request_timeout_ms"]))
        self.assertGreater(int(properties["s3.connection.timeout"]), 1000)
        self.assertGreater(int(properties["s3.connection.request.timeout"]), 3000)

    def test_every_lab_writes_the_same_complete_s3_call(self):
        expected = s3_properties(client.s3_tvf(DorisLab.S3_CONFIG))[0]
        for relative_path in S3_LABS:
            calls = [call for cell in code_cells(relative_path) for call in s3_properties(cell)]
            self.assertTrue(calls, relative_path)
            for call in calls:
                self.assertEqual(call, expected, relative_path)

    def test_lab3_downloads_the_described_fixtures(self):
        described = {fixture["url"] for fixture in DATASET["fixtures"]}
        lab3_code = "\n".join(code_cells(LAB3.relative_to(ROOT)))
        used = set(re.findall(r'"(https://[^"]+/lab3/[^"]+)"', lab3_code))
        self.assertEqual(used, described)

    def test_every_bucket_named_in_the_course_is_the_public_one(self):
        # course-bucket is the placeholder of Module 3's private-bucket example.
        allowed = {"doris-courses-public-dataset", "course-bucket"}
        for path in ROOT.rglob("*"):
            if ".venv" in path.parts or "__pycache__" in path.parts or not path.is_file():
                continue
            if path.suffix not in {".ipynb", ".py", ".md", ".yaml", ".yml", ".txt", ".toml"}:
                continue
            text = path.read_text(encoding="utf-8")
            buckets = set(re.findall(r"s3://([a-z0-9.-]+)/", text))
            buckets |= set(re.findall(r"https://([a-z0-9.-]+)\.s3\.[a-z0-9-]+\.amazonaws\.com", text))
            self.assertLessEqual(buckets, allowed, path.relative_to(ROOT))
            if path.name != Path(__file__).name:
                for credential in ("course_secrets", "{{COURSE_S3}}", "S3_READ_ONLY"):
                    self.assertNotIn(credential, text, f"{path.relative_to(ROOT)}: {credential}")


class FixtureDownloadTests(unittest.TestCase):
    def test_fixtures_are_fetched_over_https_and_validated(self):
        fixture = next(f for f in DATASET["fixtures"] if f["name"] == "stream_events_malformed.csv")
        rows = [
            f"2020-03-01 00:00:{second:02d}|{event_id}|1|view|region_01|2|0.00"
            for second, event_id in zip(range(10), range(1, 11))
        ]
        rows[-1] = rows[-1].rsplit("|", 1)[0] + "|not-a-number"
        payload = ("\n".join(rows) + "\n").encode()
        with tempfile.TemporaryDirectory() as directory:
            lab = DorisLab.__new__(DorisLab)
            lab.lab_dir = Path(directory)
            with patch.object(client.urllib.request, "urlopen", return_value=io.BytesIO(payload)) as opened, \
                 patch.object(client, "show_frame"):
                frame = lab.fetch_fixtures([
                    ("Malformed CSV", fixture["url"], "downloads/malformed.csv", "stream_malformed_csv"),
                ])
            opened.assert_called_once_with(fixture["url"], timeout=60)
            self.assertEqual(frame.iloc[0]["action"], "downloaded")
            self.assertEqual(frame.iloc[0]["rows"], "10")
            self.assertTrue((Path(directory) / "downloads/malformed.csv").exists())


if __name__ == "__main__":
    unittest.main()
