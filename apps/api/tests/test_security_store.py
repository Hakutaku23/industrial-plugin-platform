import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from platform_api.services.security_store import SecurityStore


class SecurityStoreTests(unittest.TestCase):
    def test_list_roles_returns_seeded_system_roles(self) -> None:
        db_path = Path(tempfile.gettempdir()) / f"platform-security-{uuid.uuid4().hex}.sqlite3"
        store = SecurityStore(f"sqlite:///{db_path.as_posix()}")
        try:
            roles = store.list_roles()

            role_by_name = {role["name"]: role for role in roles}
            self.assertIn("admin", role_by_name)
            self.assertIn("viewer", role_by_name)
            self.assertIn("user.read", role_by_name["admin"]["permissions"])
        finally:
            store.engine.dispose()
            if db_path.exists():
                os.chmod(db_path, 0o700)
                db_path.unlink()

    def test_sqlite_session_user_handles_naive_datetimes(self) -> None:
        db_path = Path(tempfile.gettempdir()) / f"platform-security-{uuid.uuid4().hex}.sqlite3"
        store = SecurityStore(f"sqlite:///{db_path.as_posix()}")
        try:
            user = store.create_user(
                username="admin",
                display_name="Admin",
                email=None,
                password_hash="test-hash",
                roles=["admin"],
            )
            store.create_session(
                user_id=int(user["id"]),
                session_token_hash="session-token-hash",
                ttl_sec=3600,
                ip_address="127.0.0.1",
                user_agent="test",
            )

            session_user = store.get_session_user(session_token_hash="session-token-hash")

            self.assertIsNotNone(session_user)
            assert session_user is not None
            self.assertEqual(session_user.username, "admin")
            self.assertIn("package.read", session_user.permissions)
        finally:
            store.engine.dispose()
            if db_path.exists():
                os.chmod(db_path, 0o700)
                db_path.unlink()


if __name__ == "__main__":
    unittest.main()
