import hashlib
import os
import shutil
import stat
import tarfile
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from platform_api.services.manifest import ManifestError, PluginManifest, load_manifest


class PackageStorageError(ValueError):
    """Raised when plugin package intake fails."""


@dataclass(frozen=True)
class PackageRecord:
    manifest: PluginManifest
    digest: str
    package_dir: Path


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
            target_dir = self.root / manifest.metadata.name / manifest.metadata.version / digest[:12]
            if not target_dir.exists():
                target_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(package_root, target_dir)
        finally:
            self._remove_child_dir(staging_dir)

        return PackageRecord(manifest=manifest, digest=digest, package_dir=target_dir)

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

        entries = [
            path
            for path in extracted_dir.iterdir()
            if path.name not in {"__MACOSX", ".DS_Store"}
        ]
        directories = [path for path in entries if path.is_dir()]
        files = [path for path in entries if path.is_file()]
        if len(directories) == 1 and not files and (directories[0] / "manifest.yaml").exists():
            return directories[0]

        raise PackageStorageError(
            "manifest not found: expected manifest.yaml at archive root or inside a single top-level directory"
        )

    def _validate_entry_exists(self, package_dir: Path, manifest: PluginManifest) -> None:
        entry = manifest.spec.entry
        if entry.file:
            entry_path = (package_dir / entry.file).resolve()
            package_root = package_dir.resolve()
            if package_root not in entry_path.parents and entry_path != package_root:
                raise PackageStorageError("entry file escapes package directory")
            if not entry_path.exists():
                raise PackageStorageError(f"entry file not found: {entry.file}")

    def _remove_child_dir(self, path: Path) -> None:
        root = self.root.resolve()
        resolved = path.resolve()
        if root == resolved or root not in resolved.parents:
            raise PackageStorageError(f"refusing to remove path outside package root: {path}")
        if resolved.exists():
            try:
                shutil.rmtree(resolved, onexc=_reset_permissions)
            except PermissionError:
                pass


def _reset_permissions(function: object, path: str, exc_info: BaseException) -> None:
    os.chmod(path, stat.S_IWRITE)
    if callable(function):
        function(path)
