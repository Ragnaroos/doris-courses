"""Failure boundaries for real audit evidence and repository preparation."""

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from botocore.exceptions import ClientError

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dw_course import backup, operations


class AuditTest(unittest.TestCase):
    def test_audit_records_read_only_the_users_tagged_queries(self):
        lab = Mock()
        rows = [('reader', 'dw_course_l1_test', 'EOF', 0, 1, 'real-id', "SELECT 'our-tag', COUNT(*) FROM approved_view")]
        lab.query.side_effect = [[], rows]
        with patch.object(operations, 'wait_for', side_effect=lambda read, accepts, **kw: [read(), read()][-1]):
            operations.audit_records(lab, ['reader', 'other_reader'], 'our-tag', expected=1)
        statement, params = lab.query.call_args.args
        self.assertIn('FROM __internal_schema.audit_log', statement)
        self.assertIn('`user` IN (%s, %s) AND stmt LIKE %s', statement)
        self.assertEqual(params, ('reader', 'other_reader', '%our-tag%'))
        self.assertEqual(lab.sql.call_args.args, (statement, params))

    def test_audit_waits_for_every_expected_query(self):
        accepted = {}
        def wait_for(read, accepts, **kw):
            accepted['one'] = accepts([('a',)])
            accepted['two'] = accepts([('a',), ('b',)])
            return read()
        with patch.object(operations, 'wait_for', side_effect=wait_for):
            operations.audit_records(Mock(), ['reader'], 'tag', expected=2)
        self.assertEqual(accepted, {'one': False, 'two': True})

    def test_user_names_must_be_identifiers(self):
        with self.assertRaises(ValueError):
            operations.audit_records(Mock(), ["reader' OR '1'='1"], 'tag', expected=1)


class TemporaryUserTest(unittest.TestCase):
    def test_the_user_is_dropped_even_when_a_check_fails(self):
        from dw_course import access
        lab = Mock()
        with patch.object(access, 'in_notebook', return_value=True), patch.object(access, 'show_sql') as shown:
            with self.assertRaises(AssertionError):
                with access.temporary_user(lab, 'course_bi_reader_l3') as reader:
                    raise AssertionError('a failed check')
        statements = [call.args[0] for call in lab.execute.call_args_list]
        self.assertTrue(statements[0].startswith(f"CREATE USER '{reader.name}'@'%%' IDENTIFIED BY %s"))
        password = lab.execute.call_args_list[0].args[1][0]
        self.assertEqual(statements[1], f"GRANT 'course_bi_reader_l3' TO '{reader.name}'@'%'")
        self.assertEqual(statements[-1], f"DROP USER IF EXISTS '{reader.name}'@'%'")
        # The SQL shown to the learner never contains the generated password.
        self.assertNotIn(password, shown.call_args.args[1])

    def test_a_refusal_is_returned_and_other_errors_raised(self):
        import pymysql
        from dw_course import access
        reader = access.Reader(Mock(database='dw_course_l1_test'), 'reader', 'secret')
        with patch.object(reader, 'query', side_effect=pymysql.err.OperationalError(
                1105, 'errCode = 2, detailMessage = Access denied; you need (at least one of) the (Select_priv) privilege(s)')):
            self.assertTrue(reader.denied('SELECT 1').startswith('Access denied'))
        with patch.object(reader, 'query', return_value=[(1,)]):
            self.assertIsNone(reader.denied('SELECT 1'))
        with patch.object(reader, 'query', side_effect=pymysql.err.OperationalError(1105, 'Unknown column x')):
            with self.assertRaises(pymysql.err.OperationalError):
                reader.denied('SELECT x')


class RepositoryStorageTest(unittest.TestCase):
    def test_only_absent_bucket_is_created(self):
        client=Mock();client.head_bucket.side_effect=ClientError({'Error':{'Code':'404'}},'HeadBucket')
        with patch.object(backup,'start_service') as start,patch.object(backup.boto3,'client',return_value=client):
            self.assertIs(backup.prepare_backup_storage(Mock(),start=True),client)
            start.assert_called_once()
            client.create_bucket.assert_called_once_with(Bucket=backup.BUCKET)

    def test_existing_bucket_and_snapshots_are_not_reset(self):
        client=Mock()
        with patch.object(backup,'start_service'),patch.object(backup.boto3,'client',return_value=client):
            backup.prepare_backup_storage(Mock(),start=True)
            client.create_bucket.assert_not_called()
            client.delete_bucket.assert_not_called()

    def test_permission_failure_is_not_misreported_as_missing_bucket(self):
        client=Mock();client.head_bucket.side_effect=ClientError({'Error':{'Code':'403'}},'HeadBucket')
        with patch.object(backup,'start_service'),patch.object(backup.boto3,'client',return_value=client):
            with self.assertRaises(ClientError):backup.prepare_backup_storage(Mock(),start=True)
            client.create_bucket.assert_not_called()


class SessionRecoveryTest(unittest.TestCase):
    def test_reconnect_restores_database_timezone_and_write_mode(self):
        from dw_course.runtime import WarehouseLab
        lab = WarehouseLab.__new__(WarehouseLab)
        lab.database = 'dw_course_l1_session_test'
        lab.connection = Mock()
        lab.execute = Mock()
        lab.restore_session()
        lab.connection.ping.assert_called_once_with(reconnect=True)
        self.assertEqual([c.args[0] for c in lab.execute.call_args_list], [
            'USE dw_course_l1_session_test', "SET time_zone = '+08:00'", "SET group_commit = 'off_mode'",
        ])


if __name__=='__main__':unittest.main()
