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
        self.payload = None

    def select(self, columns):
        self.client.selections.append((self.table_name, columns))
        return self

    def eq(self, column, value):
        self.filters[column] = value
        return self

    def limit(self, _limit):
        return self

    def insert(self, payload):
        self.payload = payload
        return self

    def execute(self):
        self.client.executed_tables.append(self.table_name)
        if self.table_name == "teachers":
            data = [{"teacher_id": self.filters.get("teacher_id", 9)}]
        elif self.table_name == "subjects" and self.payload is not None:
            data = [self.payload]
        elif self.table_name == "students":
            data = [{"student_id": 1, "name": "Student", "usn": "2BL24CI028"}]
        else:
            data = []
        return FakeResponse(data)


class FakeAdminClient:
    def __init__(self):
        self.selections = []
        self.executed_tables = []

    def table(self, name):
        return FakeQuery(self, name)


class AdminDatabaseOperationTests(unittest.TestCase):
    def test_create_subject_uses_admin_client_and_checks_teacher(self):
        admin_client = FakeAdminClient()
        with patch.object(database, "supabase_admin", admin_client):
            result = database.create_subject("CS101", "Computer Science", "A", 9)

        self.assertEqual(result[0]["teacher_id"], 9)
        self.assertEqual(admin_client.executed_tables, ["teachers", "subjects"])

    def test_student_registration_passes_admin_client_to_registration_service(self):
        admin_client = FakeAdminClient()
        with (
            patch.object(database, "supabase_admin", admin_client),
            patch.object(database, "create_student_record", return_value={"student_id": 1}) as create,
        ):
            result = database.create_student("Student", "2bl24ci028")

        self.assertEqual(result, {"student_id": 1})
        self.assertIs(create.call_args.args[0], admin_client)

    def test_student_login_profiles_are_loaded_through_admin_client(self):
        admin_client = FakeAdminClient()
        with patch.object(database, "supabase_admin", admin_client):
            students = database.get_all_students()

        self.assertEqual(students[0]["student_id"], 1)
        self.assertEqual(admin_client.executed_tables, ["students"])
        self.assertIn(("students", "student_id, name, usn"), admin_client.selections)


if __name__ == "__main__":
    unittest.main()
