import io
import os
import shutil
import sys
import unittest
import uuid
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from platform_api.services.metadata_store import MetadataStore
from platform_api.services.package_storage import PackageStorage


class MetadataStoreTests(unittest.TestCase):
    def test_register_package_upload_creates_version_and_audit(self) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        workspace = self._workspace_test_dir(repo_root)
        package_storage = PackageStorage(workspace / "packages")
        metadata_store = MetadataStore(workspace / "metadata.sqlite3")

        try:
            package_bytes = self._zip_directory(
                repo_root / "plugin_sdk" / "examples" / "demo_python_plugin"
            )
            package_record = package_storage.add_archive_bytes(
                "demo-python-plugin.zip",
                package_bytes,
            )

            registration = metadata_store.register_package_upload(package_record, actor="tester")
            audit_events = metadata_store.list_audit_events()

            self.assertEqual(registration.name, "demo-python-plugin")
            self.assertEqual(registration.version, "0.1.0")
            self.assertEqual(registration.status, "validated")
            self.assertEqual(len(audit_events), 1)
            self.assertEqual(audit_events[0]["event_type"], "plugin.package.uploaded")
            self.assertEqual(audit_events[0]["actor"], "tester")
            self.assertEqual(audit_events[0]["details"]["digest"], package_record.digest)
        finally:
            self._remove_workspace_test_dir(workspace)

    def test_reupload_same_version_reuses_version_and_records_audit(self) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        workspace = self._workspace_test_dir(repo_root)
        package_storage = PackageStorage(workspace / "packages")
        metadata_store = MetadataStore(workspace / "metadata.sqlite3")

        try:
            package_bytes = self._zip_directory(
                repo_root / "plugin_sdk" / "examples" / "demo_python_plugin"
            )
            first = package_storage.add_archive_bytes("demo-python-plugin.zip", package_bytes)
            second = package_storage.add_archive_bytes("demo-python-plugin.zip", package_bytes)

            first_registration = metadata_store.register_package_upload(first)
            second_registration = metadata_store.register_package_upload(second)
            audit_events = metadata_store.list_audit_events()

            self.assertEqual(first_registration.version_id, second_registration.version_id)
            self.assertEqual(len(audit_events), 2)
        finally:
            self._remove_workspace_test_dir(workspace)

    def test_lists_packages_and_versions_after_upload(self) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        workspace = self._workspace_test_dir(repo_root)
        package_storage = PackageStorage(workspace / "packages")
        metadata_store = MetadataStore(workspace / "metadata.sqlite3")

        try:
            package_bytes = self._zip_directory(
                repo_root / "plugin_sdk" / "examples" / "demo_python_plugin"
            )
            package_record = package_storage.add_archive_bytes(
                "demo-python-plugin.zip",
                package_bytes,
            )
            registration = metadata_store.register_package_upload(package_record)

            packages = metadata_store.list_plugin_packages()
            versions = metadata_store.list_plugin_versions("demo-python-plugin")
            missing_versions = metadata_store.list_plugin_versions("missing-plugin")

            self.assertEqual(len(packages), 1)
            self.assertEqual(packages[0]["id"], registration.package_id)
            self.assertEqual(packages[0]["name"], "demo-python-plugin")
            self.assertEqual(packages[0]["version_count"], 1)
            self.assertEqual(packages[0]["latest_version"], "0.1.0")
            self.assertEqual(packages[0]["latest_version_id"], registration.version_id)
            self.assertIsNotNone(versions)
            self.assertEqual(len(versions), 1)
            self.assertEqual(versions[0]["version"], "0.1.0")
            self.assertEqual(versions[0]["manifest"]["metadata"]["name"], "demo-python-plugin")
            self.assertIsNone(missing_versions)
        finally:
            self._remove_workspace_test_dir(workspace)

    def test_data_source_can_be_deleted(self) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        workspace = self._workspace_test_dir(repo_root)
        metadata_store = MetadataStore(workspace / "metadata.sqlite3")

        try:
            source = metadata_store.upsert_data_source(
                name="test-source",
                connector_type="mock",
                config={"points": {"a": 1}, "readTags": ["a"], "writeTags": ["b"]},
                read_enabled=True,
                write_enabled=True,
            )

            self.assertEqual(len(metadata_store.list_data_sources()), 1)
            self.assertTrue(metadata_store.delete_data_source(source.id))
            self.assertFalse(metadata_store.delete_data_source(source.id))
            self.assertEqual(metadata_store.list_data_sources(), [])
        finally:
            self._remove_workspace_test_dir(workspace)

    def test_instance_schedule_can_be_claimed_and_finished(self) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        workspace = self._workspace_test_dir(repo_root)
        package_storage = PackageStorage(workspace / "packages")
        metadata_store = MetadataStore(workspace / "metadata.sqlite3")

        try:
            package_bytes = self._zip_directory(
                repo_root / "plugin_sdk" / "examples" / "demo_python_plugin"
            )
            package_record = package_storage.add_archive_bytes(
                "demo-python-plugin.zip",
                package_bytes,
            )
            metadata_store.register_package_upload(package_record)
            instance = metadata_store.upsert_plugin_instance(
                name="scheduled-instance",
                package_name="demo-python-plugin",
                version="0.1.0",
                input_bindings=[],
                output_bindings=[],
                config={},
                writeback_enabled=False,
                schedule_enabled=True,
                schedule_interval_sec=30,
            )
            self.assertIsNotNone(instance)

            saved = metadata_store.get_plugin_instance(instance.id)
            self.assertIsNotNone(saved)
            self.assertTrue(saved["schedule_enabled"])
            self.assertEqual(saved["schedule_interval_sec"], 30)
            self.assertEqual(saved["status"], "scheduled")

            due_at = datetime.now(UTC) + timedelta(seconds=31)
            claimed = metadata_store.claim_due_scheduled_instances(now=due_at)
            self.assertEqual([item["id"] for item in claimed], [instance.id])
            self.assertEqual(metadata_store.get_plugin_instance(instance.id)["status"], "running")

            metadata_store.finish_scheduled_instance_run(
                instance_id=instance.id,
                finished_at=due_at,
            )
            finished = metadata_store.get_plugin_instance(instance.id)
            self.assertEqual(finished["status"], "scheduled")
            self.assertTrue(finished["last_scheduled_run_at"].startswith(due_at.replace(tzinfo=None).isoformat()))
            self.assertIsNotNone(finished["next_scheduled_run_at"])

            stopped = metadata_store.set_plugin_instance_schedule(instance_id=instance.id, enabled=False)
            self.assertFalse(stopped["schedule_enabled"])
            self.assertEqual(stopped["status"], "stopped")
            self.assertTrue(metadata_store.delete_plugin_instance(instance.id))
            self.assertIsNone(metadata_store.get_plugin_instance(instance.id))
        finally:
            self._remove_workspace_test_dir(workspace)

    def _zip_directory(self, source_dir: Path) -> bytes:
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in source_dir.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(source_dir).as_posix())
        return payload.getvalue()

    def _workspace_test_dir(self, repo_root: Path) -> Path:
        path = repo_root / "var" / "test-metadata" / uuid.uuid4().hex
        path.mkdir(parents=True, exist_ok=False)
        return path

    def _remove_workspace_test_dir(self, path: Path) -> None:
        test_root = Path(__file__).resolve().parents[3] / "var" / "test-metadata"
        resolved = path.resolve()
        if test_root.resolve() not in resolved.parents:
            raise RuntimeError(f"refusing to remove non-test path: {path}")
        if resolved.exists():
            try:
                shutil.rmtree(resolved, onexc=self._reset_permissions)
            except PermissionError:
                pass

    def _reset_permissions(self, function: object, path: str, exc_info: BaseException) -> None:
        os.chmod(path, 0o700)
        if callable(function):
            function(path)


if __name__ == "__main__":
    unittest.main()
