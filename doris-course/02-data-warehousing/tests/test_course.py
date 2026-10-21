"""Offline course checks. These tests do not connect to Doris."""

import ast
import io
import json
import re
import sys
import tokenize
import unittest
from collections import Counter
from decimal import Decimal
from html import escape
from pathlib import Path
from unittest.mock import Mock, patch

import nbformat
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dw_course.runtime import COURSE_ROOT, WarehouseLab, expect, fixture, identifier
from dw_course.schema import ORDER_COLUMNS, order_ddl, order_rows
from dw_course.wwi import HISTORY_COLUMNS, history_ddl, history_rows, manifest, parquet_paths, sample


def ends_with_bare_lab_call(source):
    """Return True when a cell's last statement is a bare lab.<method>(...) call.

    lab.close() returns None, so Jupyter shows nothing for it.
    """
    statements = ast.parse(source).body
    if not statements or not isinstance(statements[-1], ast.Expr):
        return False
    call = statements[-1].value
    return (
        isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "lab"
        and call.func.attr != "close"
    )


def hides_trailing_result(source):
    """Like IPython, skip trailing comments and blank lines, then look for a final ";"."""
    skipped = {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.ENDMARKER}
    tokens = [t for t in tokenize.generate_tokens(io.StringIO(source).readline) if t.type not in skipped]
    return tokens[-1].type == tokenize.OP and tokens[-1].string == ";"


class FixturesTest(unittest.TestCase):
    def test_initial_contract(self):
        orders = fixture("orders.json")
        expected = fixture("expected_summary.json")
        self.assertEqual(len(orders), expected["initial_rows"])
        self.assertEqual(sum(Decimal(x["order_amount"]) for x in orders), Decimal("1400.00"))
        self.assertEqual(len({x["order_id"] for x in orders}), 10)
        raw = fixture("raw_orders.json")
        self.assertEqual(len(raw), 13)
        self.assertEqual([r["input_id"] for r in raw if r["order_id"] is None], [12])
        self.assertTrue(all(r["data_source"] == "COURSE_SIMULATION" for r in orders))
        self.assertEqual(min(r["order_id"] for r in orders), 900001)

    def test_replay_independent_oracle(self):
        initial = fixture("orders.json")
        deliveries = fixture("deliveries.json")
        current = {x["order_id"]: x for x in initial}
        history = {x["event_id"]: x for x in initial}
        for attempt in range(2):
            for delivered in deliveries:
                record = {key: value for key, value in delivered.items() if key != "delivery_id"}
                if record["event_id"] in history:
                    self.assertEqual(history[record["event_id"]], record)
                history[record["event_id"]] = record
                old = current.get(record["order_id"])
                if old is None or record["event_version"] > old["event_version"]:
                    current[record["order_id"]] = record
            self.assertEqual([current[key] for key in sorted(current)], fixture("expected_current.json"))
            self.assertEqual(len(history), 18)
        summary = fixture("expected_summary.json")
        self.assertEqual(Counter(row["status"] for row in current.values()), summary["statuses"])
        for column, expected in [("order_amount", "1510.00"), ("paid_amount", "250.00"), ("refund_amount", "150.00")]:
            self.assertEqual(sum(Decimal(row[column]) for row in current.values()), Decimal(expected))

    def test_csv_matches_json(self):
        import csv
        from dw_course.schema import ORDER_COLUMNS
        with (COURSE_ROOT / "datasets/orders.csv").open() as stream:
            rows = list(csv.reader(stream))
        expected = [[str(record[col]) for col in ORDER_COLUMNS] for record in fixture("orders.json")]
        self.assertEqual(rows, expected)

    def test_wwi_subset_has_real_relationships_and_independent_totals(self):
        data = sample()
        self.assertEqual([r["order_id"] for r in data["orders"]], [1, 2, 3, 4, 5, 80, 81, 82, 83, 84])
        self.assertEqual(sum(Decimal(r["order_amount"]) for r in data["orders"]), Decimal("12220.60"))
        customers = {r["customer_id"] for r in data["customers"]}
        products = {r["product_id"] for r in data["products"]}
        for order in data["orders"]:
            self.assertIn(order["customer_id"], customers)
            lines = [r for r in data["order_lines"] if r["order_id"] == order["order_id"]]
            self.assertEqual(len(lines), order["line_count"])
            self.assertEqual(sum(r["quantity"] * Decimal(r["unit_price"]) for r in lines), Decimal(order["order_amount"]))
            self.assertTrue(all(r["product_id"] in products for r in lines))
            self.assertEqual(order["data_source"], "WWI")
        self.assertEqual(sum(t["rows"] for t in manifest()["tables"].values()), 701846)

    def test_simulation_business_ledgers_reconcile(self):
        business = fixture("business_events.json")
        current = fixture("expected_current.json")
        customers = {r["customer_id"] for r in sample()["customers"]}
        products = {r["product_id"] for r in sample()["products"]}
        events = {r["event_id"]: r for r in fixture("deliveries.json")}
        payments = {r["payment_id"]: r for r in business["payments"]}
        for r in business["order_lines"]:
            self.assertIn(r["product_id"], products)
        for r in business["refunds"]:
            self.assertEqual(r["order_id"], payments[r["payment_id"]]["order_id"])
            self.assertLessEqual(Decimal(r["amount"]), Decimal(payments[r["payment_id"]]["amount"]))
        for order in current:
            self.assertIn(order["customer_id"], customers)
            amount = sum(r["quantity"] * Decimal(r["unit_price"]) for r in business["order_lines"] if r["order_id"] == order["order_id"])
            self.assertEqual(amount, Decimal(order["order_amount"]))
            for collection, column in [("payments", "paid_amount"), ("refunds", "refund_amount")]:
                total = sum(Decimal(r["amount"]) for r in business[collection] if r["order_id"] == order["order_id"])
                self.assertEqual(total, Decimal(order[column]))
        for collection in ("payments", "refunds", "shipments"):
            for record in business[collection]:
                self.assertEqual(record["order_id"], events[record["event_id"]]["order_id"])
                self.assertEqual(record["event_time"], events[record["event_id"]]["event_time"])
        self.assertEqual(len(fixture("deliveries.json")), 9)
        self.assertEqual(len(events), 8)
        self.assertEqual(current[0]["status"], "DELIVERED")
        self.assertEqual(current[2]["status"], "REFUNDED")


