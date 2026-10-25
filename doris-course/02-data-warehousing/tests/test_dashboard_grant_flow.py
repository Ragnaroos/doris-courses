"""Distinguish a missing dashboard, its first grant migration, and a rerun."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

import pymysql
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dw_course.runtime import expect

SOURCE = next("".join(c["source"]) for c in json.loads(next(ROOT.rglob("lab12_*.ipynb")).read_text())["cells"] if c["id"] == "direct-grant")
ACCOUNT = "'course_bi_test'@'%'"
PRIVILEGE = "internal.dw_course_l1_test.bi_paid_kpis_l2: Select_priv"


class DashboardGrantFlowTest(unittest.TestCase):
    def run_cell(self, rows):
        lab, card = Mock(database="dw_course_l1_test"), Mock()
        after = {"UserIdentity": ACCOUNT, "Roles": "course_bi_dashboard_l3", "TablePrivs": PRIVILEGE}
        def execute(sql):
            if sql.startswith("REVOKE") and sum(c.args[0].startswith("REVOKE") for c in lab.execute.call_args_list) == 2:
                raise pymysql.err.OperationalError(1105, "does not exist in role default_role_rbac_course_bi_test@%")
        lab.execute.side_effect = execute
        grants = lambda sql: rows if sql == "SHOW ALL GRANTS" else [after]
        exec(compile(SOURCE, "dashboard-grant", "exec"), dict(lab=lab,grants=grants,show_records=Mock(),show_sql=Mock(),card=card,pymysql=pymysql,expect=expect))
        return lab, card

    def test_no_dashboard_does_not_change_grants(self):
        lab, card = self.run_cell([])
        lab.execute.assert_not_called()
        self.assertEqual(card.call_args.args[2], "No dashboard account")

    def test_first_migration_grants_role_before_revoking_direct_access(self):
        lab, card = self.run_cell([{"UserIdentity":ACCOUNT,"Roles":"","TablePrivs":PRIVILEGE}])
        statements = [c.args[0] for c in lab.execute.call_args_list]
        self.assertLess(next(i for i,s in enumerate(statements) if s.startswith("GRANT '")), next(i for i,s in enumerate(statements) if s.startswith("REVOKE")))
        self.assertEqual(sum(s.startswith("REVOKE") for s in statements), 2)
        card.assert_not_called()

    def test_migrated_dashboard_rerun_reports_existing_role(self):
        lab, card = self.run_cell([{"UserIdentity":ACCOUNT,"Roles":"course_bi_dashboard_l3","TablePrivs":PRIVILEGE}])
        lab.execute.assert_not_called()
        self.assertEqual(card.call_args.args[2], "Already migrated")
        self.assertNotIn("not built", card.call_args.args[0])

    def test_dashboard_in_another_database_is_not_misclassified(self):
        lab, card = self.run_cell([{"UserIdentity":ACCOUNT,"Roles":"course_bi_dashboard_l3","TablePrivs":"internal.dw_course_l1_other.bi_paid_kpis_l2: Select_priv"}])
        lab.execute.assert_not_called()
        self.assertEqual(card.call_args.args[2], "No dashboard account")


if __name__ == "__main__":
    unittest.main()
