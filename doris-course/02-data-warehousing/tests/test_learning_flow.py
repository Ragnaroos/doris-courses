"""Learner-facing checks, including expected errors and independent exercises."""

import ast
import json
import re
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dw_course import runtime
from dw_course import wwi

# Every Lab follows the course's Lab template: practices with a blank cell and a
# collapsed, runnable reference solution, and an Expected result after every step.
TEMPLATE_LABS = sorted(ROOT.glob("level*/module*/lab*.ipynb"))


class LearningFlowTest(unittest.TestCase):
    def test_restore_session_reconnects_and_reapplies_sql_settings(self):
        lab = runtime.WarehouseLab.__new__(runtime.WarehouseLab)
        lab.database = "dw_course_l1_test"
        lab.connection = Mock()
        lab.execute = Mock()

        lab.restore_session()

        lab.connection.ping.assert_called_once_with(reconnect=True)
        self.assertEqual(lab.execute.call_args_list, [
            call("USE dw_course_l1_test"),
            call("SET time_zone = '+08:00'"),
            call("SET group_commit = 'off_mode'"),
        ])

    def notebook_cells(self, module):
        path = next((ROOT / "level1" / module).glob("lab*.ipynb"))
        return {c["id"]: "".join(c["source"]) for c in json.loads(path.read_text())["cells"]}

    def reading(self, module):
        return next((ROOT / "level1" / module).glob("course*.md")).read_text()

    def test_reading_ddl_and_classification_match_lab_sql(self):
        for module, prefix in (("module03-table-design", "CREATE TABLE orders_partitioned"),
                               ("module06-data-quality", "CREATE VIEW orders_classified")):
            blocks = re.findall(r"```sql\n(.*?)```", self.reading(module), re.DOTALL)
            excerpt = next(block for block in blocks if block.startswith(prefix))
            source = "\n".join(self.notebook_cells(module).values())
            self.assertIn(" ".join(excerpt.strip().rstrip(";").split()), " ".join(source.split()))
        quality = self.reading("module06-data-quality")
        self.assertIn("CASE WHEN", quality)
        for fragment in ("WHERE reject_reason IS NULL", "WHERE reject_reason IS NOT NULL",
                         "Lightweight Schema Change", "Heavyweight Schema Change"):
            self.assertIn(fragment, quality)

    def test_profile_step_restores_session_and_lesson_explains_fields(self):
        source = self.notebook_cells("module02-architecture")["profile"]
        lab = Mock()
        for previous in ((1, 0), (0, 1)):
            lab.reset_mock()
            lab.query.return_value = [previous]
            exec(compile(source, "lab2-profile", "exec"), {"lab": lab, "show_records": Mock()})
            lab.execute.assert_any_call("SET enable_profile = true, enable_sql_cache = false")
            self.assertEqual(lab.execute.call_args.args, ("SET enable_profile = %s, enable_sql_cache = %s", previous))
        lab.scan_profile.side_effect = RuntimeError("query failed")
        with self.assertRaisesRegex(RuntimeError, "query failed"):
            exec(compile(source, "lab2-profile", "exec"), {"lab": lab, "show_records": Mock()})
        self.assertEqual(lab.execute.call_args.args, ("SET enable_profile = %s, enable_sql_cache = %s", (0, 1)))
        reading = self.reading("module02-architecture")
        for field in ("VersionCount", "CompactionStatus", "TabletId", "last_query_id()", "RowsKeyRangeFiltered"):
            self.assertIn(field, reading)

    def test_catalog_reading_matches_fixture_properties(self):
        reading = self.reading("module04-external-access")
        fixture_source = (ROOT / "dw_course/lakehouse.py").read_text()
        for fragment in ('"type"="iceberg"', '"iceberg.catalog.type"="rest"',
                         '"use_path_style"="true"', '"iceberg.rest.view-enabled"="false"'):
            self.assertIn(fragment, reading)
            self.assertIn(fragment, fixture_source)
        self.assertIn("External environment example; do not run it alongside the Lab", reading)

    def test_ingestion_keeps_the_optional_accounting_reading(self):
        reading = self.reading("module05-ingestion")
        self.assertIn('DEFAULT "CREATED"', reading)
        self.assertIn("optional05_invoice_and_receipts.md", reading)
        cells = self.notebook_cells("module05-ingestion")
        self.assertNotIn("TransactionTypeName", cells["historical-check"])
        self.assertIn("wwi_order_lines", cells["historical-check"])
        optional = (ROOT / "level1/module05-ingestion/optional05_invoice_and_receipts.md").read_text()
        self.assertIn("267011.44", optional)
        self.assertIn("TransactionTypeName", optional)
        for block in re.findall(r"```sql\n(.*?)```", optional, re.DOTALL):
            for statement in (part.strip() for part in block.split(";") if part.strip()):
                self.assertTrue(statement.startswith("SELECT"))

    def test_update_reading_teaches_operations_and_distinct_delete_mechanisms(self):
        reading = self.reading("module07-state-changes")
        for fragment in ("INSERT INTO orders_partial_update", "UPDATE orders_delete_demo",
                         "DELETE FROM orders_delete_demo", "__DORIS_DELETE_SIGN__", "Delete Bitmap",
                         "try/finally", "does not run a load deletion marker experiment"):
            self.assertIn(fragment, reading)

    def test_first_load_teaches_http_before_independent_work(self):
        cells = self.notebook_cells("module05-ingestion")
        source = cells["cell-4"]
        lab = Mock(database="dw_course_l1_test", user="root", password="")
        lab.query.return_value = [(10, "1400.00")]
        response = Mock()
        response.json.return_value = {"Status": "Success", "NumberLoadedRows": 10,
                                      "NumberFilteredRows": 0}
        namespace = {"lab": lab, "order_ddl": lambda _: "DDL", "show_sql": Mock(),
                     "show_response": Mock(), "expect": runtime.expect, "COURSE_ROOT": ROOT,
                     "ORDER_COLUMNS": ("order_id", "customer_id"), "uuid4": lambda: Mock(hex="test")}
        with patch.dict("os.environ", {"DW_BE_HTTP_URL": "http://example.invalid:8040"}), \
                patch("requests.put", return_value=response) as put:
            exec(compile(source, "first-http-load", "exec"), namespace)
        self.assertEqual(put.call_args.args[0],
                         "http://example.invalid:8040/api/dw_course_l1_test/orders_imported/_stream_load")
        args = put.call_args.kwargs
        self.assertEqual(args["headers"]["columns"], "order_id,customer_id")
        self.assertEqual(args["headers"]["label"], namespace["label"])
        self.assertEqual(args["headers"]["group_commit"], "off_mode")
        self.assertEqual(args["headers"]["max_filter_ratio"], "0")
        self.assertEqual(args["auth"], ("root", ""))
        self.assertFalse(args["allow_redirects"])
        response.raise_for_status.assert_called_once()
        lab.stream_load.assert_not_called()
        self.assertIn('label, columns)', cells["cell-6"])

    def test_sequence_ddl_is_shown_before_first_update(self):
        from dw_course.schema import order_ddl
        cells = self.notebook_cells("module07-state-changes")
        source = cells["update-walkthrough"]
        self.assertLess(source.index("show_sql("), source.index("lab.execute(ddl)"))
        self.assertLess(source.index("lab.execute(ddl)"), source.index("lab.insert("))
        for fragment in ('UNIQUE KEY(order_id)', '"function_column.sequence_col"="event_version"',
                         '"enable_unique_key_merge_on_write"="true"'):
            self.assertIn(fragment, order_ddl("orders_update_walkthrough", current=True))
            self.assertIn(fragment, cells["update-walkthrough-help"])

    def test_business_ledger_restores_only_missing_products(self):
        cells = self.notebook_cells("module07-state-changes")
        source = cells["business-ledger"].split("for attempt in range(2):", 1)[0]
        for existing in (False, True):
            with self.subTest(existing=existing):
                lab = Mock()
                lab.query.side_effect = [[("wwi_products",)] if existing else [], [(227,)]]
                lab.stream_load.return_value = {
                    "Status": "Success", "NumberLoadedRows": 227, "NumberFilteredRows": 0,
                }
                paths = Mock(return_value={"products": Path("products.parquet")})
                namespace = {
                    "lab": lab, "fixture": runtime.fixture, "expect": runtime.expect,
                    "show_sql": Mock(), "show_response": Mock(),
                    "manifest": wwi.manifest, "parquet_ddl": wwi.parquet_ddl,
                    "parquet_paths": paths, "uuid4": lambda: Mock(hex="test"),
                }
                exec(compile(source, "business-ledger-setup", "exec"), namespace)
                lab.execute.assert_any_call(
                    "INSERT INTO products SELECT StockItemID, StockItemName FROM wwi_products")
                ddl = wwi.parquet_ddl("products", "wwi_products")
                if existing:
                    paths.assert_not_called()
                    lab.stream_load.assert_not_called()
                    self.assertNotIn(ddl, [call.args[0] for call in lab.execute.call_args_list])
                else:
                    paths.assert_called_once_with()
                    lab.execute.assert_any_call(ddl)
                    lab.stream_load.assert_called_once_with(
                        "wwi_products", Path("products.parquet"), "module7_wwi_test", format="parquet")

    def test_business_ledger_stops_on_invalid_product_load(self):
        source = self.notebook_cells("module07-state-changes")["business-ledger"]
        for response in (
            {"Status": "Fail", "NumberLoadedRows": 0, "NumberFilteredRows": 0},
            {"Status": "Success", "NumberLoadedRows": 226, "NumberFilteredRows": 0},
            {"Status": "Success", "NumberLoadedRows": 227, "NumberFilteredRows": 1},
        ):
            with self.subTest(response=response):
                lab = Mock()
                lab.query.return_value = []
                lab.stream_load.return_value = response
                namespace = {
                    "lab": lab, "fixture": runtime.fixture, "expect": runtime.expect,
                    "show_sql": Mock(), "show_response": Mock(),
                    "manifest": wwi.manifest, "parquet_ddl": wwi.parquet_ddl,
                    "parquet_paths": lambda: {"products": Path("products.parquet")},
                    "uuid4": lambda: Mock(hex="test"),
                }
                with self.assertRaises(runtime.CourseCheckError):
                    exec(compile(source, "business-ledger-failed-load", "exec"), namespace)
                self.assertNotIn(
                    "INSERT INTO products SELECT StockItemID, StockItemName FROM wwi_products",
                    [call.args[0] for call in lab.execute.call_args_list])
                lab.insert.assert_not_called()

    def test_quality_negative_cases_target_uniqueness(self):
        source = self.notebook_cells("module06-data-quality")["cell-8"]
        cases = [n for n in ast.parse(source).body if isinstance(n, ast.With)]
        self.assertEqual(len(cases), 2)
        for case in cases:
            self.assertEqual(ast.unparse(case.body[0]), "check_unique_orders()")
            self.assertEqual(len(case.body), 1)

    def test_uniqueness_detects_duplicates_without_total_changes(self):
        from decimal import Decimal
        rows = runtime.fixture("orders.json")
        wrong = [dict(r) for r in rows]
        wrong[1]["order_id"] = wrong[0]["order_id"]
        self.assertEqual(len(wrong), len(rows))
        self.assertEqual(sum(Decimal(r["order_amount"]) for r in wrong),
                         sum(Decimal(r["order_amount"]) for r in rows))
        source = self.notebook_cells("module06-data-quality")["cell-8"]
        check = next(n for n in ast.parse(source).body
                     if isinstance(n, ast.FunctionDef) and n.name == "check_unique_orders")
        lab = Mock()
        namespace = {"lab": lab, "expect": runtime.expect}
        exec(compile(ast.Module(body=[check], type_ignores=[]), "uniqueness", "exec"), namespace)
        for records, duplicates in ((rows, 0), (wrong, 1), (rows + [rows[0]], 1)):
            lab.query.return_value = [(len(records) - len({r["order_id"] for r in records}),)]
            if duplicates:
                with self.assertRaises(runtime.CourseCheckError):
                    namespace["check_unique_orders"]()
            else:
                namespace["check_unique_orders"]()
            lab.query.assert_called_with(
                "SELECT COUNT(*) - COUNT(DISTINCT order_id) FROM orders_clean")

    def test_group_commit_step_sends_single_rows_without_labels(self):
        source = self.notebook_cells("module05-ingestion")["group-commit"]
        self.assertIn('if mode == "off_mode":\n        headers["label"]', source)
        self.assertIn('("orders_group_commit", "async_mode")', source)
        self.assertIn('"group_commit_interval_ms" = "2000"', source)
        reading = self.reading("module05-ingestion")
        self.assertIn("label and group_commit can't be set at the same time", reading)

    def test_every_module_has_blank_exercise_and_folded_executable_solution(self):
        self.assertEqual(len(TEMPLATE_LABS), 14)
        for path in TEMPLATE_LABS:
            cells = json.loads(path.read_text())["cells"]
            solutions = [c for c in cells if "reference-solution" in c.get("metadata", {}).get("tags", [])]
            self.assertTrue(solutions, path)
            for solution in solutions:
                # The form of the other courses: a blank cell, a pointer, then a collapsed
                # solution that runs with Run All and checks its result.
                index = cells.index(solution)
                work, pointer = cells[index - 2], cells[index - 1]
                self.assertEqual(work["cell_type"], "code", path)
                self.assertEqual(ast.parse("".join(work["source"])).body, [], path)  # comments only
                self.assertEqual("".join(pointer["source"]),
                                 "The next cell is a reference solution; it is collapsed. Expand it to compare, or run it.")
                self.assertEqual(solution["cell_type"], "code", path)
                self.assertTrue(solution["metadata"]["jupyter"]["source_hidden"], path)
                tree = ast.parse("".join(solution["source"]))
                self.assertTrue(any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                                    and n.func.id == "expect" for n in ast.walk(tree)), (path, solution["id"]))
                # Each practice ends with what a run shows.
                self.assertTrue("".join(cells[index + 1]["source"]).startswith("**Expected result"), (path, solution["id"]))
            # No answer sits in plain sight in a Markdown cell.
            for cell in cells:
                if cell["cell_type"] == "markdown":
                    self.assertNotIn("<details>", "".join(cell["source"]), path)

    def test_every_lab_step_ends_with_an_expected_result(self):
        for path in TEMPLATE_LABS:
            cells = json.loads(path.read_text())["cells"]
            for index, cell in enumerate(cells[:-1]):
                if cell["cell_type"] != "code" or index < 3 or not ast.parse("".join(cell["source"])).body:
                    continue  # the setup cell, and the blank practice cells
                following = "".join(cells[index + 1]["source"])
                with self.subTest(lab=path.name, cell=cell["id"]):
                    self.assertTrue(following.startswith("**Expected result"), following[:80])

    def test_ingestion_progresses_from_one_file_to_history(self):
        path = next((ROOT / "level1/module05-ingestion").glob("lab*.ipynb"))
        ids = [c["id"] for c in json.loads(path.read_text())["cells"]]
        self.assertLess(ids.index("cell-8"), ids.index("historical-load"))

    def test_lake_preparation_requires_explicit_start(self):
        from dw_course import lakehouse
        with patch.object(lakehouse, "_run") as run:
            with self.assertRaises(ValueError):
                lakehouse.prepare_lakehouse(None)
            run.assert_not_called()

    def test_notebooks_keep_connections_for_independent_work(self):
        for path in ROOT.glob("level*/*/lab*.ipynb"):
            for cell in json.loads(path.read_text())["cells"]:
                if cell["cell_type"] != "code":
                    continue
                tree = ast.parse("".join(cell["source"]))
                closes = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                          and isinstance(node.func, ast.Attribute)
                          and isinstance(node.func.value, ast.Name)
                          and node.func.value.id == "lab" and node.func.attr == "close"]
                self.assertEqual(closes, [], path)

    def test_expected_quality_error_has_no_failure_card(self):
        with patch.object(runtime, "in_notebook", return_value=True), patch.object(runtime, "card") as card:
            with runtime.expected_failure("Duplicate order check", "Duplicate order detected; the quality rule works"):
                runtime.expect([(11,)], [(10,)])
            self.assertEqual([call.args[1] for call in card.call_args_list], ["ok"])
            self.assertIn("Duplicate order detected", card.call_args.args[0])

    def test_missing_expected_error_is_a_real_failure(self):
        with patch.object(runtime, "in_notebook", return_value=False):
            with self.assertRaises(AssertionError):
                with runtime.expected_failure("Duplicate check", "Duplicate detected"):
                    runtime.expect([(10,)], [(10,)])

    def test_unrelated_exception_is_not_treated_as_learning_success(self):
        with patch.object(runtime, "in_notebook", return_value=True), patch.object(runtime, "card") as card:
            with self.assertRaises(RuntimeError):
                with runtime.expected_failure("Duplicate check", "Duplicate detected"):
                    raise RuntimeError("connection failed")
            card.assert_not_called()

    def test_successful_internal_checks_do_not_flood_notebook(self):
        with patch.object(runtime, "in_notebook", return_value=True), patch.object(runtime, "card") as card:
            runtime.expect([(10,)], [(10,)])
            card.assert_not_called()
            runtime.expect([(10,)], [(10,)], title="Order count as expected")
            self.assertEqual(card.call_args.args[2], "Order count as expected")