class RuntimeTest(unittest.TestCase):
    def test_scoped_database_and_opt_in(self):
        with patch.dict("os.environ", {}, clear=True), patch("pymysql.connect") as connect:
            with self.assertRaises(RuntimeError):
                WarehouseLab()
            connect.assert_not_called()
        with patch.dict("os.environ", {"DW_ALLOW_WRITES": "yes", "DW_DATABASE": "production"}, clear=True), patch("pymysql.connect") as connect:
            with self.assertRaises(ValueError):
                WarehouseLab()
            connect.assert_not_called()

    def test_identifiers_and_fixture_scope(self):
        for value in ["a; DROP TABLE t", "catalog.table", "../orders"]:
            with self.assertRaises(ValueError):
                identifier(value)
        with self.assertRaises(ValueError):
            fixture("../orders.json")

    def test_expect_catches_mismatch(self):
        with self.assertRaises(AssertionError):
            expect([(11, Decimal("1400.00"))], [(10, "1400.00")])

    def test_model_contract(self):
        self.assertIn('UNIQUE KEY(order_id)', order_ddl("orders_current", current=True))
        self.assertIn('"function_column.sequence_col"="event_version"', order_ddl("orders_current", current=True))
        self.assertIn("UNIQUE KEY(event_id)", order_ddl("order_events", history=True))
        with self.assertRaises(ValueError):
            order_ddl("invalid", current=True, history=True)

    def test_stream_load_does_not_follow_redirect(self):
        lab = WarehouseLab.__new__(WarehouseLab)
        lab.database, lab.user, lab.password = "dw_course_l1_test", "student", "not-a-real-password"
        response = Mock(status_code=307)
        with patch("requests.put", return_value=response) as put:
            with self.assertRaises(RuntimeError):
                lab.stream_load("orders", COURSE_ROOT / "datasets/orders.csv", "test", "order_id")
        self.assertFalse(put.call_args.kwargs["allow_redirects"])

    def test_parquet_stream_load_headers(self):
        lab = WarehouseLab.__new__(WarehouseLab)
        lab.database, lab.user, lab.password = "dw_course_l1_test", "student", "not-a-real-password"
        response = Mock(status_code=200)
        response.json.return_value = {"Status": "Success"}
        with patch("requests.put", return_value=response) as put:
            lab.stream_load("orders", COURSE_ROOT / "datasets/orders.csv", "test", format="parquet")
        headers = put.call_args.kwargs["headers"]
        self.assertEqual(headers["format"], "parquet")
        self.assertNotIn("column_separator", headers)
        self.assertNotIn("columns", headers)
        self.assertFalse(put.call_args.kwargs["allow_redirects"])

    def test_json_stream_load_reads_one_array_of_objects(self):
        lab = WarehouseLab.__new__(WarehouseLab)
        lab.database, lab.user, lab.password = "dw_course_l1_test", "student", "not-a-real-password"
        response = Mock(status_code=200)
        response.json.return_value = {"Status": "Success"}
        with patch("requests.put", return_value=response) as put:
            lab.stream_load("orders_raw", COURSE_ROOT / "datasets/raw_orders.json", "test", "input_id,order_id", format="json")
        headers = put.call_args.kwargs["headers"]
        self.assertEqual((headers["format"], headers["strip_outer_array"], headers["columns"]), ("json", "true", "input_id,order_id"))
        self.assertNotIn("column_separator", headers)
        with self.assertRaises(ValueError):
            lab.stream_load("orders_raw", COURSE_ROOT / "datasets/raw_orders.json", "test", format="xml")

    def test_wwi_bundle_rejects_missing_or_changed_files(self):
        import hashlib
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            payload = b"fixture-only-not-parquet"
            metadata = {"tables": {"orders": {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}}}
            with patch("dw_course.wwi.manifest", return_value=metadata):
                with self.assertRaises(FileNotFoundError):
                    parquet_paths(directory)
                path = Path(directory) / "orders.parquet"
                path.write_bytes(payload)
                self.assertEqual(parquet_paths(directory), {"orders": path})
                path.write_bytes(b"changed")
                with self.assertRaises(ValueError):
                    parquet_paths(directory)


