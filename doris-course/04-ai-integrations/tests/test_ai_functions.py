"""Offline tests of Module 2's lab helpers that do not need Docker, Doris, or the model."""

import re
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd
import yaml

from doris_course import ai_functions
from doris_course import environment as env
from doris_course.ai_functions import FINISHED_REQUEST, METRIC, AiFunctionsLab
from doris_course.lab import EnvironmentNotReady

ROOT = Path(__file__).resolve().parents[1]
LESSON = ROOT / "level1/module02-doris-ai-functions/course.md"

# Messages of Doris 4.1.3, as the Lab saw them.
BATCH_COUNT = "(127.0.0.1)[RUNTIME_ERROR]Failed to parse ai_sentiment batch result, expected 3 items but got 1"
BATCH_TYPE = "(127.0.0.1)[INTERNAL_ERROR]Invalid batch result format, array element 0 is not a string"
NO_HOST = ("(127.0.0.1)[HTTP_ERROR]Could not resolve host: doris-ai-llm, "
           "url=http://doris-ai-llm:8080/v1/chat/completions")
LOOPBACK = ("(127.0.0.1)[HTTP_ERROR]Failed to connect to 127.0.0.1 port 8080 after 0 ms: Couldn't connect to "
            "server, url=http://127.0.0.1:8080/v1/chat/completions")
NO_RESOURCE = "AI resource 'no_such_resource' does not exist"

SERVER_LOG = """\
0.28.421.180 I slot launch_slot_: id  0 | task 0 | processing task, is_child = 0
0.28.550.208 I slot print_timing: id  0 | task 0 | prompt eval time =     112.02 ms /    35 tokens
0.28.550.217 I slot print_timing: id  0 | task 0 |        eval time =      16.96 ms /     2 tokens
0.28.550.218 I slot print_timing: id  0 | task 0 |       total time =     128.98 ms /    37 tokens
0.29.110.004 I slot print_timing: id  0 | task 1 |       total time =      61.20 ms /    12 tokens
"""
METRICS = """\
# HELP llamacpp:prompt_tokens_total Number of prompt tokens processed.
llamacpp:prompt_tokens_total 35
llamacpp:prompt_tokens_cached_total 141
llamacpp:tokens_predicted_total 5
llamacpp:requests_processing 0
"""


def bare_lab():
    lab = AiFunctionsLab.__new__(AiFunctionsLab)
    lab.tickets = yaml.safe_load(ai_functions.TICKETS_SPEC.read_text())
    lab.session_variables = {}
    lab.connection = None
    return lab


class ResourceTests(unittest.TestCase):
    def test_the_lesson_shows_the_statement_that_the_lab_runs(self):
        if env.LLM_ENDPOINT != f"http://{env.LLM_CONTAINER}:8080/v1/chat/completions":
            self.skipTest("DORIS_AI_LLM_ENDPOINT points to another server")
        statement = bare_lab().resource_sql()
        self.assertIn(statement + ";", LESSON.read_text())

    def test_the_resource_is_local_and_needs_no_key(self):
        statement = bare_lab().resource_sql()
        self.assertIn('"ai.provider_type" = "local"', statement)
        self.assertNotIn("api_key", statement)
        self.assertIn(f'"ai.model_name" = "{env.LLM_MODEL}"', statement)


class FailureTests(unittest.TestCase):
    def test_answers_that_doris_cannot_parse_are_the_models(self):
        lab = bare_lab()
        for message in (BATCH_COUNT, BATCH_TYPE):
            with self.subTest(message=message):
                hint, in_answer = lab._explain_failure(message)
                self.assertTrue(in_answer)
                self.assertIn("JSON array", hint)

    def test_failures_on_the_way_to_the_model_are_not(self):
        lab = bare_lab()
        for message, words in ((NO_HOST, "lab.start_model()"), (LOOPBACK, "127.0.0.1 is the container itself"),
                               (NO_RESOURCE, "lab.create_resource()")):
            with self.subTest(message=message):
                hint, in_answer = lab._explain_failure(message)
                self.assertFalse(in_answer)
                self.assertIn(words, hint)


