from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import select

from platform_api.core.config import settings
from platform_api.services.metadata_store import MetadataStore
from platform_api.services.model_errors import ModelOperationError, model_error
from platform_api.services.model_manifest import ModelManifestError, load_checksums, load_model_manifest, validate_artifact_files, validate_checksums
from platform_api.services.model_registry import ModelBindingModel, ModelRecordModel, ModelRegistry, ModelVersionModel


class ModelBindingGuard:
    """Centralized hard checks for model binding and runtime preparation."""

    def __init__(self, registry: ModelRegistry | None = None, metadata_store: MetadataStore | None = None) -> None:
        self.registry = registry or ModelRegistry()
        self.registry.initialize()
        self.metadata_store = metadata_store or MetadataStore(settings.metadata_database)

    def validate_candidate_binding(
        self,
        *,
        instance_id: int,
        model_id: int,
        binding_mode: str,
        model_version_id: int | None,
    ) -> dict[str, Any]:
        instance = self._require_instance(instance_id)
        requirement = self._require_model_requirement(instance)
        binding_mode = (binding_mode or "current").strip()
        if binding_mode not in {"current", "fixed_version"}:
            raise model_error("E_MODEL_BINDING_MODE_INVALID", "binding_mode must be current or fixed_version")

        with self.registry.session_factory() as session:
            model = session.get(ModelRecordModel, int(model_id))
            if model is None:
                raise model_error("E_MODEL_NOT_FOUND", f"model not found: {model_id}", http_status=404)
            if model.family_fingerprint != requirement["family_fingerprint"]:
                raise model_error(
                    "E_MODEL_FINGERPRINT_MISMATCH",
                    "model family_fingerprint does not match plugin requirement",
                    plugin_family_fingerprint=requirement["family_fingerprint"],
                    model_family_fingerprint=model.family_fingerprint,
                )

            if binding_mode == "current":
                if model.active_version_id is None:
                    raise model_error("E_MODEL_ACTIVE_VERSION_MISSING", f"model has no active version: {model.model_name}")
                version = session.get(ModelVersionModel, int(model.active_version_id))
                if version is None or version.model_id != model.id:
                    raise model_error("E_MODEL_ACTIVE_VERSION_MISSING", f"active model version not found: {model.active_version_id}")
            else:
                if model_version_id is None:
                    raise model_error("E_MODEL_FIXED_VERSION_REQUIRED", "fixed_version binding requires model_version_id")
                version = session.get(ModelVersionModel, int(model_version_id))
                if version is None or version.model_id != model.id:
                    raise model_error("E_MODEL_FIXED_VERSION_MISSING", f"model version not found: {model_version_id}", http_status=404)

            return self._evaluate_bound_records(
                instance=instance,
                requirement=requirement,
                binding={
                    "instance_id": int(instance_id),
                    "model_id": model.id,
                    "model_version_id": version.id if binding_mode == "fixed_version" else None,
                    "binding_mode": binding_mode,
                    "family_fingerprint": model.family_fingerprint,
                },
                model=model,
                version=version,
                raise_on_error=True,
            )

    def assert_instance_runtime_ready(self, *, instance_id: int) -> dict[str, Any]:
        health = self.evaluate_instance_binding(instance_id=instance_id, raise_on_error=True)
        if not health.get("healthy"):
            first = (health.get("errors") or [{}])[0]
            raise model_error(
                str(first.get("code") or "E_MODEL_BINDING_NOT_READY"),
                str(first.get("message") or "model binding is not ready"),
                diagnostics=health,
            )
        return health

    def evaluate_instance_binding(self, *, instance_id: int, raise_on_error: bool = False) -> dict[str, Any]:
        instance = self.metadata_store.get_plugin_instance(int(instance_id))
        if instance is None:
            health = self._health(
                instance_id=instance_id,
                status="INSTANCE_NOT_FOUND",
                healthy=False,
                errors=[{"code": "E_INSTANCE_NOT_FOUND", "message": f"plugin instance not found: {instance_id}"}],
            )
            if raise_on_error:
                raise model_error("E_INSTANCE_NOT_FOUND", f"plugin instance not found: {instance_id}", http_status=404, diagnostics=health)
            return health

        requirement = self._extract_instance_model_requirement(instance)
        with self.registry.session_factory() as session:
            binding = session.scalar(select(ModelBindingModel).where(ModelBindingModel.instance_id == int(instance_id)))
            if requirement is None and binding is None:
                return self._health(
                    instance_id=instance_id,
                    status="NO_MODEL_REQUIREMENT",
                    healthy=True,
                    instance=instance,
                    requirement=None,
                    binding=None,
                )
            if requirement is None and binding is not None:
                health = self._health(
                    instance_id=instance_id,
                    status="BOUND_WITHOUT_REQUIREMENT",
                    healthy=False,
                    instance=instance,
                    requirement=None,
                    binding=self._binding_record_to_dict(binding),
                    errors=[{"code": "E_PLUGIN_MODEL_REQUIREMENT_MISSING", "message": "plugin manifest does not declare modelDependency.familyFingerprint"}],
                )
                if raise_on_error:
                    raise model_error("E_PLUGIN_MODEL_REQUIREMENT_MISSING", "plugin manifest does not declare modelDependency.familyFingerprint", diagnostics=health)
                return health
            assert requirement is not None
            if binding is None:
                health = self._health(
                    instance_id=instance_id,
                    status="REQUIRED_UNBOUND",
                    healthy=False,
                    instance=instance,
                    requirement=requirement,
                    binding=None,
                    errors=[{"code": "E_MODEL_BINDING_REQUIRED", "message": "plugin requires a compatible model binding"}],
                )
                if raise_on_error:
                    raise model_error("E_MODEL_BINDING_REQUIRED", "plugin requires a compatible model binding", diagnostics=health)
                return health

            model = session.get(ModelRecordModel, binding.model_id)
            if model is None:
                health = self._health(
                    instance_id=instance_id,
                    status="MODEL_NOT_FOUND",
                    healthy=False,
                    instance=instance,
                    requirement=requirement,
                    binding=self._binding_record_to_dict(binding),
                    errors=[{"code": "E_MODEL_NOT_FOUND", "message": f"bound model not found: {binding.model_id}"}],
                )
                if raise_on_error:
                    raise model_error("E_MODEL_NOT_FOUND", f"bound model not found: {binding.model_id}", diagnostics=health)
                return health

            if binding.binding_mode == "current":
                version_id = model.active_version_id
            elif binding.binding_mode == "fixed_version":
                version_id = binding.model_version_id
            else:
                version_id = None

            version = session.get(ModelVersionModel, int(version_id)) if version_id is not None else None
            if version is None or version.model_id != model.id:
                code = "E_MODEL_ACTIVE_VERSION_MISSING" if binding.binding_mode == "current" else "E_MODEL_FIXED_VERSION_MISSING"
                status = "ACTIVE_VERSION_MISSING" if binding.binding_mode == "current" else "FIXED_VERSION_MISSING"
                health = self._health(
                    instance_id=instance_id,
                    status=status,
                    healthy=False,
                    instance=instance,
                    requirement=requirement,
                    binding=self._binding_record_to_dict(binding),
                    model=self._model_record_to_dict(model),
                    errors=[{"code": code, "message": "bound model version not found"}],
                )
                if raise_on_error:
                    raise model_error(code, "bound model version not found", diagnostics=health)
                return health

            health = self._evaluate_bound_records(
                instance=instance,
                requirement=requirement,
                binding=self._binding_record_to_dict(binding),
                model=model,
                version=version,
                raise_on_error=False,
            )
            if raise_on_error and not health.get("healthy"):
                first = (health.get("errors") or [{}])[0]
                raise model_error(str(first.get("code") or "E_MODEL_BINDING_NOT_READY"), str(first.get("message") or "model binding is not ready"), diagnostics=health)
            return health

    def _evaluate_bound_records(
        self,
        *,
        instance: dict[str, Any],
        requirement: dict[str, Any],
        binding: dict[str, Any],
        model: ModelRecordModel,
        version: ModelVersionModel,
        raise_on_error: bool,
    ) -> dict[str, Any]:
        errors: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []

        required_family = str(requirement.get("family_fingerprint") or "").strip()
        if binding.get("family_fingerprint") != required_family:
            errors.append({
                "code": "E_MODEL_BINDING_FINGERPRINT_MISMATCH",
                "message": "stored binding family_fingerprint does not match plugin requirement",
                "binding_family_fingerprint": binding.get("family_fingerprint"),
                "plugin_family_fingerprint": required_family,
            })
        if model.family_fingerprint != required_family:
            errors.append({
                "code": "E_MODEL_FINGERPRINT_MISMATCH",
                "message": "model family_fingerprint does not match plugin requirement",
                "model_family_fingerprint": model.family_fingerprint,
                "plugin_family_fingerprint": required_family,
            })
        if version.family_fingerprint != required_family:
            errors.append({
                "code": "E_MODEL_VERSION_FINGERPRINT_MISMATCH",
                "message": "model version family_fingerprint does not match plugin requirement",
                "version_family_fingerprint": version.family_fingerprint,
                "plugin_family_fingerprint": required_family,
            })

        if version.status not in {"ACTIVE", "VALIDATED"}:
            errors.append({
                "code": "E_MODEL_VERSION_NOT_VALIDATED",
                "message": "bound model version must be ACTIVE or VALIDATED before runtime use",
                "status": version.status,
            })

        artifacts = _json_object(version.artifacts_json)
        required_artifacts = [str(item).strip() for item in requirement.get("required_artifacts", []) if str(item).strip()]
        for key in required_artifacts:
            if key not in artifacts:
                errors.append({"code": "E_MODEL_REQUIRED_ARTIFACT_MISSING", "message": f"required artifact missing: {key}", "artifact": key})

        artifact_dir = Path(version.artifact_dir).resolve()
        if not artifact_dir.is_dir():
            errors.append({"code": "E_MODEL_ARTIFACT_DIR_MISSING", "message": f"model artifact directory not found: {artifact_dir}"})
        else:
            root = artifact_dir
            for key, spec in artifacts.items():
                rel = str(spec.get("path", "")).strip() if isinstance(spec, dict) else ""
                if not rel:
                    errors.append({"code": "E_MODEL_ARTIFACT_PATH_EMPTY", "message": f"artifact path is empty: {key}", "artifact": key})
                    continue
                path = (root / rel).resolve()
                if root not in path.parents and path != root:
                    errors.append({"code": "E_MODEL_ARTIFACT_PATH_ESCAPE", "message": f"artifact path escapes model directory: {key}", "artifact": key, "path": rel})
                    continue
                if not path.is_file():
                    errors.append({"code": "E_MODEL_ARTIFACT_FILE_MISSING", "message": f"artifact file not found: {key} -> {rel}", "artifact": key, "path": rel})
            try:
                manifest = load_model_manifest(root / "manifest.yaml")
                validate_artifact_files(root, manifest)
                checksums = load_checksums(root / "checksums.json")
                validate_checksums(root, checksums)
            except ModelManifestError as exc:
                errors.append({"code": "E_MODEL_PACKAGE_INTEGRITY_FAILED", "message": str(exc)})

        status = "OK" if not errors else str(errors[0]["code"]).removeprefix("E_MODEL_")
        health = self._health(
            instance_id=int(instance["id"]),
            status=status,
            healthy=not errors,
            instance=instance,
            requirement=requirement,
            binding=binding,
            model=self._model_record_to_dict(model),
            version=self._version_record_to_dict(version),
            errors=errors,
            warnings=warnings,
        )
        if raise_on_error and errors:
            first = errors[0]
            raise model_error(str(first["code"]), str(first["message"]), diagnostics=health)
        return health

    def _require_instance(self, instance_id: int) -> dict[str, Any]:
        instance = self.metadata_store.get_plugin_instance(int(instance_id))
        if instance is None:
            raise model_error("E_INSTANCE_NOT_FOUND", f"plugin instance not found: {instance_id}", http_status=404)
        return instance

    def _require_model_requirement(self, instance: dict[str, Any]) -> dict[str, Any]:
        requirement = self._extract_instance_model_requirement(instance)
        if requirement is None:
            raise model_error(
                "E_PLUGIN_MODEL_REQUIREMENT_MISSING",
                "plugin manifest does not declare modelDependency.familyFingerprint; refuse model binding",
            )
        return requirement

    def _extract_instance_model_requirement(self, instance: dict[str, Any]) -> dict[str, Any] | None:
        version_record = self.metadata_store.get_plugin_version(str(instance.get("package_name", "")), str(instance.get("version", "")))
        if version_record is None:
            return None
        manifest = version_record.get("manifest") or {}
        if not isinstance(manifest, dict):
            return None
        dependency = _extract_model_dependency(manifest)
        if not dependency:
            return None
        family = _first_string(
            dependency,
            "familyFingerprint",
            "family_fingerprint",
            "modelFamilyFingerprint",
            "model_family_fingerprint",
        )
        if not family:
            return None
        required_artifacts = _string_list(dependency.get("requiredArtifacts") or dependency.get("required_artifacts") or [])
        return {
            "required": bool(dependency.get("required", True)),
            "family_fingerprint": family,
            "role": _first_string(dependency, "role") or "inference",
            "required_artifacts": required_artifacts,
            "raw": dependency,
        }

    def _health(self, *, instance_id: int, status: str, healthy: bool, instance: dict[str, Any] | None = None, requirement: dict[str, Any] | None = None, binding: dict[str, Any] | None = None, model: dict[str, Any] | None = None, version: dict[str, Any] | None = None, errors: list[dict[str, Any]] | None = None, warnings: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        return {
            "instance_id": int(instance_id),
            "status": status,
            "healthy": bool(healthy),
            "instance": _instance_summary(instance),
            "requirement": requirement,
            "binding": binding,
            "model": model,
            "version": version,
            "errors": errors or [],
            "warnings": warnings or [],
        }

    def _binding_record_to_dict(self, row: ModelBindingModel) -> dict[str, Any]:
        return {
            "id": row.id,
            "instance_id": row.instance_id,
            "model_id": row.model_id,
            "model_version_id": row.model_version_id,
            "binding_mode": row.binding_mode,
            "family_fingerprint": row.family_fingerprint,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
        }

    def _model_record_to_dict(self, row: ModelRecordModel) -> dict[str, Any]:
        return {
            "id": row.id,
            "model_name": row.model_name,
            "display_name": row.display_name,
            "family_fingerprint": row.family_fingerprint,
            "status": row.status,
            "active_version_id": row.active_version_id,
        }

    def _version_record_to_dict(self, row: ModelVersionModel) -> dict[str, Any]:
        return {
            "id": row.id,
            "model_id": row.model_id,
            "version": row.version,
            "family_fingerprint": row.family_fingerprint,
            "status": row.status,
            "artifact_dir": row.artifact_dir,
            "artifacts": _json_object(row.artifacts_json),
        }


def _extract_model_dependency(manifest: dict[str, Any]) -> dict[str, Any] | None:
    candidates = [manifest.get("modelDependency"), manifest.get("model_dependency")]
    spec = manifest.get("spec")
    if isinstance(spec, dict):
        candidates.extend([spec.get("modelDependency"), spec.get("model_dependency")])
    for candidate in candidates:
        if isinstance(candidate, dict):
            return candidate
    return None


def _first_string(record: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = str(item).strip()
        if text and text not in result:
            result.append(text)
    return result


def _json_object(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _instance_summary(instance: dict[str, Any] | None) -> dict[str, Any] | None:
    if not instance:
        return None
    return {
        "id": instance.get("id"),
        "name": instance.get("name"),
        "package_name": instance.get("package_name"),
        "version": instance.get("version"),
        "status": instance.get("status"),
    }