class MaterialsTest(unittest.TestCase):
    def test_learner_materials_use_module_labels(self):
        for path in COURSE_ROOT.rglob("*"):
            if path.suffix not in {".md", ".yaml", ".ipynb"}:
                continue
            if any(part in {".runtime", ".venv", ".ipynb_checkpoints"} for part in path.parts):
                continue
            if path.suffix == ".ipynb":
                notebook = nbformat.read(path, as_version=4)
                # Executed learner outputs are historical records, not authored text.
                content = "\n".join(cell.source for cell in notebook.cells)
            else:
                content = path.read_text()
            self.assertNotRegex(content, r"(?<![A-Za-z0-9_])D0?[1-7](?![A-Za-z0-9_])", path)
        for module in (COURSE_ROOT / "level1").glob("module*"):
            number = int(re.match(r"module(\d+)", module.name)[1])
            reading = next(module.glob("course*.md")).read_text()
            self.assertTrue(reading.startswith(f"# Module {number}:"), module)
            for quiz_path in module.glob("quiz*.yaml"):
                quiz = yaml.safe_load(quiz_path.read_text())
                self.assertTrue(quiz["title"].startswith(f"Module {number} Quiz:"), quiz_path)

    def test_learner_prose_excludes_author_status_notes(self):
        paths = list((COURSE_ROOT / "level1").glob("*/course*.md"))
        paths += list((COURSE_ROOT / "level1").glob("*/*.ipynb"))
        for path in paths:
            content = path.read_text()
            if path.suffix == ".ipynb":
                notebook = nbformat.read(path, as_version=4)
                content = "\n".join(c.source for c in notebook.cells if c.cell_type == "markdown")
            self.assertNotRegex(content, r"(?i)candidate experiment|candidate lab|not yet tested|initial lab draft|acceptance evidence|do not mark unexecuted steps as complete|maintenance/.*/VALIDATION\.md", path)
        for path in (COURSE_ROOT / "level1").glob("*/quiz*.ipynb"):
            notebook = nbformat.read(path, as_version=4)
            content = "\n".join(c.source for c in notebook.cells if c.cell_type == "markdown")
            self.assertIn("### Load the Quiz", content, path)
            self.assertIn("## Start the Quiz", content, path)

    def test_readings_keep_examples_separate_from_lab_writes(self):
        for path in (COURSE_ROOT / "level1").glob("*/course*.md"):
            content = path.read_text()
            blocks = re.findall(
                r"(?:(^<!-- (?:external-service-example|reading-only-example) -->\n))?^```sql\n(.*?)^```",
                content, re.MULTILINE | re.DOTALL,
            )
            self.assertTrue(blocks, path)
            for marker, block in blocks:
                if "reading-only-example" in marker:
                    self.assertIn("SQL reading example:", content)
                    allowed_targets = {
                        "module03-table-design": {"orders_partitioned"},
                        "module05-ingestion": {"orders_defaults_reading"},
                        "module06-data-quality": {"orders_classified", "orders_clean", "orders_rejected"},
                        "module07-state-changes": {"orders_partial_update", "orders_delete_demo"},
                    }
                    self.assertIn(path.parent.name, allowed_targets)
                    targets = re.findall(
                        r"(?:CREATE TABLE|CREATE VIEW|INSERT INTO|UPDATE|DELETE FROM)\s+(\w+)", block)
                    self.assertTrue(targets, path)
                    self.assertLessEqual(set(targets), allowed_targets[path.parent.name])
                    self.assertNotRegex(block, r"\b(DROP|TRUNCATE|ALTER|GRANT|REVOKE)\b")
                    for statement in (s.strip() for s in block.split(";") if s.strip()):
                        self.assertRegex(statement, r"^(CREATE TABLE|CREATE VIEW|INSERT INTO|UPDATE|DELETE FROM|SET|SELECT)\b")
                        if statement.startswith("SET"):
                            self.assertEqual(path.parent.name, "module07-state-changes")
                            self.assertEqual(statement, "SET enable_unique_key_partial_update = true")
                    continue
                if "external-service-example" in marker:
                    self.assertIn(path.parent.name, ("module04-external-access", "module05-ingestion"))
                    self.assertIn("<", block)  # Requires external connection parameters.
                    self.assertNotRegex(block, r"\b(orders_imported|wwi_\w+)\b")
                    continue
                statements = [s.strip() for s in block.split(";") if s.strip()]
                for statement in statements:
                    self.assertRegex(statement, r"^(SELECT|EXPLAIN|SHOW)\b", path)

    def test_reading_result_tables_match_wwi_and_replay_fixtures(self):
        intro = next((COURSE_ROOT / "level1/module01-introduction").glob("course*.md")).read_text()
        dates = sorted({row["order_date"] for row in sample()["orders"]})
        for date in dates:
            rows = [row for row in sample()["orders"] if row["order_date"] == date]
            amount = sum(Decimal(row["order_amount"]) for row in rows)
            self.assertIn(f"| {date} | {len(rows)} | {amount:.2f} |", intro)
        changes = next((COURSE_ROOT / "level1/module07-state-changes").glob("course*.md")).read_text()
        for row in fixture("deliveries.json"):
            if row["order_id"] == 900001:
                prefix = f'| {row["delivery_id"]} | {row["event_id"]} | {row["event_version"]} | {row["status"]}'
                self.assertIn(prefix, changes)
        for row in fixture("expected_current.json"):
            if row["order_id"] in (900001, 900003):
                expected = (f'| {row["order_id"]} | {row["status"]} | {row["event_version"]} '
                            f'| {row["paid_amount"]} | {row["refund_amount"]} |')
                self.assertIn(expected, changes)

    def test_intro_walkthrough_matches_sample_line_items_and_filters(self):
        intro = next((COURSE_ROOT / "level1/module01-introduction").glob("course*.md")).read_text()
        data = sample()
        order = next(row for row in data["orders"] if row["order_id"] == 4)
        self.assertIn(
            f'| 4 | {order["customer_id"]} | {order["order_date"]} | '
            f'{order["order_amount"]} | {order["line_count"]} |', intro,
        )
        lines = [line for line in data["order_lines"] if line["order_id"] == 4]
        self.assertEqual(len(lines), order["line_count"])
        self.assertEqual(sum(line["quantity"] * Decimal(line["unit_price"]) for line in lines),
                         Decimal(order["order_amount"]))
        selected = [row for row in data["orders"] if Decimal(row["order_amount"]) >= 1000]
        for order in selected:
            self.assertIn(
                f'| {order["order_id"]} | {order["order_date"]} | {order["order_amount"]} |', intro,
            )
        selected_amount = sum(Decimal(row["order_amount"]) for row in selected)
        self.assertIn(f"three orders total {selected_amount:.2f}", intro)
        doubled = 2 * sum(Decimal(row["order_amount"]) for row in data["orders"])
        self.assertIn(f"twenty rows and an amount of {doubled:.2f}", intro)

    def test_numbered_material_names(self):
        import runpy
        modules = sorted((COURSE_ROOT / "level1").glob("module*"))
        self.assertEqual([module.name for module in modules], [
            "module01-introduction", "module02-architecture", "module03-table-design",
            "module04-external-access", "module05-ingestion", "module06-data-quality",
            "module07-state-changes",
        ])
        runner = runpy.run_path(str(COURSE_ROOT / "scripts/run_labs.py"))
        self.assertEqual(runner["CORE"], [
            module.name for module in modules if module.name != "module04-external-access"
        ])
        for module in (COURSE_ROOT / "level1").glob("module*"):
            number = re.match(r"module(\d{2})-", module.name)[1]
            self.assertTrue((module / "course.md").is_file())
            self.assertEqual(list(module.glob("course?*.md")), [])
            self.assertEqual(len(list(module.glob(f"lab{number}_*.ipynb"))), 1)
            # Module 5 has a second quiz, for its optional reading on continuous ingestion.
            quizzes = 2 if module.name == "module05-ingestion" else 1
            self.assertEqual(len(list(module.glob(f"quiz{number}_*.yaml"))), quizzes)
            self.assertEqual(len(list(module.glob(f"quiz{number}_*.ipynb"))), quizzes)
            for yaml_path in module.glob(f"quiz{number}_*.yaml"):
                quiz_path = yaml_path.with_suffix(".ipynb")
                quiz_source = "\n".join(cell.source for cell in nbformat.read(quiz_path, as_version=4).cells)
                self.assertIn(str(yaml_path.relative_to(COURSE_ROOT)), quiz_source)
            self.assertFalse((module / "quiz.ipynb").exists())

    def test_notebooks_are_valid_clean_and_compilable(self):
        paths = list((COURSE_ROOT / "level1").glob("*/*.ipynb"))
        self.assertEqual(len(paths), 20)  # Seven Lab/Quiz pairs, three extensions, two streaming Labs, one reading quiz.
        for path in paths:
            notebook = nbformat.read(path, as_version=4)
            nbformat.validate(notebook)
            for cell in notebook.cells:
                if cell.cell_type == "code":
                    self.assertEqual(cell.outputs, [], path)
                    self.assertIsNone(cell.execution_count, path)
                    ast.parse(cell.source, filename=str(path))

    def test_trailing_lab_calls_end_with_semicolon(self):
        # Jupyter echoes a cell's last value: lab.sql() would show its table twice,
        # lab.execute() would print a stray row count.
        paths = sorted(path for path in COURSE_ROOT.glob("level*/**/*.ipynb") if not path.name.startswith("quiz"))
        self.assertEqual(len(paths), 19)  # Level 1: seven Labs, 5A, 5B, three extensions; Level 2: four; Level 3: three.
        for path in paths:
            notebook = nbformat.read(path, as_version=4)
            for cell in notebook.cells:
                if cell.cell_type != "code" or not ends_with_bare_lab_call(cell.source):
                    continue
                with self.subTest(notebook=path.name, cell=cell.get("id")):
                    self.assertTrue(hides_trailing_result(cell.source))

    def test_quiz_contract_and_shared_renderer(self):
        from dw_course.quiz import CourseQuiz
        paths = list((COURSE_ROOT / "level1").glob("*/quiz*.yaml"))
        self.assertEqual(len(paths), 8)
        for path in paths:
            data = yaml.safe_load(path.read_text())
            self.assertEqual(len(data["questions"]), 6, path)
            ids = [q["id"] for q in data["questions"]]
            self.assertEqual(len(ids), len(set(ids)), path)
            for question in data["questions"]:
                # Options are shown shuffled, so they are named, not lettered.
                options = [option["id"] for option in question["options"]]
                self.assertEqual(len(options), 4, (path, question["id"]))
                for option_id in options:
                    self.assertRegex(option_id, r"^[a-z0-9]+(?:_[a-z0-9]+)*$", (path, question["id"]))
                    self.assertGreater(len(option_id), 1, (path, question["id"]))
                texts = [option["text"].strip() for option in question["options"]]
                self.assertTrue(all(texts), (path, question["id"]))
                self.assertEqual(len(set(texts)), 4, (path, question["id"]))
                self.assertEqual(len(options), len(set(options)))
                self.assertIn(question["answer"], options)
                self.assertTrue(question["explanation"])
                for text in texts:
                    self.assertNotRegex(text, r"^[A-D]\. ", (path, question["id"]))
                self.assertNotRegex(question["explanation"], r"(^|\s)[A-D]: ", (path, question["id"]))
            self.assertIsInstance(CourseQuiz.from_yaml(path), CourseQuiz)

    def test_quiz_four_choices_and_feedback_render(self):
        from dw_course.quiz import CourseQuiz

        for path in (COURSE_ROOT / "level1").glob("*/quiz*.yaml"):
            quiz = CourseQuiz.from_yaml(path)
            for index, question in enumerate(quiz.questions):
                for option in question.options:
                    with self.subTest(path=path.name, question=question.question_id,
                                      option=option.option_id):
                        quiz._current = index
                        quiz._answers.clear()
                        quiz._render_question()
                        _, choices, feedback, controls = quiz._root.children[0].children
                        self.assertEqual(
                            list(choices.options),
                            [(item.text, item.option_id) for item in question.options],
                        )
                        self.assertEqual(len(choices.options), 4)
                        choices.value = option.option_id
                        controls.children[1].click()
                        self.assertEqual(quiz._answers[question.question_id], option.option_id)
                        self.assertEqual(
                            "Not quite." in feedback.value, option.option_id != question.answer
                        )
                        self.assertIn(escape(question.explanation), feedback.value)

    def test_learner_table_names_and_upstream_references(self):
        for path in COURSE_ROOT.rglob("*"):
            if path.suffix not in {".md", ".yaml", ".ipynb", ".py"}:
                continue
            if any(part in {".runtime", ".venv", ".ipynb_checkpoints"} for part in path.parts):
                continue
            self.assertNotRegex(path.read_text(), r"\bd[0-9]{2}[a-z]?_", path)

        sources = {}
        for path in (COURSE_ROOT / "level1").glob("*/lab*.ipynb"):
            notebook = nbformat.read(path, as_version=4)
            nbformat.validate(notebook)
            code = "\n".join(cell.source for cell in notebook.cells if cell.cell_type == "code")
            ast.parse(code, filename=str(path))
            sources[path.parent.name] = code

        self.assertIn("CREATE TABLE orders_sample", sources["module01-introduction"])
        self.assertIn('target = "wwi_" + name', sources["module05-ingestion"])
        quality = sources["module06-data-quality"]
        replay = sources["module07-state-changes"]
        self.assertIn("INSERT INTO customers SELECT CustomerID, CustomerName FROM wwi_customers", quality)
        self.assertIn("CREATE VIEW orders_classified", quality)
        self.assertIn('order_ddl("orders_clean")', quality)
        self.assertIn("FROM orders_clean", replay)
        self.assertIn("INSERT INTO products SELECT StockItemID, StockItemName FROM wwi_products", replay)
        self.assertIn('("order_items", business["order_lines"])', replay)
        self.assertIn('("shipment_events", business["shipments"])', replay)
        self.assertIn("lab.insert(table, columns,", replay)
        for upstream in ("orders_clean", "customers", "wwi_customers", "wwi_products"):
            self.assertNotIn(f"DROP TABLE IF EXISTS {upstream}", replay)

    def test_local_markdown_links(self):
        for path in COURSE_ROOT.rglob("*.md"):
            if any(part in {".venv", ".runtime", ".ipynb_checkpoints"} for part in path.parts):
                continue
            for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
                if target.startswith(("https://", "http://", "#")):
                    continue
                self.assertTrue((path.parent / target.split("#")[0]).exists(), f"{path}: {target}")


    def test_notebook_markdown_links_and_covers(self):
        for path in (COURSE_ROOT / "level1").glob("*/*.ipynb"):
            notebook = nbformat.read(path, as_version=4)
            self.assertIn("DATA WAREHOUSING WITH APACHE DORIS", notebook.cells[0].source)
            self.assertIn("border-top:4px solid #0f766e", notebook.cells[0].source)
            self.assertNotIn("10 million", notebook.cells[0].source, path)
            for cell in notebook.cells:
                if cell.cell_type != "markdown":
                    continue
                for target in re.findall(r"\]\(([^)]+)\)", cell.source):
                    if target.startswith(("https://", "http://", "#")):
                        continue
                    self.assertTrue((path.parent / target.split("#")[0]).exists(), f"{path}: {target}")


