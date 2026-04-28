import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
RESERVED_OUTPUT_NAMES = {"status", "outputs", "logs", "metrics", "error"}


class ManifestError(ValueError):
    """Raised when a plugin manifest is missing or invalid."""


class PluginMetadata(BaseModel):
    name: str
    display_name: str = Field(alias="displayName")
    version: str
    author: str
    description: str
    tags: list[str] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not NAME_RE.match(value):
            raise ValueError("metadata.name must be kebab-case")
        return value

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        if not SEMVER_RE.match(value):
            raise ValueError("metadata.version must use semver, for example 0.1.0")
        return value


class EntrySpec(BaseModel):
    mode: Literal["function", "cli", "service"]
    entry_type: Literal["file", "module"] = Field(default="file", alias="type")
    file: str | None = None
    module: str | None = None
    callable: str | None = None
    command: list[str] | None = None
    health_endpoint: str | None = Field(default=None, alias="healthEndpoint")
    ready_signal: str | None = Field(default=None, alias="readySignal")

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("file")
    @classmethod
    def validate_file(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized:
            return None
        if normalized.startswith("/") or "\\" in normalized or ".." in Path(normalized).parts:
            raise ValueError("entry.file must be a safe package-relative path")
        return normalized

    @field_validator("module")
    @classmethod
    def validate_module(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized:
            return None
        parts = normalized.split(".")
        if any(not IDENTIFIER_RE.match(part) for part in parts):
            raise ValueError("entry.module must be a valid Python module path")
        return normalized

    @field_validator("callable")
    @classmethod
    def validate_callable(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized:
            return None
        if not IDENTIFIER_RE.match(normalized):
            raise ValueError("entry.callable must be a valid Python identifier")
        return normalized

    @model_validator(mode="after")
    def validate_entry(self) -> "EntrySpec":
        if self.mode == "function":
            if not self.callable:
                raise ValueError("function entry requires callable")
            if self.entry_type == "file" and not self.file:
                raise ValueError("function file entry requires file")
            if self.entry_type == "module":
                if not self.module:
                    raise ValueError("function module entry requires module")
                if not self.file:
                    self.file = self.module
        if self.mode in {"cli", "service"} and not self.command:
            raise ValueError(f"{self.mode} entry requires command")
        return self


class RuntimeSpec(BaseModel):
    python_version: str | None = Field(default=None, alias="pythonVersion")
    working_dir: str = Field(default=".", alias="workingDir")
    timeout_sec: int = Field(default=30, alias="timeoutSec")
    memory_mb: int | None = Field(default=None, alias="memoryMB")
    cpu_limit: float | None = Field(default=None, alias="cpuLimit")
    os: str | None = None
    arch: str | None = None
    env: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    @field_validator("timeout_sec")
    @classmethod
    def validate_timeout(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("runtime.timeoutSec must be positive")
        return value

    @field_validator("memory_mb")
    @classmethod
    def validate_memory(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("runtime.memoryMB must be positive")
        return value


class ScheduleSpec(BaseModel):
    type: Literal["manual", "interval", "cron", "event", "service"]
    interval_sec: int | None = Field(default=None, alias="intervalSec")
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class InterfaceSpec(BaseModel):
    name: str
    type: str
    required: bool = False
    writable: bool = False
    description: str | None = None
    unit: str | None = None
    schema_: dict[str, Any] | None = Field(default=None, alias="schema")
    limits: dict[str, Any] | None = None
    quality_aware: bool | None = Field(default=None, alias="qualityAware")
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    @field_validator("name")
    @classmethod
    def validate_interface_name(cls, value: str) -> str:
        if not value or value in RESERVED_OUTPUT_NAMES:
            raise ValueError(f"interface name is reserved or empty: {value}")
        return value


class PermissionsSpec(BaseModel):
    network: bool = False
    filesystem: Literal["scoped", "none", "readonly"] = "scoped"
    writeback: bool = False
    subprocess: bool = False
    model_config = ConfigDict(extra="allow")


class PluginSpec(BaseModel):
    plugin_type: Literal["python", "binary", "archive"] = Field(alias="pluginType")
    package_format: Literal["directory", "zip", "tar.gz"] = Field(alias="packageFormat")
    entry: EntrySpec
    runtime: RuntimeSpec
    schedule: ScheduleSpec
    inputs: list[InterfaceSpec]
    outputs: list[InterfaceSpec]
    permissions: PermissionsSpec
    model_config = ConfigDict(populate_by_name=True)


class CompatibilitySpec(BaseModel):
    platform_api: str = Field(alias="platformApi")
    runner_api: str = Field(alias="runnerApi")
    supported_environments: list[str] = Field(default_factory=list, alias="supportedEnvironments")
    model_config = ConfigDict(populate_by_name=True)


class ModelDependencySpec(BaseModel):
    required: bool = True
    family_fingerprint: str | None = Field(default=None, alias="familyFingerprint")
    model_name: str | None = Field(default=None, alias="modelName")
    role: str | None = None
    required_artifacts: list[str] = Field(default_factory=list, alias="requiredArtifacts")
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    @field_validator("family_fingerprint")
    @classmethod
    def validate_family_fingerprint(cls, value: str | None) -> str | None:
        if value is not None and not str(value).strip():
            raise ValueError("modelDependency.familyFingerprint must not be empty")
        return value


class ModelUpdateSpec(BaseModel):
    enabled: bool = False
    role: Literal["trainer", "evaluator", "updater"] = "trainer"
    family_fingerprint: str | None = Field(default=None, alias="familyFingerprint")
    required_artifacts: list[str] = Field(default_factory=list, alias="requiredArtifacts")
    output_schema: str = Field(default="ipp-model/v1", alias="outputSchema")
    candidate_dir_name: str = Field(default="candidate_model", alias="candidateDirName")
    current_model_dir_name: str = Field(default="current_model", alias="currentModelDirName")
    promote_mode: Literal["manual", "auto_if_passed"] = Field(default="manual", alias="promoteMode")
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    @field_validator("family_fingerprint")
    @classmethod
    def validate_family_fingerprint(cls, value: str | None) -> str | None:
        if value is not None and not str(value).strip():
            raise ValueError("modelUpdate.familyFingerprint must not be empty")
        return value

    @field_validator("candidate_dir_name", "current_model_dir_name")
    @classmethod
    def validate_dir_name(cls, value: str) -> str:
        normalized = str(value).strip()
        if not normalized or "/" in normalized or "\\" in normalized or normalized in {".", ".."}:
            raise ValueError("modelUpdate directory names must be safe single path segments")
        return normalized


class PluginManifest(BaseModel):
    api_version: Literal["plugin.platform/v1", "plugin.platform/v2"] = Field(alias="apiVersion")
    kind: Literal["PluginPackage"]
    metadata: PluginMetadata
    spec: PluginSpec
    compatibility: CompatibilitySpec
    config_schema: dict[str, Any] | None = Field(default=None, alias="configSchema")
    model_dependency: ModelDependencySpec | None = Field(default=None, alias="modelDependency")
    model_update: ModelUpdateSpec | None = Field(default=None, alias="modelUpdate")
    model_config = ConfigDict(populate_by_name=True)


def parse_manifest_text(content: str) -> PluginManifest:
    try:
        raw = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise ManifestError(f"manifest.yaml is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ManifestError("manifest.yaml must contain a YAML object")
    try:
        return PluginManifest.model_validate(raw)
    except ValidationError as exc:
        raise ManifestError(str(exc)) from exc


def load_manifest(path: Path) -> PluginManifest:
    if not path.exists():
        raise ManifestError(f"manifest not found: {path}")
    return parse_manifest_text(path.read_text(encoding="utf-8"))
