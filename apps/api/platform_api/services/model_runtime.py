from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select

from platform_api.core.config import settings
from platform_api.services.model_audit import record_model_audit_event
from platform_api.services.model_binding_guard import ModelBindingGuard
from platform_api.services.model_errors import ModelOperationError
from platform_api.services.model_registry import (
    ModelBindingModel,
    ModelRecordModel,
    ModelRegistry,
    ModelVersionModel,
)


class ModelRuntimeError(RuntimeError):
    """Raised when a bound model cannot be prepared for a plugin run."""

    def __init__(self, message: str, *, code: str = "E_MODEL_RUNTIME_FAILED", details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}

    def __str__(self) -> str:
        return f"{self.code}: {super().__str__()}"


@dataclass(frozen=True)
class ModelRuntimePreparation:
    context: dict[str, Any]
    env: dict[str, str]
    metrics: dict[str, Any]
    source_dir: Path
    runtime_dir: Path
    materialization_mode: str


def prepare_instance_model_runtime(
    *,
    instance_id: int,
    run_id: str,
    registry: ModelRegistry | None = None,
) -> ModelRuntimePreparation | None:
    """Materialize a compatible bound model into var/runs/<run_id>/model.

    Runtime rules:
    - plugins without modelDependency may run without a model binding;
    - plugins declaring modelDependency must have a healthy compatible binding;
    - stale or incompatible bindings are rejected before plugin process startup.
    """

    model_registry = registry or ModelRegistry()
    model_registry.initialize()
    binding_guard = ModelBindingGuard(registry=model_registry)

    health = binding_guard.evaluate_instance_binding(instance_id=int(instance_id), raise_on_error=False)
    if health.get("status") == "NO_MODEL_REQUIREMENT" and health.get("healthy"):
        return None
    if not health.get("healthy"):
        first_error = (health.get("errors") or [{}])[0]
        code = str(first_error.get("code") or "E_MODEL_BINDING_NOT_READY")
        message = str(first_error.get("message") or "model binding is not ready")
        record_model_audit_event(
            event_type="model.runtime.blocked",
            target_type="plugin_instance",
            target_id=str(instance_id),
            details={"run_id": run_id, "code": code, "message": message, "health": health},
        )
        raise ModelRuntimeError(message, code=code, details={"health": health})

    try:
        binding_guard.assert_instance_runtime_ready(instance_id=int(instance_id))
    except ModelOperationError as exc:
        record_model_audit_event(
            event_type="model.runtime.blocked",
            target_type="plugin_instance",
            target_id=str(instance_id),
            details={"run_id": run_id, "error": exc.to_detail()},
        )
        raise ModelRuntimeError(exc.message, code=exc.code, details=exc.details) from exc

    with model_registry.session_factory() as session:
        binding = session.scalar(select(ModelBindingModel).where(ModelBindingModel.instance_id == int(instance_id)))
        if binding is None:
            raise ModelRuntimeError("model binding disappeared before runtime preparation", code="E_MODEL_BINDING_NOT_FOUND")

        model = session.get(ModelRecordModel, binding.model_id)
        if model is None:
            raise ModelRuntimeError(f"bound model not found: {binding.model_id}", code="E_MODEL_NOT_FOUND")

        if binding.binding_mode == "current":
            version_id = model.active_version_id
            if version_id is None:
                raise ModelRuntimeError(f"bound model has no active version: {model.model_name}", code="E_MODEL_ACTIVE_VERSION_MISSING")
        elif binding.binding_mode == "fixed_version":
            version_id = binding.model_version_id
            if version_id is None:
                raise ModelRuntimeError("fixed_version model binding has no model_version_id", code="E_MODEL_FIXED_VERSION_MISSING")
        else:
            raise ModelRuntimeError(f"unsupported model binding mode: {binding.binding_mode}", code="E_MODEL_BINDING_MODE_INVALID")

        version = session.get(ModelVersionModel, int(version_id))
        if version is None or version.model_id != model.id:
            raise ModelRuntimeError(f"bound model version not found: {version_id}", code="E_MODEL_VERSION_NOT_FOUND")

        source_dir = Path(version.artifact_dir).resolve()
        if not source_dir.is_dir():
            raise ModelRuntimeError(f"model artifact directory not found: {source_dir}", code="E_MODEL_ARTIFACT_DIR_MISSING")

        run_dir = (settings.run_storage_dir / run_id).resolve()
        runtime_dir_name = _runtime_model_dir_name()
        runtime_dir = (run_dir / runtime_dir_name).resolve()
        materialization_mode = _materialization_mode()
        _materialize_model_dir(source_dir=source_dir, runtime_dir=runtime_dir, run_dir=run_dir, mode=materialization_mode)

        context = model_registry._runtime_model_context(  # noqa: SLF001 - platform-internal protocol bridge.
            model=model,
            version=version,
            runtime_model_dir=str(runtime_dir),
        )
        artifacts_json = json.dumps(context.get("artifacts", {}), ensure_ascii=False, sort_keys=True)
        env = {
            "IPP_MODEL_DIR": str(runtime_dir),
            "IPP_MODEL_MANIFEST": str(runtime_dir / "manifest.yaml"),
            "IPP_MODEL_ARTIFACTS_JSON": artifacts_json,
        }
        metrics = {
            "model_name": model.model_name,
            "model_version": version.version,
            "model_artifact_id": version.id,
            "family_fingerprint": version.family_fingerprint,
            "model_binding_mode": binding.binding_mode,
            "model_materialization_mode": materialization_mode,
            "model_runtime_dir": str(runtime_dir),
            "model_binding_health": health.get("status"),
        }
        record_model_audit_event(
            event_type="model.runtime.prepared",
            target_type="plugin_instance",
            target_id=str(instance_id),
            details={
                "run_id": run_id,
                "model_id": model.id,
                "model_name": model.model_name,
                "model_version_id": version.id,
                "model_version": version.version,
                "binding_mode": binding.binding_mode,
                "materialization_mode": materialization_mode,
                "runtime_dir": str(runtime_dir),
            },
        )
        return ModelRuntimePreparation(
            context=context,
            env=env,
            metrics=metrics,
            source_dir=source_dir,
            runtime_dir=runtime_dir,
            materialization_mode=materialization_mode,
        )


