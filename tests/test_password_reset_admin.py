import importlib
import sys
import types
import unittest
from unittest.mock import patch


fake_config = types.ModuleType("src.database.config")
fake_config.get_secret = lambda _key, default="": default
fake_config.supabase = object()
fake_config.supabase_admin = object()
sys.modules["src.database.config"] = fake_config
database = importlib.import_module("src.database.db")


class FakeResponse:
    data = True


class FakeRpc:
    def __init__(self):
        self.name = None
        self.params = None

    def execute(self):
        return FakeResponse()


class FakeAdminClient:
    def __init__(self):
        self.call = FakeRpc()

    def rpc(self, name, params):
        self.call.name = name
        self.call.params = params
        return self.call


class FakeDatabaseError(Exception):
    code = "42P01"


class FakeFailingInsert:
    def execute(self):
        raise FakeDatabaseError("details that must not be logged")


class FakePasswordResetTable:
    def insert(self, _data):
        return FakeFailingInsert()


class FakeInsertClient:
    def table(self, name):
        if name != "password_resets":
            raise AssertionError("Unexpected table access")
        return FakePasswordResetTable()


class FakeQuery:
    def __init__(self, data):
        self.data = data
        self.filters = []

    def select(self, columns):
        self.columns = columns
        return self

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def execute(self):
        return types.SimpleNamespace(data=self.data)


class FakeEnrollmentClient:
    def __init__(self, owns_subject=True):
        self.owns_subject = owns_subject
        self.table_names = []

    def table(self, name):
        self.table_names.append(name)
        if name == "subjects":
            data = [{"subject_id": 8}] if self.owns_subject else []
        elif name == "subject_students":
            data = [{
                "student_id": 17,
                "students": {"student_id": 17, "name": "Student"}
            }]
        else:
            raise AssertionError(f"Unexpected table: {name}")
        return FakeQuery(data)


class PasswordResetAdminTests(unittest.TestCase):
    def test_password_reset_uses_atomic_server_side_rpc(self):
        admin_client = FakeAdminClient()
        with (
            patch.object(database, "supabase_admin", admin_client),
            patch.object(
                database,
                "verify_password_reset_token",
                return_value=(True, 17, "Token is valid.")
            )
        ):
            success, message = database.reset_teacher_password(
                "one-time-token",
                "StrongPass123"
            )

        self.assertTrue(success, message)
        self.assertEqual(
            admin_client.call.name,
            "redeem_teacher_password_reset"
        )
        self.assertEqual(
            admin_client.call.params["p_token_hash"],
            database.hash_token("one-time-token")
        )
        self.assertNotEqual(
            admin_client.call.params["p_password_hash"],
            "StrongPass123"
        )

    def test_password_reset_fails_closed_without_service_role(self):
        with patch.object(database, "supabase_admin", None):
            with self.assertRaisesRegex(RuntimeError, "service role"):
                database._get_password_reset_client()

    def test_password_reset_logs_safe_database_code_when_token_insert_fails(self):
        with (
            patch.object(database, "supabase_admin", FakeInsertClient()),
            patch.object(
                database,
                "find_teacher_by_email_or_username",
                return_value={
                    "teacher_id": 17,
                    "email": "teacher@example.com",
                    "name": "Teacher"
                }
            ),
            patch.object(database.logger, "error") as log_error
        ):
            success, message, raw_token, _email_status = (
                database.request_password_reset("teacher@example.com")
            )

        self.assertFalse(success)
        self.assertEqual(
            message,
            "Password reset is temporarily unavailable."
        )
        self.assertIsNone(raw_token)
        self.assertEqual(log_error.call_args.args[2], "42P01")
        self.assertNotIn(
            "details that must not be logged",
            str(log_error.call_args)
        )

    def test_teacher_enrollment_lookup_uses_admin_and_checks_ownership(self):
        admin_client = FakeEnrollmentClient()
        with patch.object(database, "supabase_admin", admin_client):
            students = database.get_enrolled_students_for_teacher(4, 8)

        self.assertEqual(students[0]["student_id"], 17)
        self.assertEqual(
            admin_client.table_names,
            ["subjects", "subject_students"]
        )

    def test_teacher_cannot_fetch_enrollments_for_another_teachers_subject(self):
        admin_client = FakeEnrollmentClient(owns_subject=False)
        with patch.object(database, "supabase_admin", admin_client):
            with self.assertRaisesRegex(PermissionError, "not authorized"):
                database.get_enrolled_students_for_teacher(4, 8)

        self.assertEqual(admin_client.table_names, ["subjects"])


if __name__ == "__main__":
    unittest.main()
