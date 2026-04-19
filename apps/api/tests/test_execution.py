import io
import os
import shutil
import sys
import textwrap
import unittest
import uuid
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "runner"))

from platform_api.services.execution import PluginExecutionError, execute_plugin_instance, execute_plugin_version
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

            result = execute_plugin_instance(
                instance_id=instance.id,
                trigger_type="schedule",
                store=metadata_store,
            )
            writebacks = metadata_store.list_writeback_records(result["run_id"])
            runs = metadata_store.list_plugin_runs("demo-python-plugin")

            self.assertEqual(result["status"], "COMPLETED")
            self.assertEqual(result["inputs"]["value"], 7)
            self.assertEqual(result["outputs"]["doubled"], 14)
            self.assertEqual(runs[0]["instance_id"], instance.id)
            self.assertEqual(runs[0]["trigger_type"], "schedule")
            self.assertEqual(writebacks[0]["status"], "dry_run")
            self.assertEqual(writebacks[0]["target_tag"], "demo:doubled")
            self.assertEqual(writebacks[0]["value"], 14)
        finally:
            self._remove_workspace_test_dir(workspace)

    def test_execute_instance_resolves_batch_points_and_writes_batch_outputs(self) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        workspace = self._workspace_test_dir(repo_root)
        package_storage = PackageStorage(workspace / "packages")
        metadata_store = MetadataStore(workspace / "metadata.sqlite3")

        try:
            package_record = package_storage.add_archive_bytes(
                "batch-python-plugin.zip",
                self._batch_plugin_archive(),
            )
            metadata_store.register_package_upload(package_record)
            source = metadata_store.upsert_data_source(
                name="mock-line-a",
                connector_type="mock",
                config={
                    "points": {
                        "demo:a": 2,
                        "demo:b": 3,
                        "demo:out-a": 0,
                        "demo:out-b": 0,
                    },
                    "pointCatalog": [
                        {
                            "class": "demo",
                            "canRead": True,
                            "readTag": "demo:a",
                            "canWrite": True,
                            "writeTag": "demo:out-a",
                        },
                        {
                            "class": "demo",
                            "canRead": True,
                            "readTag": "demo:b",
                            "canWrite": True,
                            "writeTag": "demo:out-b",
                        },
                    ],
                    "readTags": ["demo:a", "demo:b"],
                    "writeTags": ["demo:out-a", "demo:out-b"],
                },
                read_enabled=True,
                write_enabled=True,
            )
            instance = metadata_store.upsert_plugin_instance(
                name="batch-instance",
                package_name="batch-python-plugin",
                version="0.1.0",
                input_bindings=[
                    {
                        "binding_type": "batch",
                        "input_name": "state_batch",
                        "data_source_id": source.id,
                        "source_tags": ["demo:a", "demo:b"],
                        "output_format": "named-map",
                    }
                ],
                output_bindings=[
                    {
                        "binding_type": "batch",
                        "output_name": "setpoints",
                        "data_source_id": source.id,
                        "target_tags": ["demo:out-a", "demo:out-b"],
                        "dry_run": False,
                    }
                ],
                config={},
                writeback_enabled=True,
            )

            result = execute_plugin_instance(instance_id=instance.id, store=metadata_store)
            writebacks = metadata_store.list_writeback_records(result["run_id"])
            updated_source = metadata_store.get_data_source(source.id)

            self.assertEqual(result["status"], "COMPLETED")
            self.assertEqual(result["inputs"]["state_batch"], {"demo:a": 2, "demo:b": 3})
            self.assertEqual(result["outputs"]["total"], 5)
            self.assertEqual({item["target_tag"]: item["status"] for item in writebacks}, {
                "demo:out-a": "success",
                "demo:out-b": "success",
            })
            self.assertEqual(updated_source["config"]["points"]["demo:out-a"], 15)
            self.assertEqual(updated_source["config"]["points"]["demo:out-b"], 25)
        finally:
            self._remove_workspace_test_dir(workspace)

    def test_execute_instance_resolves_ordered_batch_input(self) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        workspace = self._workspace_test_dir(repo_root)
        package_storage = PackageStorage(workspace / "packages")
        metadata_store = MetadataStore(workspace / "metadata.sqlite3")

        try:
            package_record = package_storage.add_archive_bytes(
                "batch-python-plugin.zip",
                self._batch_plugin_archive(),
            )
            metadata_store.register_package_upload(package_record)
            source = metadata_store.upsert_data_source(
                name="mock-line-a",
                connector_type="mock",
                config={"points": {"demo:a": 2, "demo:b": 3}},
                read_enabled=True,
                write_enabled=True,
            )
            instance = metadata_store.upsert_plugin_instance(
                name="batch-instance",
                package_name="batch-python-plugin",
                version="0.1.0",
                input_bindings=[
                    {
                        "binding_type": "batch",
                        "input_name": "state_batch",
                        "data_source_id": source.id,
                        "source_tags": ["demo:b", "demo:a"],
                        "output_format": "ordered-list",
                    }
                ],
                output_bindings=[],
                config={},
                writeback_enabled=False,
            )

            result = execute_plugin_instance(instance_id=instance.id, store=metadata_store)

            self.assertEqual(result["status"], "COMPLETED")
            self.assertEqual(result["inputs"]["state_batch"], [3, 2])
            self.assertEqual(result["outputs"]["total"], 5)
        finally:
            self._remove_workspace_test_dir(workspace)

    def test_instance_blocks_unreadable_point_binding(self) -> None:
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
                config={
                    "points": {"demo:value": 7},
                    "pointCatalog": [
                        {
                            "class": "demo",
                            "canRead": False,
                            "readTag": "demo:value",
                            "canWrite": True,
                            "writeTag": "demo:doubled",
                        }
                    ],
                    "readTags": [],
                    "writeTags": ["demo:doubled"],
                },
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
                output_bindings=[],
                config={},
                writeback_enabled=False,
            )
            self.assertIsNotNone(instance)

            result = execute_plugin_instance(instance_id=instance.id, store=metadata_store)

            self.assertEqual(result["status"], "FAILED")
            self.assertEqual(result["error"]["code"], "E_INPUT_BINDING_FAILED")
            self.assertIn("not configured as readable", result["error"]["message"])
        finally:
            self._remove_workspace_test_dir(workspace)

    def test_instance_blocks_unwritable_point_binding_even_in_dry_run(self) -> None:
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
                config={
                    "points": {"demo:value": 7},
                    "pointCatalog": [
                        {
                            "class": "demo",
                            "canRead": True,
                            "readTag": "demo:value",
                            "canWrite": False,
                            "writeTag": "demo:doubled",
                        }
                    ],
                    "readTags": ["demo:value"],
                    "writeTags": [],
                },
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

            result = execute_plugin_instance(instance_id=instance.id, store=metadata_store)
            writebacks = metadata_store.list_writeback_records(result["run_id"])

            self.assertEqual(result["status"], "COMPLETED")
            self.assertEqual(writebacks[0]["status"], "blocked")
            self.assertIn("not configured as writable", writebacks[0]["reason"])
        finally:
            self._remove_workspace_test_dir(workspace)

    def _zip_directory(self, source_dir: Path) -> bytes:
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in source_dir.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(source_dir).as_posix())
        return payload.getvalue()

    def _batch_plugin_archive(self) -> bytes:
        manifest = textwrap.dedent(
            """
            apiVersion: plugin.platform/v1
            kind: PluginPackage
            metadata:
              name: batch-python-plugin
              displayName: Batch Python Plugin
              version: 0.1.0
              author: Dev
              description: Batch binding test plugin.
              tags:
                - demo
                - python
            spec:
              pluginType: python
              packageFormat: zip
              entry:
                mode: function
                file: runtime/main.py
                callable: run
              runtime:
                pythonVersion: "3.12"
                workingDir: "."
                timeoutSec: 20
              schedule:
                type: manual
              inputs:
                - name: state_batch
                  type: object
                  required: true
              outputs:
                - name: total
                  type: number
                - name: setpoints
                  type: object
                  writable: true
              permissions:
                network: false
                filesystem: scoped
                writeback: false
            compatibility:
              platformApi: ">=0.1.0"
              runnerApi: ">=0.1.0"
            """
        ).strip()
        main = textwrap.dedent(
            """
            from typing import Any


            def run(payload: dict[str, Any]) -> dict[str, Any]:
                state = payload.get("inputs", {}).get("state_batch")
                if isinstance(state, dict):
                    total = sum(state.values())
                elif isinstance(state, list):
                    total = sum(state)
                else:
                    return {"status": "failed", "outputs": {}, "logs": ["state_batch must be a dict or list"], "metrics": {}}

                return {
                    "status": "success",
                    "outputs": {
                        "total": total,
                        "setpoints": {
                            "demo:out-a": total + 10,
                            "demo:out-b": total + 20,
                        },
                    },
                    "logs": ["batch calculation completed"],
                    "metrics": {"point_count": len(state)},
                }
            """
        ).strip()
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.yaml", manifest)
            archive.writestr("runtime/main.py", main)
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
