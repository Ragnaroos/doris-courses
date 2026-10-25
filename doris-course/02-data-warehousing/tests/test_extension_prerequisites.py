"""An extension must stop before resetting its tables when input is missing."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dw_course import docker_runtime as docker
from dw_course.onboarding import SetupRequired


class ExtensionPrerequisitesTest(unittest.TestCase):
    def test_extension_setup_uses_the_guard(self):
        notebook = json.loads((ROOT / "level1/extensions/extension67_schema_and_delete.ipynb").read_text())
        setup = next("".join(c["source"]) for c in notebook["cells"] if c["id"] == "extension67_schema_and_delete-1")
        self.assertIn('lab = connect_sandbox(module="extension67")', setup)

    def test_missing_or_incomplete_input_closes_connection_without_resetting_tables(self):
        for existing, count in (([], 0), ([("orders_clean",), ("ext_schema",)], 9)):
            lab = Mock(database="dw_course_l1_test")
            lab.query.side_effect = lambda sql: existing if sql == "SHOW TABLES" else [(count,)]
            with patch.object(docker, "WarehouseLab", return_value=lab):
                with self.assertRaises(SetupRequired) as raised:
                    docker.connect_sandbox(module="extension67")
            self.assertIn("Lab 6", str(raised.exception))
            self.assertIn("No lab tables have been reset", str(raised.exception))
            self.assertIn(("Open Lab 6", "level1/module06-data-quality/lab06_validate_orders.ipynb"), raised.exception.links)
            lab.execute.assert_not_called()
            lab.close.assert_called_once()

    def test_complete_input_needs_no_lab7_tables(self):
        lab = Mock(database="dw_course_l1_test")
        lab.query.side_effect = [[("orders_clean",)], [(10,)]]
        with patch.object(docker, "WarehouseLab", return_value=lab):
            self.assertIs(docker.connect_sandbox(module="extension67"), lab)
        lab.execute.assert_not_called()
        lab.close.assert_not_called()


if __name__ == "__main__":
    unittest.main()