class AlignmentTest(unittest.TestCase):
    def test_learner_root_excludes_maintenance_materials(self):
        for name in ("PR_DRAFT.md", "VALIDATION.md", "integration-backlog.md"):
            self.assertFalse((COURSE_ROOT / name).exists(), name)

    def test_d01_teaches_explicit_sql_matching_order_contract(self):
        path = COURSE_ROOT / "level1/module01-introduction/lab01_connect_and_query.ipynb"
        notebook = nbformat.read(path, as_version=4)
        statements = []
        for cell in notebook.cells:
            if cell.cell_type != "code":
                continue
            for node in ast.walk(ast.parse(cell.source)):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "execute"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                ):
                    statements.append(node.args[0].value)
        create, = [sql for sql in statements if sql.lstrip().startswith("CREATE TABLE")]
        self.assertEqual(
            re.sub(r"\s+", "", create),
            re.sub(r"\s+", "", history_ddl("orders_sample")),
        )
        insert, = [sql for sql in statements if sql.lstrip().startswith("INSERT INTO")]
        header, values = insert.split("VALUES", 1)
        columns = header[header.index("(") + 1:header.index(")")].split(",")
        self.assertEqual(tuple(column.strip() for column in columns), HISTORY_COLUMNS)
        rows = ast.literal_eval("[" + values.strip() + "]")
        actual = []
        for row in rows:
            record = dict(zip(HISTORY_COLUMNS, row))
            for column in ("order_amount",):
                record[column] = format(Decimal(str(record[column])), ".2f")
            actual.append(record)
        self.assertEqual([tuple(r[col] for col in HISTORY_COLUMNS) for r in actual], history_rows())

    def test_d01_initialization_is_separate_from_connection(self):
        path = COURSE_ROOT / "level1/module01-introduction/lab01_connect_and_query.ipynb"
        notebook = nbformat.read(path, as_version=4)
        initialize, = [cell for cell in notebook.cells if cell.id == "initialize"]
        calls = [
            node.func.id
            for node in ast.walk(ast.parse(initialize.source))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        self.assertNotIn("WarehouseLab", calls)
        self.assertNotIn("prepare_environment", calls)
        self.assertIn("install_styles", calls)
        source = "\n".join(cell.source for cell in notebook.cells)
        self.assertNotIn("10 million", source)
        self.assertNotIn("order_ddl(", source)
        self.assertIn("Practice:", source)
        self.assertIn("3944.20", source)
        self.assertIn("8276.40", source)

    def test_display_components_are_reused(self):
        from doris_labkit import results, ui as labkit_ui
        from dw_course import ui
        self.assertIs(ui.show_frame, results.show_frame)
        self.assertIs(ui.card, labkit_ui.card)
        self.assertIs(ui.install_styles, labkit_ui.install_styles)
        self.assertIs(ui.workflow_html, labkit_ui.workflow_html)

    def test_sql_keeps_column_names(self):
        lab = WarehouseLab.__new__(WarehouseLab)
        cursor = Mock()
        cursor.description = [("order_id",), ("amount",)]
        cursor.fetchall.return_value = [(1001, Decimal("100.00"))]
        manager = Mock()
        manager.__enter__ = Mock(return_value=cursor)
        manager.__exit__ = Mock(return_value=False)
        lab.connection = Mock()
        lab.connection.cursor.return_value = manager
        with patch("dw_course.runtime.in_notebook", return_value=True), patch("dw_course.runtime.show_sql"), patch("dw_course.runtime.show_frame") as show:
            frame = lab.sql("SELECT order_id, amount FROM example")
        self.assertEqual(list(frame.columns), ["order_id", "amount"])
        self.assertEqual(frame.iloc[0]["amount"], Decimal("100.00"))
        show.assert_called_once()

    def test_sql_can_limit_the_columns_it_shows_and_returns(self):
        lab = WarehouseLab.__new__(WarehouseLab)
        cursor = Mock()
        cursor.description = [("TabletId",), ("Version",), ("MetaUrl",)]
        cursor.fetchall.return_value = [(1, 11, "http://127.0.0.1:8040/api/meta/header/1")]
        manager = Mock()
        manager.__enter__ = Mock(return_value=cursor)
        manager.__exit__ = Mock(return_value=False)
        lab.connection = Mock()
        lab.connection.cursor.return_value = manager
        with patch("dw_course.runtime.in_notebook", return_value=True), patch("dw_course.runtime.show_sql"), \
                patch("dw_course.runtime.show_frame") as show:
            frame = lab.sql("SHOW TABLETS FROM orders_batch", columns=["TabletId", "Version", "Missing"])
        self.assertEqual(list(frame.columns), ["TabletId", "Version"])
        self.assertEqual(list(show.call_args.args[1].columns), ["TabletId", "Version"])

    def test_sql_keeps_nullable_integers_and_reports_errors(self):
        import pymysql

        lab = WarehouseLab.__new__(WarehouseLab)
        cursor = Mock()
        cursor.description = [("customer_id",)]
        cursor.fetchall.return_value = [(42,), (None,)]
        manager = Mock()
        manager.__enter__ = Mock(return_value=cursor)
        manager.__exit__ = Mock(return_value=False)
        lab.connection = Mock()
        lab.connection.cursor.return_value = manager
        with patch("dw_course.runtime.in_notebook", return_value=True), patch("dw_course.runtime.show_sql"), patch("dw_course.runtime.show_frame"):
            frame = lab.sql("SELECT customer_id FROM orders_clean")
        self.assertEqual(str(frame["customer_id"].dtype), "Int64")
        self.assertEqual(frame["customer_id"].iloc[0], 42)
        cursor.execute.side_effect = pymysql.err.ProgrammingError(1105, "errCode = 2, detailMessage = Unknown table 'missing'")
        with patch("dw_course.runtime.in_notebook", return_value=True), patch("dw_course.runtime.show_sql"), \
             patch("dw_course.runtime.report_sql_error") as report:
            with self.assertRaises(pymysql.err.ProgrammingError):
                lab.sql("SELECT * FROM missing", title="Missing table")
        report.assert_called_once()
        self.assertEqual(report.call_args.args[0], "Missing table")

    def test_compose_scope_and_persistence(self):
        from dw_course.docker_runtime import COMPOSE_FILE, PROJECT
        config = yaml.safe_load(COMPOSE_FILE.read_text())
        self.assertEqual(config["name"], PROJECT)
        self.assertEqual(set(config["services"]), {"doris"})
        service = config["services"]["doris"]
        self.assertEqual(service["image"], "apache/doris:all-in-one-4.1.3")
        self.assertEqual(service["ports"], ["127.0.0.1:${DW_FE_QUERY_PORT:-52030}:9030",
                                            "127.0.0.1:${DW_FE_HTTP_PORT:-51030}:8030",
                                            "127.0.0.1:${DW_BE_HTTP_PORT:-51040}:8040"])
        self.assertEqual(set(config["volumes"]), {"fe-meta", "be-storage"})

    def test_compose_files_and_runtime_use_the_same_port_variables(self):
        from dw_course.environment import LAKE_PORTS, SANDBOX_PORTS
        for name, ports in (("single-node", SANDBOX_PORTS), ("lakehouse", LAKE_PORTS)):
            text = (COURSE_ROOT / "environments" / name / "compose.yml").read_text()
            published = dict(re.findall(r'"127\.0\.0\.1:\$\{(DW_\w+):-(\d+)\}:\d+"', text))
            with self.subTest(environment=name):
                # Every host port is a variable, with the default of dw_course/environment.py.
                self.assertEqual(published, {variable: str(default) for variable, (default, _) in ports.items()})
                self.assertNotRegex(text, r'"127\.0\.0\.1:\d+:\d+"')

    def test_port_variables_move_the_connection(self):
        from dw_course.environment import connection_settings
        with patch.dict("os.environ", {"DW_FE_QUERY_PORT": "62030", "DW_FE_HTTP_PORT": "61030",
                                       "DW_BE_HTTP_PORT": "61040"}, clear=True):
            settings = connection_settings()
        self.assertEqual(settings["DW_PORT"], "62030")
        self.assertEqual(settings["DW_FE_HTTP_URL"], "http://127.0.0.1:61030")
        self.assertEqual(settings["DW_BE_HTTP_URL"], "http://127.0.0.1:61040")
        with patch.dict("os.environ", {"DW_FE_QUERY_PORT": "port 9030"}, clear=True):
            with self.assertRaises(ValueError):
                connection_settings()

    def test_busy_port_stops_before_any_container_starts(self):
        from dw_course.docker_runtime import prepare_environment
        from dw_course.onboarding import SetupRequired
        with patch.dict("os.environ", {}, clear=True), patch("subprocess.run", return_value=Mock(stdout="")) as run, \
                patch("dw_course.docker_runtime.port_in_use", side_effect=lambda number: number == 51040), \
                patch("pymysql.connect") as connect:
            with self.assertRaises(SetupRequired) as raised:
                prepare_environment(start=True)
        message = str(raised.exception)
        self.assertIn("51040 (DW_BE_HTTP_PORT", message)
        self.assertIn("lsof -nP -iTCP:51040 -sTCP:LISTEN", message)
        self.assertIn("`DW_BE_HTTP_PORT=61040 .venv/bin/jupyter lab`", message)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertFalse(any("up" in command for command in commands))
        connect.assert_not_called()

    def test_lake_statement_waits_only_while_doris_cannot_reach_the_services(self):
        import pymysql
        from dw_course.lakehouse import _execute_when_reachable
        lab, progress = Mock(), Mock()
        refused = pymysql.err.OperationalError(1105, "Connect to http://course-lake-rest:8181 failed: Connection refused")
        lab.execute.side_effect = [refused, 1]
        with patch("time.sleep") as sleep:
            self.assertEqual(_execute_when_reachable(lab, "CREATE DATABASE IF NOT EXISTS lake.db", progress), 1)
        sleep.assert_called_once_with(3)
        # Any other error, or a refusal that outlasts the timeout, is a real failure.
        lab.execute.side_effect = pymysql.err.OperationalError(1105, "Access denied")
        with self.assertRaisesRegex(pymysql.err.OperationalError, "Access denied"):
            _execute_when_reachable(lab, "CREATE DATABASE IF NOT EXISTS lake.db", progress)
        lab.execute.side_effect = refused
        with patch("time.sleep"), patch("time.monotonic", side_effect=[0, 61]):
            with self.assertRaisesRegex(pymysql.err.OperationalError, "Connection refused"):
                _execute_when_reachable(lab, "CREATE DATABASE IF NOT EXISTS lake.db", progress)

    def test_ports_of_the_running_course_container_are_not_a_conflict(self):
        from dw_course.docker_runtime import check_host_ports
        from dw_course.environment import SANDBOX_PORTS
        progress = Mock(logs=[])
        with patch.dict("os.environ", {}, clear=True), \
                patch("dw_course.docker_runtime.published_ports", return_value={52030, 51030, 51040}), \
                patch("dw_course.docker_runtime.port_in_use", return_value=True):
            check_host_ports(SANDBOX_PORTS, "doris-warehousing-course", progress)
        self.assertIn("used by this course", progress.log.call_args_list[0].args[0])

    def test_object_storage_is_pinned_silo_reached_by_its_aliases(self):
        # minio/minio is no longer on Docker Hub; both helper environments run Silo.
        services = {name: yaml.safe_load((COURSE_ROOT / "environments" / name / "compose.yml").read_text())["services"]["silo"]
                    for name in ("lakehouse", "backup")}
        self.assertRegex(services["lakehouse"]["image"], r"^pgsty/silo:RELEASE\.\d{4}-\d\d-\d\dT\d\d-\d\d-\d\dZ$")
        self.assertEqual(services["backup"]["image"], services["lakehouse"]["image"])
        aliases = {name: service["networks"]["default"]["aliases"] for name, service in services.items()}
        self.assertEqual(aliases, {"lakehouse": ["course-lake-silo"], "backup": ["course-backup-silo"]})
        # Doris, the REST fixture and the notebooks reach the store only through these aliases.
        hosts = set()
        for path in COURSE_ROOT.rglob("*"):
            parts = path.relative_to(COURSE_ROOT).parts
            hidden = any(part.startswith(".") for part in parts)
            if path.suffix in {".py", ".yml", ".ipynb", ".md"} and not hidden and parts[0] != "tests":
                text = path.read_text()
                self.assertNotRegex(text, r"minio/minio|course-[a-z]+-minio", path)
                hosts.update(re.findall(r"http://(course-[\w-]+):9000", text))
        self.assertEqual(hosts, {"course-lake-silo", "course-backup-silo"})

    def test_docker_start_requires_explicit_opt_in(self):
        from dw_course.docker_runtime import prepare_environment
        with patch.dict("os.environ", {}, clear=True), patch("subprocess.run") as run:
            with self.assertRaises(RuntimeError):
                prepare_environment()
            run.assert_not_called()

    def test_docker_start_checks_health_before_connection(self):
        from dw_course.docker_runtime import prepare_environment, compose_command
        from dw_course.environment import connection_settings
        cursor = Mock()
        cursor.fetchone.side_effect = [(1,), (45,)]
        manager = Mock()
        manager.__enter__ = Mock(return_value=cursor)
        manager.__exit__ = Mock(return_value=False)
        connection = Mock()
        connection.cursor.return_value = manager
        with patch.dict("os.environ", {"DW_START_SANDBOX": "yes"}, clear=True), patch("subprocess.run", return_value=Mock(stdout="")) as run, \
                patch("dw_course.docker_runtime.port_in_use", return_value=False), patch("pymysql.connect", return_value=connection):
            self.assertEqual(prepare_environment(), connection_settings())
            self.assertEqual(run.call_args_list[2].args[0], compose_command("config", "--quiet"))
            self.assertEqual(run.call_args_list[3].args[0][:3], ["docker", "ps", "--quiet"])
            self.assertEqual(run.call_args_list[4].args[0], compose_command("pull", "--policy", "missing"))
            self.assertEqual(run.call_args_list[5].args[0], compose_command("up", "-d", "--wait", "--wait-timeout", "300"))
            self.assertEqual(run.call_args_list[6].args[0], compose_command("ps"))
            self.assertEqual(cursor.execute.call_args_list[-1].args[0],
                             'SELECT SUM(number) FROM numbers("number"="10")')
            connection.close.assert_called_once()

    def test_notebooks_use_one_sandbox_without_environment_selection(self):
        for path in (COURSE_ROOT / "level1").glob("*/lab*.ipynb"):
            notebook = nbformat.read(path, as_version=4)
            code = "\n".join(c.source for c in notebook.cells if c.cell_type == "code")
            self.assertRegex(code, r"lab = connect_sandbox\(\)" if path.parent.name not in {"module06-data-quality", "module07-state-changes"} else r"lab = connect_sandbox\(module=[67]\)", path)
            self.assertNotIn("USE_DOCKER", code, path)
            self.assertNotIn("FE_HOST =", code, path)
            self.assertNotIn("ALLOW_LAB_WRITES =", code, path)
            if path.parent.name == "module01-introduction":
                self.assertIn("prepare_environment(start=True)", code)
            else:
                self.assertNotIn("prepare_environment(", code, path)

    def test_fresh_notebook_connection_uses_sandbox_not_stale_environment(self):
        from dw_course.docker_runtime import connect_sandbox
        from dw_course.environment import connection_settings
        import os
        for environment in ({}, {"DW_HOST": "another-server", "DW_PORT": "19030",
                                  "DW_BE_HTTP_URL": "http://another-server:8040",
                                  "DW_USER": "another-user", "DW_PASSWORD": "not-a-real-password"},
                            {"DW_FE_QUERY_PORT": "62030"}):
            with patch.dict(os.environ, environment, clear=True), patch(
                "dw_course.docker_runtime.WarehouseLab"
            ) as constructor, patch("subprocess.run") as run:
                self.assertIs(connect_sandbox(), constructor.return_value)
                constructor.assert_called_once_with(allow_writes=True)
                expected = connection_settings()
                self.assertEqual({key: os.environ[key] for key in expected}, expected)
                self.assertEqual(os.environ["DW_PORT"], environment.get("DW_FE_QUERY_PORT", "52030"))
                run.assert_not_called()

    def test_prerequisites_let_labs_reload_missing_wwi_tables(self):
        from dw_course.docker_runtime import _check_prerequisites
        from dw_course.onboarding import SetupRequired

        def lab_with(tables):
            lab = Mock()
            lab.database = "dw_course_l1_test"

            def query(statement):
                if statement == "SHOW TABLES":
                    return [(name,) for name in tables]
                return [(tables[statement.rsplit(" ", 1)[-1]],)]

            lab.query.side_effect = query
            return lab

        # A missing WWI table is reloaded by the lab's own setup cell.
        _check_prerequisites(lab_with({}), 6)
        _check_prerequisites(lab_with({"customers": 663, "orders_clean": 10}), 7)
        # An incomplete copy is reused without modification, so it must stop the lab.
        for module, tables, blocked, steps in (
            (6, {"wwi_customers": 600}, "wwi_customers is", "Complete Lab 5 (historical import) in"),
            (7, {"wwi_products": 200, "customers": 663, "orders_clean": 10}, "wwi_products is",
             "Complete Lab 5 (historical import) in"),
            (7, {"wwi_products": 227}, "customers, orders_clean are", "Complete Lab 6 (quality checks) in"),
        ):
            with self.subTest(module=module, tables=tables):
                with self.assertRaises(SetupRequired) as raised:
                    _check_prerequisites(lab_with(tables), module)
                self.assertIn(blocked, str(raised.exception))
                self.assertIn(steps, str(raised.exception))

    def test_explicit_sandbox_start_and_be_readiness(self):
        from dw_course.docker_runtime import prepare_environment
        cursor = Mock()
        cursor.fetchone.side_effect = [(1,), (45,)]
        connection = Mock()
        connection.cursor.return_value.__enter__ = Mock(return_value=cursor)
        connection.cursor.return_value.__exit__ = Mock(return_value=False)
        with patch.dict("os.environ", {}, clear=True), patch("subprocess.run", return_value=Mock(stdout="")), patch(
            "dw_course.docker_runtime.port_in_use", return_value=False), patch("pymysql.connect", return_value=connection
        ):
            prepare_environment(start=True)
        connection.close.assert_called_once()

    def test_sandbox_health_failure_does_not_connect(self):
        from dw_course.docker_runtime import prepare_environment
        import subprocess
        with patch("subprocess.run", side_effect=[
            *[Mock(stdout="") for _ in range(5)], subprocess.CalledProcessError(1, "up")
        ]), patch("dw_course.docker_runtime.port_in_use", return_value=False), patch(
            "pymysql.connect"
        ) as connect:
            with self.assertRaises(subprocess.CalledProcessError):
                prepare_environment(start=True)
            connect.assert_not_called()

    def test_sandbox_be_failure_does_not_publish_connection(self):
        from dw_course.docker_runtime import prepare_environment
        import os
        cursor = Mock()
        cursor.fetchone.side_effect = [(1,), (None,)]
        connection = Mock()
        connection.cursor.return_value.__enter__ = Mock(return_value=cursor)
        connection.cursor.return_value.__exit__ = Mock(return_value=False)
        with patch.dict(os.environ, {"DW_PORT": "19030"}, clear=True), patch(
            "subprocess.run", return_value=Mock(stdout="")
        ), patch("dw_course.docker_runtime.port_in_use", return_value=False), patch("pymysql.connect", return_value=connection):
            with self.assertRaisesRegex(RuntimeError, "BE execution"):
                prepare_environment(start=True)
            self.assertEqual(os.environ["DW_PORT"], "19030")
        connection.close.assert_called_once()

    def test_startup_workflow_success_uses_shared_panel(self):
        from dw_course.ui import WorkflowProgress
        from dw_course.docker_runtime import STARTUP_STEPS
        with patch("dw_course.ui.in_notebook", return_value=True), patch(
            "dw_course.ui.display"
        ) as display, patch("dw_course.ui.show_log") as log:
            progress = WorkflowProgress("Prepare the Doris lab environment", STARTUP_STEPS)
            for step in STARTUP_STEPS:
                progress.advance(step)
            progress.finish()
            display.assert_called_once()
            panel = display.return_value.update.call_args.args[0].data
            self.assertEqual(panel.count('doris-workflow-item success'), 6)
            self.assertIn("<span>Completed</span>", panel)
            self.assertIn("width:100%", panel)
            self.assertNotIn("failure", panel)
            log.assert_called_once()
            self.assertEqual(log.call_args.args[0], "View complete startup logs")

    def test_successful_subprocess_stderr_is_kept_in_folded_log(self):
        from dw_course.docker_runtime import _run, STARTUP_STEPS
        from dw_course.ui import WorkflowProgress
        with patch("dw_course.ui.in_notebook", return_value=True), patch(
            "dw_course.ui.display"
        ), patch("dw_course.ui.show_log") as log:
            progress = WorkflowProgress("Prepare the Doris lab environment", STARTUP_STEPS)
            _run([
                sys.executable, "-c",
                "import sys; print('Container Healthy', file=sys.stderr)",
            ], progress)
            self.assertEqual(progress.logs[-1], "Container Healthy\n")
            progress.finish()
            self.assertIn("Container Healthy", log.call_args.args[1])
            self.assertFalse(log.call_args.kwargs.get("opened", False))

    def test_startup_workflow_failure_keeps_remaining_steps_pending(self):
        import subprocess
        from dw_course.docker_runtime import prepare_environment
        error = subprocess.CalledProcessError(
            1, "up", output="bind: address already in use <script>"
        )
        with patch("dw_course.ui.in_notebook", return_value=True), patch(
            "dw_course.ui.display"
        ) as display, patch("dw_course.ui.show_log") as log, patch(
            "subprocess.run", side_effect=[*[Mock(stdout="") for _ in range(5)], error]
        ), patch("dw_course.docker_runtime.port_in_use", return_value=False), patch("pymysql.connect") as connect:
            with self.assertRaises(subprocess.CalledProcessError):
                prepare_environment(start=True)
            panel = display.return_value.update.call_args.args[0].data
            self.assertEqual(panel.count("doris-workflow-item success"), 3)
            self.assertEqual(panel.count("doris-workflow-item failure"), 1)
            self.assertEqual(panel.count("doris-workflow-item pending"), 2)
            self.assertIn("<span>Failed</span>", panel)
            self.assertIn("width:50%", panel)
            self.assertIn("address already in use", panel)
            self.assertNotIn("<script>", panel)
            self.assertIn("&lt;script&gt;", panel)
            self.assertIn("address already in use", log.call_args.args[1])
            self.assertTrue(log.call_args.kwargs["opened"])
            connect.assert_not_called()

    def test_startup_workflow_timeout_marks_current_step_failed(self):
        import subprocess
        from dw_course.docker_runtime import prepare_environment
        error = subprocess.TimeoutExpired("pull", 1800, output=b"download stalled")
        with patch("dw_course.ui.in_notebook", return_value=True), patch(
            "dw_course.ui.display"
        ) as display, patch("dw_course.ui.show_log"), patch(
            "subprocess.run", side_effect=[*[Mock(stdout="") for _ in range(4)], error]
        ), patch("dw_course.docker_runtime.port_in_use", return_value=False), patch("pymysql.connect") as connect:
            with self.assertRaises(subprocess.TimeoutExpired):
                prepare_environment(start=True)
            panel = display.return_value.update.call_args.args[0].data
            self.assertEqual(panel.count("doris-workflow-item success"), 2)
            self.assertEqual(panel.count("doris-workflow-item failure"), 1)
            self.assertEqual(panel.count("doris-workflow-item pending"), 3)
            self.assertIn("download stalled", panel)
            connect.assert_not_called()

    def test_explicit_write_confirmation_still_requires_scoped_database(self):
        with patch.dict("os.environ", {"DW_DATABASE": "production"}, clear=True), patch(
            "pymysql.connect"
        ) as connect:
            with self.assertRaises(ValueError):
                WarehouseLab(allow_writes=True)
            connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