class LocalBundleTest(unittest.TestCase):
    def test_default_bundle_prepares_and_reuses_verified_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "datasets").symlink_to(ROOT / "datasets", target_is_directory=True)
            with patch.object(wwi, "COURSE_ROOT", root), patch.dict("os.environ", {}, clear=True):
                paths = wwi.parquet_paths()
                self.assertEqual(len(paths), 10)
                modified = {k: p.stat().st_mtime_ns for k, p in paths.items()}
                self.assertEqual(wwi.parquet_paths(), paths)
                self.assertEqual({k: p.stat().st_mtime_ns for k, p in paths.items()}, modified)

    def test_explicit_missing_directory_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(wwi, "_unpack_bundle") as unpack:
                with self.assertRaises(FileNotFoundError):
                    wwi.parquet_paths(Path(directory) / "missing")
                unpack.assert_not_called()

    def test_archive_members_must_be_exact_regular_files(self):
        entries = {"orders": {"bytes": 1, "sha256": "unused"}}
        for name, kind in [("../orders.parquet", tarfile.REGTYPE),
                           ("orders.parquet", tarfile.SYMTYPE)]:
            member = tarfile.TarInfo(name)
            member.type, member.size = kind, 1
            with tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / "wwi"
                with patch.object(wwi, "manifest", return_value={"tables": entries}), patch("tarfile.open") as opened:
                    opened.return_value.__enter__.return_value.getmembers.return_value = [member]
                    with self.assertRaises(ValueError):
                        wwi._unpack_bundle(target)
                    self.assertFalse(target.exists())

    def test_bad_checksum_does_not_publish_partial_bundle(self):
        bad = wwi.manifest()
        next(iter(bad["tables"].values()))["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "wwi"
            with patch.object(wwi, "manifest", return_value=bad):
                with self.assertRaises(ValueError):
                    wwi._unpack_bundle(target)
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
