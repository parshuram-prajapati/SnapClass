import importlib
import sys
import types
import unittest
from unittest.mock import Mock, patch


fake_config = types.ModuleType("src.database.config")
fake_config.get_secret = lambda _key, default="": default
fake_config.supabase = object()
fake_config.supabase_admin = object()
sys.modules["src.database.config"] = fake_config
database = importlib.import_module("src.database.db")


class TeacherAuthTests(unittest.TestCase):
    def setUp(self):
        self.teacher = {
            "teacher_id": 17,
            "username": "legacy_teacher",
            "name": "Teacher",
            "password": "legacy-password"
        }

    def test_legacy_plaintext_password_is_upgraded_after_successful_login(self):
        admin_client = Mock()
        admin_client.table.return_value.update.return_value.eq.return_value.select.return_value.execute.return_value.data = [
            {"teacher_id": 17}
        ]

        with (
            patch.object(database, "supabase_admin", admin_client),
            patch.object(
                database,
                "find_teacher_by_email_or_username",
                return_value=self.teacher
            ),
            patch.object(database, "hash_pass", return_value="$2b$upgraded-hash")
        ):
            profile = database.teacher_login(
                "legacy_teacher",
                "legacy-password"
            )

        self.assertEqual(profile["teacher_id"], 17)
        self.assertNotIn("password", profile)
        admin_client.table.assert_called_once_with("teachers")
        admin_client.table.return_value.update.assert_called_once_with(
            {"password": "$2b$upgraded-hash"}
        )

    def test_wrong_legacy_password_is_rejected_without_database_update(self):
        admin_client = Mock()
        with (
            patch.object(database, "supabase_admin", admin_client),
            patch.object(
                database,
                "find_teacher_by_email_or_username",
                return_value=self.teacher
            )
        ):
            profile = database.teacher_login(
                "legacy_teacher",
                "incorrect-password"
            )

        self.assertIsNone(profile)
        admin_client.table.assert_not_called()

    def test_bcrypt_password_login_does_not_rewrite_the_password(self):
        password_hash = database.hash_pass("correct-password")
        teacher = {**self.teacher, "password": password_hash}
        admin_client = Mock()

        with (
            patch.object(database, "supabase_admin", admin_client),
            patch.object(
                database,
                "find_teacher_by_email_or_username",
                return_value=teacher
            )
        ):
            profile = database.teacher_login(
                "legacy_teacher",
                "correct-password"
            )

        self.assertEqual(profile["teacher_id"], 17)
        self.assertNotIn("password", profile)
        admin_client.table.assert_not_called()


if __name__ == "__main__":
    unittest.main()
