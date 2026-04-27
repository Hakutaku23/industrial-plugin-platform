from __future__ import annotations

import stat
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

import yaml


PackageKind = Literal["plugin", "model"]


class PackageIntakeError(ValueError):
    """Raised when an uploaded archive cannot be classified safely."""


@dataclass(frozen=True)
class PackageIntakeResult:
    kind: PackageKind
    manifest: dict


def detect_package_kind(*, filename: str, content: bytes) -> PackageIntakeResult:
    """Classify an uploaded package by manifest.yaml.

    Plugin package:
      apiVersion: plugin.platform/v1 or plugin.platform/v2
      kind: PluginPackage

    Model artifact package:
      schema: ipp-model/v1
      model: ...
      artifacts: ...
    """
    if not content:
        raise PackageIntakeError("package body is empty")

    suffix = _archive_suffix(filename)
    if suffix is None:
        raise PackageIntakeError("only .zip and .tar.gz packages are supported")

    with tempfile.TemporaryDirectory(prefix="ipp-intake-") as temp_dir:
        temp_root = Path(temp_dir)
        archive_path = temp_root / f"upload{suffix}"
        archive_path.write_bytes(content)
        extracted_dir = temp_root / "extracted"
        extracted_dir.mkdir()

        if suffix == ".zip":
            _extract_zip(archive_path, extracted_dir)
        else:
            _extract_tar_gz(archive_path, extracted_dir)

        package_root = _locate_package_root(extracted_dir)
        manifest_path = package_root / "manifest.yaml"
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise PackageIntakeError("manifest.yaml must contain a YAML object")

        api_version = str(raw.get("apiVersion", "")).strip()
        kind = str(raw.get("kind", "")).strip()
        schema = str(raw.get("schema", "")).strip()

        if api_version in {"plugin.platform/v1", "plugin.platform/v2"} and kind == "PluginPackage":
            return PackageIntakeResult(kind="plugin", manifest=raw)
        if schema == "ipp-model/v1" and isinstance(raw.get("model"), dict) and isinstance(raw.get("artifacts"), dict):
            return PackageIntakeResult(kind="model", manifest=raw)

        raise PackageIntakeError(
            "unsupported package manifest: expected plugin apiVersion/kind or model schema=ipp-model/v1"
        )


def _archive_suffix(filename: str) -> str | None:
    lowered = filename.lower()
    if lowered.endswith(".tar.gz"):
        return ".tar.gz"
    if lowered.endswith(".zip"):
        return ".zip"
    return None


def _assert_safe_member_path(name: str) -> None:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or name.startswith("\\"):
        raise PackageIntakeError(f"unsafe archive path: {name}")


def _extract_zip(archive_path: Path, output_dir: Path) -> None:
    try:
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                _assert_safe_member_path(member.filename)
                mode = member.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise PackageIntakeError(f"symlink is not allowed: {member.filename}")
            archive.extractall(output_dir)
    except zipfile.BadZipFile as exc:
        raise PackageIntakeError("zip package is invalid") from exc


def _extract_tar_gz(archive_path: Path, output_dir: Path) -> None:
    try:
        with tarfile.open(archive_path, "r:gz") as archive:
            for member in archive.getmembers():
                _assert_safe_member_path(member.name)
                if member.issym() or member.islnk():
                    raise PackageIntakeError(f"link is not allowed: {member.name}")
            archive.extractall(output_dir)
    except tarfile.TarError as exc:
        raise PackageIntakeError("tar.gz package is invalid") from exc


def _locate_package_root(extracted_dir: Path) -> Path:
    if (extracted_dir / "manifest.yaml").exists():
        return extracted_dir

    entries = [path for path in extracted_dir.iterdir() if path.name not in {"__MACOSX", ".DS_Store"}]
    directories = [path for path in entries if path.is_dir()]
    files = [path for path in entries if path.is_file()]
    if len(directories) == 1 and not files and (directories[0] / "manifest.yaml").exists():
        return directories[0]

    raise PackageIntakeError(
        "manifest not found: expected manifest.yaml at archive root or inside a single top-level directory"
    )