class AiSqlTests(unittest.TestCase):
    """lab.ai_sql isolates answers that Doris cannot parse, and stops on a broken route."""

    def run_ai_sql(self, results, **arguments):
        lab = bare_lab()
        shown = []
        with mock.patch.object(lab, "_execute", side_effect=results), \
                mock.patch.object(lab, "_model_counters", return_value=None), \
                mock.patch.object(ai_functions, "show_sql"), mock.patch.object(ai_functions, "show_log"), \
                mock.patch.object(ai_functions, "card"), mock.patch.object(lab, "_failure"), \
                mock.patch.object(ai_functions, "show_frame", lambda title, frame, **_: shown.append((title, frame))):
            value = lab.ai_sql(arguments.pop("statement"), title="t", **arguments)
        return value, dict(shown)

    def test_a_bad_answer_fails_only_its_own_ticket(self):
        value, shown = self.run_ai_sql([(1, None), (None, BATCH_TYPE), (1, None)],
                                       statement="INSERT INTO t SELECT {ticket_id}", each=[1, 2, 3])
        self.assertEqual(value, 2)
        outcomes = shown["Outcome for each ticket"]
        self.assertEqual(list(outcomes["outcome"]), ["wrote 1 row(s)", "failed", "wrote 1 row(s)"])

    def test_a_broken_route_stops_the_cell(self):
        with self.assertRaises(EnvironmentNotReady):
            self.run_ai_sql([(None, NO_HOST)], statement="SELECT AI_GENERATE('ai_course_llm', 'x')")

    def test_a_single_statement_that_the_model_broke_returns_none(self):
        value, _ = self.run_ai_sql([(None, BATCH_COUNT)], statement="SELECT 1")
        self.assertIsNone(value)

    def test_nothing_pending_runs_nothing(self):
        lab = bare_lab()
        with mock.patch.object(lab, "_execute") as execute, mock.patch.object(ai_functions, "show_sql"), \
                mock.patch.object(ai_functions, "card"):
            value = lab.ai_sql("INSERT INTO t SELECT {ticket_id}", title="t", each=pd.Series([], dtype=int))
        execute.assert_not_called()
        self.assertEqual(value, 0)


class ModelWorkTests(unittest.TestCase):
    def test_the_log_has_one_finished_line_per_request(self):
        self.assertEqual(len(FINISHED_REQUEST.findall(SERVER_LOG)), 2)

    def test_metrics_parse(self):
        metrics = {name: float(value) for name, value in METRIC.findall(METRICS)}
        self.assertEqual(metrics["prompt_tokens_total"], 35)
        self.assertEqual(metrics["prompt_tokens_cached_total"], 141)

    def test_work_is_the_difference_between_two_readings(self):
        before = {"requests": 3, "prompt_tokens": 400, "generated_tokens": 10}
        after = {"requests": 31, "prompt_tokens": 5640, "generated_tokens": 130}
        work = AiFunctionsLab.model_work(before, after, 13.84)
        self.assertEqual(work, {"model requests": 28, "prompt tokens": 5240, "generated tokens": 120,
                                "seconds": "13.8"})

    def test_work_that_cannot_be_read_is_not_measured(self):
        work = AiFunctionsLab.model_work(None, None, 1.0)
        self.assertEqual(work["model requests"], "not measured")
        partial = AiFunctionsLab.model_work({"requests": 1, "prompt_tokens": None, "generated_tokens": None},
                                            {"requests": 2, "prompt_tokens": None, "generated_tokens": None}, 1.0)
        self.assertEqual((partial["model requests"], partial["prompt tokens"]), (1, "not measured"))


class TicketLoadTests(unittest.TestCase):
    def test_table_ddl_declares_every_column_with_its_comment(self):
        lab = bare_lab()
        ddl = lab._tickets_ddl()
        for column in lab.tickets["columns"]:
            self.assertIn(f'{column["name"]} {column["type"]} NOT NULL COMMENT "{column["comment"]}"', ddl)
        self.assertIn("DUPLICATE KEY(ticket_id)", ddl)

    def test_insert_quotes_the_text_safely(self):
        lab = bare_lab()
        row = {"ticket_id": "7", "created_at": "2026-10-01 09:00:00", "language": "en",
               "raw_text": "It's \\ broken", "expected_topic": "quality", "expected_sentiment": "negative"}
        statement = lab._insert_tickets_sql([row])
        self.assertIn("(7, '2026-10-01 09:00:00', 'en', 'It\\'s \\\\ broken', 'quality', 'negative')", statement)
        with self.assertRaises(ValueError):
            lab._insert_tickets_sql([dict(row, ticket_id="7; DROP TABLE t")])

    def test_every_ticket_goes_into_the_insert(self):
        lab = bare_lab()
        rows = lab._ticket_rows()
        statement = lab._insert_tickets_sql(rows)
        self.assertEqual(len(re.findall(r"^\(\d+, ", statement, re.M)), lab.tickets["row_count"])


if __name__ == "__main__":
    unittest.main()
