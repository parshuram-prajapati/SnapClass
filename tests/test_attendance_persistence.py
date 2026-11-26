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
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, client, table_name):
        self.client = client
        self.table_name = table_name
        self.filters = {}
        self.student_ids = []
        self.payload = None

    def select(self, _columns):
        return self

    def eq(self, column, value):
        self.filters[column] = value
        return self

    def limit(self, _value):
        return self

    def in_(self, _column, values):
        self.student_ids = values
        return self

    def insert(self, payload):
        self.payload = payload
        return self

    def execute(self):
        if self.table_name == "subjects":
            data = (
                [{"subject_id": 3}]
                if self.client.owns_subject
                else []
            )
        elif self.table_name == "subject_students":
            data = [
                {"student_id": student_id}
                for student_id in self.client.enrolled_student_ids
                if student_id in self.student_ids
            ]
        elif self.table_name == "attendance_logs":
            self.client.saved_logs = self.payload
            data = self.payload
        else:
            raise AssertionError(f"Unexpected table: {self.table_name}")

        return FakeResponse(data)


class FakeAdminClient:
    def __init__(self, owns_subject=True, enrolled_student_ids=(1, 2)):
        self.owns_subject = owns_subject
        self.enrolled_student_ids = set(enrolled_student_ids)
        self.saved_logs = None

    def table(self, name):
        return FakeQuery(self, name)


class AttendancePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.logs = [
            {
                "student_id": 1,
                "subject_id": 3,
                "timestamp": "2026-11-26T12:00:00+00:00",
                "is_present": True
            },
            {
                "student_id": 2,
                "subject_id": 3,
                "timestamp": "2026-11-26T12:00:00+00:00",
                "is_present": False
            }
        ]

    def test_saves_only_owned_subject_and_enrolled_student_attendance(self):
        admin_client = FakeAdminClient()
        with patch.object(database, "supabase_admin", admin_client):
            saved = database.create_attendance(self.logs, teacher_id=9)

        self.assertEqual(saved, self.logs)
        self.assertEqual(admin_client.saved_logs, self.logs)

    def test_rejects_subject_not_owned_by_teacher(self):
        admin_client = FakeAdminClient(owns_subject=False)
        with patch.object(database, "supabase_admin", admin_client):
            with self.assertRaisesRegex(PermissionError, "not authorized"):
                database.create_attendance(self.logs, teacher_id=9)

        self.assertIsNone(admin_client.saved_logs)

    def test_rejects_students_not_enrolled_in_subject(self):
        admin_client = FakeAdminClient(enrolled_student_ids=(1,))
        with patch.object(database, "supabase_admin", admin_client):
            with self.assertRaisesRegex(ValueError, "not enrolled"):
                database.create_attendance(self.logs, teacher_id=9)

        self.assertIsNone(admin_client.saved_logs)

    def test_rejects_mixed_subjects_before_database_access(self):
        admin_client = FakeAdminClient()
        mixed_logs = [*self.logs, {**self.logs[0], "subject_id": 4}]
        with patch.object(database, "supabase_admin", admin_client):
            with self.assertRaisesRegex(ValueError, "one subject"):
                database.create_attendance(mixed_logs, teacher_id=9)

        self.assertIsNone(admin_client.saved_logs)


if __name__ == "__main__":
    unittest.main()
