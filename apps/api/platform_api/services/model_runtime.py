from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select

from platform_api.core.config import settings
from platform_api.services.model_registry import (
    ModelBindingModel,
    ModelRecordModel,
    ModelRegistry,
    ModelRegistryError,
    ModelVersionModel,
)


class ModelRuntimeError(RuntimeError):
    """Raised when a bound model cannot be prepared for a plugin run."""


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
    """Materialize the model bound to an instance into this run directory.

    This package intentionally does not change the Rust runner working directory yet.
    Therefore the injected model paths are absolute paths under var/runs/<run_id>/model,
    not model-store paths and not package-relative paths.
    """

    model_registry = registry or ModelRegistry()
    model_registry.initialize()

    with model_registry.session_factory() as session:
        binding = session.scalar(
            select(ModelBindingModel).where(ModelBindingModel.instance_id == int(instance_id))
        )
        if binding is None:
            return None

        model = session.get(ModelRecordModel, binding.model_id)
        if model is None:
            raise ModelRuntimeError(f"bound model not found: {binding.model_id}")

        if binding.binding_mode == "current":
            version_id = model.active_version_id
            if version_id is None:
                raise ModelRuntimeError(f"bound model has no active version: {model.model_name}")
        elif binding.binding_mode == "fixed_version":
            version_id = binding.model_version_id
            if version_id is None:
                raise ModelRuntimeError("fixed_version model binding has no model_version_id")
        else:
            raise ModelRuntimeError(f"unsupported model binding mode: {binding.binding_mode}")

        version = session.get(ModelVersionModel, int(version_id))
        if version is None or version.model_id != model.id:
            raise ModelRuntimeError(f"bound model version not found: {version_id}")

        try:
            requirement = model_registry.get_instance_model_requirement(instance_id=int(instance_id))
        except ModelRegistryError as exc:
            raise ModelRuntimeError(str(exc)) from exc
        required_family_fingerprint = str(requirement.get("family_fingerprint") or "").strip()
        if not required_family_fingerprint:
            raise ModelRuntimeError(
                "plugin manifest does not declare modelDependency.familyFingerprint; refuse model runtime preparation"
            )
        if version.family_fingerprint != required_family_fingerprint:
            raise ModelRuntimeError(
                "bound model family_fingerprint mismatch at runtime: "
                f"plugin requires {required_family_fingerprint}, model provides {version.family_fingerprint}"
            )

        source_dir = Path(version.artifact_dir).resolve()
        if not source_dir.is_dir():
            raise ModelRuntimeError(f"model artifact directory not found: {source_dir}")

        run_dir = (settings.run_storage_dir / run_id).resolve()
        runtime_dir_name = _runtime_model_dir_name()
        runtime_dir = (run_dir / runtime_dir_name).resolve()
        materialization_mode = _materialization_mode()
        _materialize_model_dir(source_dir=source_dir, runtime_dir=runtime_dir, run_dir=run_dir, mode=materialization_mode)

        context = model_registry._runtime_model_context(  # noqa: SLF001 - controlled platform internal use.
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
        }
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
        raise ModelRuntimeError(f"refusing to remove model runtime path outside run dir: {runtime_dir}")
    if runtime_dir.is_symlink() or runtime_dir.is_file():
        runtime_dir.unlink()
    elif runtime_dir.exists():
        shutil.rmtree(runtime_dir)
