import io
import os
import shutil
import sys
import unittest
import uuid
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from platform_api.services.package_storage import PackageStorage, PackageStorageError


class PackageStorageTests(unittest.TestCase):
    def test_demo_zip_is_stored(self) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        plugin_dir = repo_root / "plugin_sdk" / "examples" / "demo_python_plugin"
        package_bytes = self._zip_directory(plugin_dir)

        storage_dir = self._workspace_test_dir(repo_root)
        try:
            record = PackageStorage(storage_dir).add_archive_bytes(
                "demo-python-plugin.zip",
                package_bytes,
            )

            self.assertEqual(record.manifest.metadata.name, "demo-python-plugin")
            self.assertTrue(record.package_dir.is_absolute())
            self.assertTrue((record.package_dir / "manifest.yaml").exists())
        finally:
            self._remove_workspace_test_dir(storage_dir)

    def test_zip_with_single_top_level_directory_is_stored(self) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        plugin_dir = repo_root / "plugin_sdk" / "examples" / "no_input_output_plugin"
        package_bytes = self._zip_wrapped_directory(plugin_dir)

        storage_dir = self._workspace_test_dir(repo_root)
        try:
            record = PackageStorage(storage_dir).add_archive_bytes(
                "no-input-output-plugin.zip",
                package_bytes,
            )

            self.assertEqual(record.manifest.metadata.name, "no-input-output-plugin")
            self.assertTrue(record.package_dir.is_absolute())
            self.assertTrue((record.package_dir / "manifest.yaml").exists())
            self.assertTrue((record.package_dir / "runtime" / "main.py").exists())
        finally:
            self._remove_workspace_test_dir(storage_dir)

    def test_zip_path_traversal_is_rejected(self) -> None:
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("../manifest.yaml", "bad: true")

        repo_root = Path(__file__).resolve().parents[3]
        storage_dir = self._workspace_test_dir(repo_root)
        try:
            with self.assertRaises(PackageStorageError):
                PackageStorage(storage_dir).add_archive_bytes("bad.zip", payload.getvalue())
        finally:
            self._remove_workspace_test_dir(storage_dir)

    def _zip_directory(self, source_dir: Path) -> bytes:
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in source_dir.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(source_dir).as_posix())
        return payload.getvalue()

    def _zip_wrapped_directory(self, source_dir: Path) -> bytes:
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in source_dir.rglob("*"):
                if path.is_file():
                    archive.write(path, Path(source_dir.name, path.relative_to(source_dir)).as_posix())
        return payload.getvalue()

    def _workspace_test_dir(self, repo_root: Path) -> Path:
        path = repo_root / "var" / "test-packages" / uuid.uuid4().hex
        path.mkdir(parents=True, exist_ok=False)
        return path

    def _remove_workspace_test_dir(self, path: Path) -> None:
        test_root = Path(__file__).resolve().parents[3] / "var" / "test-packages"
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
