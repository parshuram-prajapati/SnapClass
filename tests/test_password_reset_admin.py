import importlib
import sys
import types
import unittest
from unittest.mock import patch


fake_config = types.ModuleType("src.database.config")
fake_config.get_secret = lambda _key, default="": default
fake_config.supabase = object()
fake_config.supabase_admin = object()
with patch.dict(sys.modules, {"src.database.config": fake_config}):
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


if __name__ == "__main__":
    unittest.main()
