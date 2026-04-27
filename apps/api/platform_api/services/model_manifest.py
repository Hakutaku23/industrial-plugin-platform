from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


ARTIFACT_KEY_RE = re.compile(r"^[A-Za-z0-9_-]+$")
MODEL_NAME_RE = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")


class ModelManifestError(ValueError):
    """Raised when a model artifact manifest is invalid."""


class ModelInfo(BaseModel):
    name: str
    version: str
    framework: str | None = None
    task_type: str | None = None
    entry_artifact: str = "model"
    description: str = ""

    model_config = ConfigDict(extra="allow")

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not MODEL_NAME_RE.match(value):
            raise ValueError("model.name must be lower kebab/snake case")
        return value

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        normalized = str(value).strip()
        if not normalized:
            raise ValueError("model.version must not be empty")
        if "/" in normalized or "\\" in normalized or ".." in normalized:
            raise ValueError("model.version contains unsafe path characters")
        return normalized


class ModelFamilyInfo(BaseModel):
    family_fingerprint: str
    role: str = "model_artifact"

    model_config = ConfigDict(extra="allow")

    @field_validator("family_fingerprint")
    @classmethod
    def validate_family(cls, value: str) -> str:
        normalized = str(value).strip()
        if not normalized:
            raise ValueError("model_family.family_fingerprint must not be empty")
        return normalized


class RuntimeContract(BaseModel):
    managed_by_plugin: bool = True
    note: str | None = None

    model_config = ConfigDict(extra="allow")


class ArtifactSpec(BaseModel):
    path: str
    type: str = "user_defined"
    role: str | None = None
    sha256: str | None = None

    model_config = ConfigDict(extra="allow")

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        _assert_safe_relative_path(value)
        return value


class TrainingInfo(BaseModel):
    source: str | None = None
    data_window: dict[str, Any] | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class ModelArtifactManifest(BaseModel):
    schema_: str = Field(alias="schema")
    model: ModelInfo
    model_family: ModelFamilyInfo
    runtime_contract: RuntimeContract = Field(default_factory=RuntimeContract)
    artifacts: dict[str, ArtifactSpec]
    training: TrainingInfo | None = None

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    @model_validator(mode="after")
    def validate_manifest(self) -> "ModelArtifactManifest":
        if self.schema_ != "ipp-model/v1":
            raise ValueError("schema must be ipp-model/v1")
        if not self.artifacts:
            raise ValueError("artifacts map must not be empty")
        for key in self.artifacts:
            if not ARTIFACT_KEY_RE.match(key):
                raise ValueError(f"artifact key contains unsupported characters: {key}")
        if self.model.entry_artifact not in self.artifacts:
            raise ValueError("model.entry_artifact must exist in artifacts map")
        return self

    def artifacts_json(self) -> dict[str, Any]:
        return {
            key: value.model_dump(exclude_none=True)
            for key, value in self.artifacts.items()
        }


def parse_model_manifest_text(content: str) -> ModelArtifactManifest:
    try:
        raw = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise ModelManifestError(f"manifest.yaml is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ModelManifestError("manifest.yaml must contain a YAML object")
    try:
        return ModelArtifactManifest.model_validate(raw)
    except ValidationError as exc:
        raise ModelManifestError(str(exc)) from exc


def load_model_manifest(path: Path) -> ModelArtifactManifest:
    if not path.exists():
        raise ModelManifestError(f"manifest not found: {path}")
    return parse_model_manifest_text(path.read_text(encoding="utf-8"))


def load_metrics(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema": "ipp-model-metrics/v1",
            "metrics": {},
            "metrics_completeness": {"reported": False, "missing_fields": []},
        }
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ModelManifestError(f"metrics.json is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ModelManifestError("metrics.json must contain a JSON object")
    return parsed


def load_checksums(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema": "ipp-model-checksums/v1", "files": {}}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ModelManifestError(f"checksums.json is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ModelManifestError("checksums.json must contain a JSON object")
    files = parsed.get("files", {})
    if not isinstance(files, dict):
        raise ModelManifestError("checksums.json files must be an object")
    for relative_path in files:
        _assert_safe_relative_path(str(relative_path))
    return parsed


def validate_artifact_files(package_root: Path, manifest: ModelArtifactManifest) -> None:
    root = package_root.resolve()
    for key, artifact in manifest.artifacts.items():
        artifact_path = (root / artifact.path).resolve()
        if root not in artifact_path.parents and artifact_path != root:
            raise ModelManifestError(f"artifact path escapes package root: {key}")
        if not artifact_path.is_file():
            raise ModelManifestError(f"artifact file not found: {key} -> {artifact.path}")
        if artifact.sha256:
            expected = _normalize_sha256(artifact.sha256)
            actual = sha256_file(artifact_path)
            if expected != actual:
                raise ModelManifestError(f"artifact sha256 mismatch: {key}")


def validate_checksums(package_root: Path, checksums: dict[str, Any]) -> None:
    files = checksums.get("files", {})
    if not files:
        return
    root = package_root.resolve()
    for relative_path, expected_raw in files.items():
        _assert_safe_relative_path(str(relative_path))
        path = (root / str(relative_path)).resolve()
        if root not in path.parents and path != root:
            raise ModelManifestError(f"checksum path escapes package root: {relative_path}")
        if not path.is_file():
            raise ModelManifestError(f"checksum file not found: {relative_path}")
        expected = _normalize_sha256(str(expected_raw))
        actual = sha256_file(path)
        if expected != actual:
            raise ModelManifestError(f"checksum mismatch: {relative_path}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_sha256(value: str) -> str:
    normalized = str(value).strip().lower()
    if normalized.startswith("sha256:"):
        normalized = normalized.split(":", 1)[1]
    if not re.fullmatch(r"[0-9a-f]{64}", normalized):
        raise ModelManifestError("sha256 value must be sha256:<64 hex> or 64 hex")
    return normalized


def _assert_safe_relative_path(value: str) -> None:
    raw = str(value).strip()
    if not raw:
        raise ModelManifestError("relative path must not be empty")
    path = PurePosixPath(raw.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts:
        raise ModelManifestError(f"unsafe relative path: {value}")
