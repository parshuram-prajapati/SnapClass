import unittest

from src.services.student_registration import (
    DEFAULT_USN_PATTERN,
    create_student_record,
    normalize_usn,
)


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeUniqueViolation(Exception):
    code = "23505"
    details = (
        'Key (upper(btrim(usn)))=(2BL24CI028) already exists in '
        '"students_usn_normalized_unique_idx".'
    )


class FakeQuery:
    def __init__(self, table, operation, payload=None):
        self.table = table
        self.operation = operation
        self.payload = payload

    def select(self, _columns):
        return self

    def eq(self, _column, _value):
        return self

    def limit(self, _count):
        return self

    def insert(self, payload):
        self.operation = "insert"
        self.payload = payload
        return self

    def execute(self):
        if self.operation == "select":
            return FakeResponse(self.table.existing_rows)
        if self.table.insert_error:
            raise self.table.insert_error
        self.table.inserted = self.payload
        return FakeResponse([{"student_id": 7, **self.payload}])


class FakeTable:
    def __init__(self, existing_rows=None, insert_error=None):
        self.existing_rows = existing_rows or []
        self.insert_error = insert_error
        self.inserted = None

    def table(self, _name):
        return self

    def select(self, columns):
        return FakeQuery(self, "select").select(columns)

    def insert(self, payload):
        return FakeQuery(self, "insert", payload)


class StudentRegistrationTests(unittest.TestCase):
    def test_valid_usn_is_trimmed_and_uppercased_on_insert(self):
        client = FakeTable()

        result = create_student_record(
            client,
            "  Parshuram Prajapati ",
            "  2bl24ci028  "
        )

        self.assertEqual(client.inserted["name"], "Parshuram Prajapati")
        self.assertEqual(client.inserted["usn"], "2BL24CI028")
        self.assertEqual(result[0]["student_id"], 7)

    def test_invalid_and_missing_usn_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Invalid USN"):
            normalize_usn("2BL24CI02X")

        with self.assertRaisesRegex(ValueError, "USN is required"):
            normalize_usn("   ")

    def test_duplicate_usn_is_rejected_before_insert(self):
        client = FakeTable(existing_rows=[{"student_id": 4}])

        with self.assertRaisesRegex(ValueError, "already registered"):
            create_student_record(client, "Student Name", "2BL24CI028")

        self.assertIsNone(client.inserted)

    def test_unique_constraint_race_returns_duplicate_message(self):
        client = FakeTable(insert_error=FakeUniqueViolation())

        with self.assertRaisesRegex(ValueError, "already registered"):
            create_student_record(client, "Student Name", "2BL24CI028")

    def test_usn_pattern_can_be_configured(self):
        custom_pattern = r"^STU-[0-9]{4}$"

        self.assertEqual(
            normalize_usn(" stu-0042 ", custom_pattern),
            "STU-0042"
        )

        with self.assertRaises(ValueError):
            normalize_usn("2BL24CI028", custom_pattern)


if __name__ == "__main__":
    unittest.main()