def _materialization_mode() -> str:
    value = os.getenv("PLATFORM_MODEL_MATERIALIZATION_MODE", "symlink").strip().lower()
    if value not in {"symlink", "copy"}:
        return "symlink"
    return value


def _runtime_model_dir_name() -> str:
    value = os.getenv("PLATFORM_RUNTIME_MODEL_DIR_NAME", "model").strip()
    if not value or "/" in value or "\\" in value or value in {".", ".."}:
        return "model"
    return value


def _materialize_model_dir(*, source_dir: Path, runtime_dir: Path, run_dir: Path, mode: str) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    _remove_existing_runtime_dir(runtime_dir=runtime_dir, run_dir=run_dir)
    if mode == "copy":
        shutil.copytree(source_dir, runtime_dir)
        return
    try:
        runtime_dir.symlink_to(source_dir, target_is_directory=True)
    except OSError:
        shutil.copytree(source_dir, runtime_dir)


def _remove_existing_runtime_dir(*, runtime_dir: Path, run_dir: Path) -> None:
    resolved_run = run_dir.resolve()
    resolved_target = runtime_dir.resolve() if runtime_dir.exists() else runtime_dir.absolute()
    if resolved_run == resolved_target or resolved_run not in resolved_target.parents:
        raise ModelRuntimeError(f"refusing to remove model runtime path outside run dir: {runtime_dir}", code="E_MODEL_RUNTIME_PATH_UNSAFE")
    if runtime_dir.is_symlink() or runtime_dir.is_file():
        runtime_dir.unlink()
    elif runtime_dir.exists():
        shutil.rmtree(runtime_dir)
