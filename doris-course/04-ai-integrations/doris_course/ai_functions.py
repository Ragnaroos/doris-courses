"""Learner-facing runtime for the local Doris AI Functions lab."""

from __future__ import annotations

import csv
import json
import re
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import pymysql

from doris_labkit.db import connect_doris, report_sql_error
from doris_labkit.docker import start_container
from doris_labkit.results import result_frame, show_frame
from doris_labkit.ui import card, install_styles


DORIS_CONTAINER = "doris"
DORIS_HOST = "127.0.0.1"
DORIS_PORT = 9030
DORIS_DATABASE = "doris_course"
RESOURCE_NAME = "ollama_qwen25_1_5b"
MODEL_NAME = "qwen2.5:1.5b-instruct"
OLLAMA_PORT = 11434
CHAT_PATH = "/v1/chat/completions"
ALLOWED_TOPICS = {"refund", "shipping", "quality", "account", "product_question"}
ALLOWED_SENTIMENTS = {"positive", "negative", "neutral", "mixed"}


class AiFunctionsLab:
    """Small, course-level helper used by Module 02's learner notebook."""

    RESOURCE_NAME = RESOURCE_NAME
    MODEL_NAME = MODEL_NAME
    CHAT_PATH = CHAT_PATH

    def __init__(
        self,
        lab_dir: Path,
        *,
        host: str = DORIS_HOST,
        port: int = DORIS_PORT,
        container: str = DORIS_CONTAINER,
        ollama_port: int = OLLAMA_PORT,
    ) -> None:
        if not 1 <= int(ollama_port) <= 65535:
            raise ValueError("ollama_port must be between 1 and 65535.")
        self.lab_dir = Path(lab_dir).resolve()
        self.host = host
        self.port = port
        self.container = container
        self.ollama_port = int(ollama_port)
        self.host_ollama = f"http://127.0.0.1:{self.ollama_port}"
        self.be_ollama = f"http://host.docker.internal:{self.ollama_port}"
        self.chat_path = CHAT_PATH
        self.connection = None
        install_styles()
        card(
            f"Doris: {host}:{port}; container: {container}; module: {self.lab_dir}",
            "ok",
            "AI Functions lab tools are ready",
        )

    def start(self) -> None:
        """Start or reuse the prerequisite single-FE/single-BE container."""
        state = start_container(
            self.container,
            missing_hint="Complete the prerequisite Doris Docker Lab before continuing.",
        )
        self.connection = None
        show_frame(
            "Doris container",
            pd.DataFrame([{
                "container": self.container,
                "status": state.get("State", {}).get("Status", "unknown"),
                "health": state.get("State", {}).get("Health", {}).get("Status", "not reported"),
                "query_endpoint": f"{self.host}:{self.port}",
            }]),
        )

    def connect(self):
        """Connect as the course administrator and select the existing database."""
        if self.connection is None:
            self.connection = connect_doris(host=self.host, port=self.port)
        self.execute(f"USE {DORIS_DATABASE}")
        return self.connection

    def _require_connection(self):
        return self.connection or self.connect()

    def query(self, statement: str) -> pd.DataFrame:
        """Run SQL and return a DataFrame without displaying it."""
        clean = statement.strip().rstrip(";").rstrip()
        with self._require_connection().cursor() as cursor:
            try:
                cursor.execute(clean)
            except pymysql.MySQLError as error:
                report_sql_error(None, clean, error)
                raise
            rows = cursor.fetchall() if cursor.description else []
            columns = [column[0] for column in cursor.description or ()]
        return result_frame(rows, columns)

    def execute(self, statement: str) -> int:
        """Run a statement and return its affected-row count."""
        clean = statement.strip().rstrip(";").rstrip()
        with self._require_connection().cursor() as cursor:
            try:
                return cursor.execute(clean)
            except pymysql.MySQLError as error:
                report_sql_error(None, clean, error)
                raise

    @staticmethod
    def _json_request(
        url: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout: int = 30,
    ) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"} if data is not None else {},
            method="POST" if data is not None else "GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Ollama request failed for {url}: {exc}") from exc

    def ollama_host_preflight(
        self,
        model_name: str = MODEL_NAME,
    ) -> tuple[pd.DataFrame, str, str]:
        """Verify host Ollama and make one bounded completion request."""
        version = self._json_request(f"{self.host_ollama}/api/version")
        tags = self._json_request(f"{self.host_ollama}/api/tags")
        selected = next(
            (
                model
                for model in tags.get("models", [])
                if model.get("name") == model_name or model.get("model") == model_name
            ),
            None,
        )
        if selected is None:
            raise RuntimeError(
                f"Model {model_name!r} is not installed. Run `ollama pull {model_name}` "
                "in a terminal, then rerun this cell."
            )
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": "Include the token HOST_OK in one short sentence."}],
            "temperature": 0,
            "max_tokens": 24,
            "stream": False,
        }
        started = time.perf_counter()
        response = self._json_request(f"{self.host_ollama}{self.chat_path}", payload)
        elapsed = time.perf_counter() - started
        text = str(response["choices"][0]["message"]["content"]).strip()
        if "HOST_OK" not in text:
            raise AssertionError("The host completion did not contain the requested HOST_OK marker.")
        digest = str(selected.get("digest", "not reported"))
        details = selected.get("details", {}) or {}
        frame = pd.DataFrame([{
            "route": "host → Ollama",
            "ollama_version": version.get("version", "unknown"),
            "model": model_name,
            "digest": digest,
            "parameters": details.get("parameter_size", "unknown"),
            "quantization": details.get("quantization_level", "unknown"),
            "elapsed_seconds": round(elapsed, 3),
        }])
        return frame, text, digest

    def ollama_be_preflight(
        self,
        model_name: str = MODEL_NAME,
    ) -> tuple[pd.DataFrame, str]:
        """Verify the exact Docker route later used by the Doris BE."""
        from doris_labkit.docker import run

        payload = json.dumps({
            "model": model_name,
            "messages": [{"role": "user", "content": "Include the token BE_OK in one short sentence."}],
            "temperature": 0,
            "max_tokens": 24,
            "stream": False,
        }, ensure_ascii=False)
        started = time.perf_counter()
        result = run([
            "docker", "exec", self.container, "curl", "-fsS", "--max-time", "30",
            f"{self.be_ollama}{self.chat_path}", "-H", "Content-Type: application/json", "-d", payload,
        ], timeout=40)
        elapsed = time.perf_counter() - started
        try:
            response = json.loads(result.stdout)
            text = str(response["choices"][0]["message"]["content"]).strip()
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                f"The container received an unexpected Ollama response: {result.stdout[:500]}"
            ) from exc
        if "BE_OK" not in text:
            raise AssertionError("The container completion did not contain the requested BE_OK marker.")
        frame = pd.DataFrame([{
            "route": f"{self.container} container → host.docker.internal → Ollama",
            "endpoint": f"{self.be_ollama}{self.chat_path}",
            "http_result": "success",
            "elapsed_seconds": round(elapsed, 3),
        }])
        return frame, text

    @staticmethod
    def read_ticket_csv(path: Path) -> list[dict[str, str]]:
        required = [
            "ticket_id", "created_at", "language", "raw_text",
            "expected_topic", "expected_sentiment",
        ]
        with Path(path).open("r", encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != required:
                raise ValueError(f"Unexpected CSV columns: {reader.fieldnames!r}")
            rows = list(reader)
        if not 12 <= len(rows) <= 16:
            raise ValueError("The bounded teaching dataset must contain 12–16 rows.")
        ids = [int(row["ticket_id"]) for row in rows]
        if len(ids) != len(set(ids)):
            raise ValueError("ticket_id values must be unique.")
        topics = {row["expected_topic"] for row in rows}
        sentiments = {row["expected_sentiment"] for row in rows}
        languages = {row["language"] for row in rows}
        if topics != ALLOWED_TOPICS:
            raise ValueError(f"Dataset topic coverage is invalid: {sorted(topics)}")
        if not ALLOWED_SENTIMENTS <= sentiments:
            raise ValueError(f"Dataset sentiment coverage is invalid: {sorted(sentiments)}")
        if not {"en", "zh"} <= languages:
            raise ValueError("Dataset must include both English and Chinese text.")
        if any(not row["raw_text"].strip() for row in rows):
            raise ValueError("raw_text must be nonempty for every row.")
        return rows

    def load_tickets(self, path: Path) -> int:
        """Load the validated local CSV using parameter binding."""
        rows = self.read_ticket_csv(path)
        statement = """
        INSERT INTO ai_support_tickets
            (ticket_id, created_at, language, raw_text, expected_topic, expected_sentiment)
        VALUES (%s, %s, %s, %s, %s, %s)
        """
        columns = (
            "ticket_id", "created_at", "language", "raw_text",
            "expected_topic", "expected_sentiment",
        )
        values = [tuple(row[column] for column in columns) for row in rows]
        with self._require_connection().cursor() as cursor:
            affected = cursor.executemany(statement, values)
        if affected != len(rows):
            raise AssertionError(f"Loaded {affected} rows; expected {len(rows)}.")
        return affected

    def resource_properties(self, resource_name: str = RESOURCE_NAME) -> pd.DataFrame:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", resource_name):
            raise ValueError("Unsafe resource name.")
        return self.query(f'SHOW RESOURCES WHERE NAME = "{resource_name}"')

    def assert_owned_resource_or_absent(
        self,
        resource_name: str = RESOURCE_NAME,
    ) -> pd.DataFrame:
        frame = self.resource_properties(resource_name)
        if frame.empty:
            return frame
        properties = {str(row["Item"]): str(row["Value"]) for _, row in frame.iterrows()}
        expected = {
            "type": "ai",
            "ai.provider_type": "LOCAL",
            "ai.endpoint": f"{self.be_ollama}{self.chat_path}",
            "ai.model_name": MODEL_NAME,
        }
        mismatches = {
            key: {"expected": value, "actual": properties.get(key)}
            for key, value in expected.items()
            if (
                properties.get(key, "").upper() != value.upper()
                if key == "ai.provider_type"
                else properties.get(key) != value
            )
        }
        if mismatches:
            raise RuntimeError(
                f"Resource {resource_name!r} already exists but is not owned by this Lab: "
                f"{mismatches}. Choose a different name or remove it after confirming its owner."
            )
        return frame

    def write_enrichment(
        self,
        rows: Iterable[dict[str, Any]],
        *,
        model_digest: str,
        prompt_version: str,
        model_name: str = MODEL_NAME,
        run_id: str | None = None,
    ) -> str:
        """Materialize validated outputs without making another model call."""
        materialized = list(rows)
        run_id = run_id or uuid.uuid4().hex
        statement = """
        INSERT INTO ai_ticket_enrichment
            (ticket_id, topic, sentiment, summary, model_name, model_digest,
             prompt_version, processed_at, run_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), %s)
        """
        values = [(
            int(row["ticket_id"]),
            None if pd.isna(row.get("topic")) else row.get("topic"),
            None if pd.isna(row.get("sentiment")) else row.get("sentiment"),
            None if pd.isna(row.get("summary")) else row.get("summary"),
            model_name,
            model_digest,
            prompt_version,
            run_id,
        ) for row in materialized]
        with self._require_connection().cursor() as cursor:
            affected = cursor.executemany(statement, values)
        if affected != len(values):
            raise AssertionError(f"Materialized {affected} rows; expected {len(values)}.")
        return run_id
