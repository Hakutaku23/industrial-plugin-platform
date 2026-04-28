import hashlib
import json
import os
import shutil
import stat
import tarfile
import uuid
import zipfile
from dataclasses import dataclass, field
from importlib.machinery import EXTENSION_SUFFIXES
from pathlib import Path, PurePosixPath
from typing import Any

from platform_api.services.manifest import ManifestError, PluginManifest, load_manifest
from platform_api.services.package_signature import (
    PluginSignatureError,
    PluginSignatureVerification,
    verify_plugin_signature,
)


class PackageStorageError(ValueError):
    """Raised when plugin package intake fails."""


@dataclass(frozen=True)
class PackageRecord:
    manifest: PluginManifest
    digest: str
    package_dir: Path
    signature_verification: dict[str, Any] = field(default_factory=dict)


class PackageStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def add_archive_bytes(self, filename: str, content: bytes) -> PackageRecord:
        digest = hashlib.sha256(content).hexdigest()
        suffix = self._archive_suffix(filename)
        if suffix is None:
            raise PackageStorageError("only .zip and .tar.gz plugin packages are supported")

        staging_dir = self.root / "_intake" / f"{digest}-{uuid.uuid4().hex}"
        staging_dir.mkdir(parents=True, exist_ok=False)
        target_dir: Path | None = None
        signature_verification: PluginSignatureVerification | None = None
        try:
            archive_path = staging_dir / f"upload{suffix}"
            archive_path.write_bytes(content)
            extracted_dir = staging_dir / "extracted"
            extracted_dir.mkdir()

            if suffix == ".zip":
                self._extract_zip(archive_path, extracted_dir)
            else:
                self._extract_tar_gz(archive_path, extracted_dir)

            package_root = self._locate_package_root(extracted_dir)
            try:
                manifest = load_manifest(package_root / "manifest.yaml")
            except ManifestError as exc:
                raise PackageStorageError(str(exc)) from exc

            self._validate_entry_exists(package_root, manifest)
            self._validate_checksums(package_root)
            try:
                signature_verification = verify_plugin_signature(package_root)
            except PluginSignatureError as exc:
                raise PackageStorageError(f"plugin signature verification failed: {exc}") from exc

            target_dir = self.root / manifest.metadata.name / manifest.metadata.version / digest[:12]
            if not target_dir.exists():
                target_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(package_root, target_dir)
            if signature_verification is not None:
                self._write_platform_metadata(target_dir, signature_verification)
        finally:
            self._remove_child_dir(staging_dir)

        if target_dir is None:
            raise PackageStorageError("plugin package target directory was not resolved")
        return PackageRecord(
            manifest=manifest,
            digest=digest,
            package_dir=target_dir,
            signature_verification=signature_verification.to_dict() if signature_verification else {},
        )

    def _archive_suffix(self, filename: str) -> str | None:
        lowered = filename.lower()
        if lowered.endswith(".tar.gz"):
            return ".tar.gz"
        if lowered.endswith(".zip"):
            return ".zip"
        return None

    def _assert_safe_member_path(self, name: str) -> None:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or name.startswith("\\"):
            raise PackageStorageError(f"unsafe archive path: {name}")

    def _extract_zip(self, archive_path: Path, output_dir: Path) -> None:
        try:
            with zipfile.ZipFile(archive_path) as archive:
                for member in archive.infolist():
                    self._assert_safe_member_path(member.filename)
                    mode = member.external_attr >> 16
                    if stat.S_ISLNK(mode):
                        raise PackageStorageError(f"symlink is not allowed: {member.filename}")
                archive.extractall(output_dir)
        except zipfile.BadZipFile as exc:
            raise PackageStorageError("zip package is invalid") from exc

    def _extract_tar_gz(self, archive_path: Path, output_dir: Path) -> None:
        try:
            with tarfile.open(archive_path, "r:gz") as archive:
                for member in archive.getmembers():
                    self._assert_safe_member_path(member.name)
                    if member.issym() or member.islnk():
                        raise PackageStorageError(f"link is not allowed: {member.name}")
                archive.extractall(output_dir)
        except tarfile.TarError as exc:
            raise PackageStorageError("tar.gz package is invalid") from exc

    def _locate_package_root(self, extracted_dir: Path) -> Path:
        if (extracted_dir / "manifest.yaml").exists():
            return extracted_dir

        entries = [path for path in extracted_dir.iterdir() if path.name not in {"__MACOSX", ".DS_Store"}]
        directories = [path for path in entries if path.is_dir()]
        files = [path for path in entries if path.is_file()]
        if len(directories) == 1 and not files and (directories[0] / "manifest.yaml").exists():
            return directories[0]

        raise PackageStorageError(
            "manifest not found: expected manifest.yaml at archive root or inside a single top-level directory"
        )

    def _validate_entry_exists(self, package_dir: Path, manifest: PluginManifest) -> None:
        entry = manifest.spec.entry
        entry_type = getattr(entry, "entry_type", "file")
        if entry_type == "file":
            if not entry.file:
                raise PackageStorageError("entry.file is required for file entry")
            entry_path = (package_dir / entry.file).resolve()
            package_root = package_dir.resolve()
            if package_root not in entry_path.parents and entry_path != package_root:
                raise PackageStorageError("entry file escapes package directory")
            if not entry_path.exists():
                raise PackageStorageError(f"entry file not found: {entry.file}")
            if not entry_path.is_file():
                raise PackageStorageError(f"entry path is not a file: {entry.file}")
            return

        if entry_type == "module":
            if not entry.module:
                raise PackageStorageError("entry.module is required for module entry")
            module_rel = Path(*entry.module.split("."))
            module_file = (package_dir / module_rel).with_suffix(".py")
            package_init = package_dir / module_rel / "__init__.py"
            if module_file.is_file() or package_init.is_file():
                return
            extension_candidate = self._find_python_extension_module(package_dir=package_dir, module_rel=module_rel)
            if extension_candidate is not None:
                return
            expected = [str(module_file.relative_to(package_dir)), str(package_init.relative_to(package_dir))]
            expected.extend(str(path.relative_to(package_dir)) for path in self._extension_probe_paths(package_dir, module_rel)[:6])
            raise PackageStorageError("entry module not found: expected one of " + ", ".join(expected))

        raise PackageStorageError(f"unsupported entry.type: {entry_type}")

    def _find_python_extension_module(self, *, package_dir: Path, module_rel: Path) -> Path | None:
        for path in self._extension_probe_paths(package_dir, module_rel):
            if path.is_file():
                return path
        return None

    def _extension_probe_paths(self, package_dir: Path, module_rel: Path) -> list[Path]:
        base = package_dir / module_rel
        parent = base.parent
        stem = base.name
        candidates = [(parent / stem).with_suffix(suffix) for suffix in EXTENSION_SUFFIXES]
        candidates.extend(parent.glob(f"{stem}*.so"))
        candidates.extend(parent.glob(f"{stem}*.pyd"))
        result: list[Path] = []
        seen: set[Path] = set()
        package_root = package_dir.resolve()
        for item in candidates:
            resolved = item.resolve()
            if resolved in seen:
                continue
            if package_root not in resolved.parents and resolved != package_root:
                continue
            seen.add(resolved)
            result.append(item)
        return result

    def _validate_checksums(self, package_dir: Path) -> None:
        checksums_path = package_dir / "checksums.json"
        if not checksums_path.exists():
            return
        try:
            payload = json.loads(checksums_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise PackageStorageError(f"checksums.json is not valid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise PackageStorageError("checksums.json must contain a JSON object")
        files = payload.get("files", {})
        if not isinstance(files, dict):
            raise PackageStorageError("checksums.json files must be an object")

        root = package_dir.resolve()
        for relative_path, expected_raw in files.items():
            relative_text = str(relative_path).strip()
            self._assert_safe_relative_path(relative_text)
            path = (root / relative_text).resolve()
            if root not in path.parents and path != root:
                raise PackageStorageError(f"checksum path escapes package root: {relative_text}")
            if not path.is_file():
                raise PackageStorageError(f"checksum file not found: {relative_text}")
            expected = self._normalize_sha256(str(expected_raw))
            actual = self._sha256_file(path)
            if expected != actual:
                raise PackageStorageError(f"checksum mismatch: {relative_text}")

    def _assert_safe_relative_path(self, value: str) -> None:
        path = PurePosixPath(value.replace("\\", "/"))
        if not value or path.is_absolute() or ".." in path.parts:
            raise PackageStorageError(f"unsafe relative path: {value}")

    def _normalize_sha256(self, value: str) -> str:
        normalized = value.strip().lower()
        if normalized.startswith("sha256:"):
            normalized = normalized.split(":", 1)[1]
        if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
            raise PackageStorageError("sha256 value must be sha256:<64 hex> or 64 hex")
        return normalized

    def _sha256_file(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _write_platform_metadata(self, target_dir: Path, signature_verification: PluginSignatureVerification) -> None:
        metadata_dir = target_dir / ".platform"
        metadata_dir.mkdir(parents=True, exist_ok=True)
        target = metadata_dir / "signature_verification.json"
        tmp = metadata_dir / "signature_verification.json.tmp"
        tmp.write_text(json.dumps(signature_verification.to_dict(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, target)

    def _remove_child_dir(self, path: Path) -> None:
        root = self.root.resolve()
        resolved = path.resolve()
        if root == resolved or root not in resolved.parents:
            raise PackageStorageError(f"refusing to remove path outside package root: {path}")
        if resolved.exists():
            try:
                shutil.rmtree(resolved, onexc=_reset_permissions)
            except TypeError:
                shutil.rmtree(resolved, onerror=_reset_permissions_legacy)
            except PermissionError:
                pass


def _reset_permissions(function: object, path: str, exc_info: BaseException) -> None:
    os.chmod(path, stat.S_IWRITE)
    if callable(function):
        function(path)


def _reset_permissions_legacy(function: object, path: str, exc_info: object) -> None:
    os.chmod(path, stat.S_IWRITE)
    if callable(function):
        function(path)
