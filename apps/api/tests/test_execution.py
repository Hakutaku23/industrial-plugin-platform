import io
import os
import shutil
import sys
import unittest
import uuid
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "runner"))

from platform_api.services.execution import execute_plugin_version
from platform_api.services.metadata_store import MetadataStore
from platform_api.services.package_storage import PackageStorage


class ExecutionTests(unittest.TestCase):
    def test_execute_registered_demo_plugin_records_run_and_logs(self) -> None:
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

            result = execute_plugin_version(
                package_name="demo-python-plugin",
                version="0.1.0",
                inputs={"value": 7},
                config={},
                store=metadata_store,
            )
            runs = metadata_store.list_plugin_runs("demo-python-plugin")
            logs = metadata_store.list_run_logs(result["run_id"])

            self.assertEqual(result["status"], "COMPLETED")
            self.assertEqual(result["outputs"]["doubled"], 14)
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0]["run_id"], result["run_id"])
            self.assertEqual(runs[0]["outputs"]["doubled"], 14)
            self.assertGreaterEqual(len(logs), 2)
        finally:
            self._remove_workspace_test_dir(workspace)

    def test_execute_instance_resolves_mock_points_and_records_writeback(self) -> None:
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
            source = metadata_store.upsert_data_source(
                name="mock-line-a",
                connector_type="mock",
                config={"points": {"demo:value": 7}},
                read_enabled=True,
                write_enabled=True,
            )
            instance = metadata_store.upsert_plugin_instance(
                name="demo-instance",
                package_name="demo-python-plugin",
                version="0.1.0",
                input_bindings=[
                    {
                        "input_name": "value",
                        "data_source_id": source.id,
                        "source_tag": "demo:value",
                    }
                ],
                output_bindings=[
                    {
                        "output_name": "doubled",
                        "data_source_id": source.id,
                        "target_tag": "demo:doubled",
                        "dry_run": True,
                    }
                ],
                config={},
                writeback_enabled=False,
            )
            self.assertIsNotNone(instance)

            from platform_api.services.execution import execute_plugin_instance

            result = execute_plugin_instance(instance_id=instance.id, store=metadata_store)
            writebacks = metadata_store.list_writeback_records(result["run_id"])

            self.assertEqual(result["status"], "COMPLETED")
            self.assertEqual(result["inputs"]["value"], 7)
            self.assertEqual(result["outputs"]["doubled"], 14)
            self.assertEqual(writebacks[0]["status"], "dry_run")
            self.assertEqual(writebacks[0]["target_tag"], "demo:doubled")
            self.assertEqual(writebacks[0]["value"], 14)
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
        path = repo_root / "var" / "test-execution" / uuid.uuid4().hex
        path.mkdir(parents=True, exist_ok=False)
        return path

    def _remove_workspace_test_dir(self, path: Path) -> None:
        test_root = Path(__file__).resolve().parents[3] / "var" / "test-execution"
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
