from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from platform_api.security import Principal, require_permission
from platform_api.services.model_audit import record_model_audit_event
from platform_api.services.model_binding_guard import ModelBindingGuard
from platform_api.services.model_deletion import ModelDeletionError, ModelDeletionService
from platform_api.services.model_errors import ModelOperationError, model_error
from platform_api.services.model_registry import ModelRegistry, ModelRegistryError


router = APIRouter(prefix="/api/v1", tags=["models"])


class BindModelRequest(BaseModel):
    model_id: int
    binding_mode: str = Field(default="current", pattern="^(current|fixed_version)$")
    model_version_id: int | None = None


class PromoteRequest(BaseModel):
    reason: str = "manual promote"


class RollbackRequest(BaseModel):
    reason: str = "manual rollback"


class DeleteModelRequest(BaseModel):
    force: bool = False
    delete_files: bool = True
    reason: str = "manual model delete"


def registry() -> ModelRegistry:
    return ModelRegistry()


def guard() -> ModelBindingGuard:
    return ModelBindingGuard()


def deletion_service() -> ModelDeletionService:
    return ModelDeletionService()


def _raise_model_operation_error(exc: ModelOperationError) -> None:
    raise HTTPException(status_code=exc.http_status, detail=exc.to_detail()) from exc


def _raise_registry_error(exc: ModelRegistryError, *, code: str = "E_MODEL_OPERATION_FAILED", status_code: int = 400) -> None:
    raise HTTPException(status_code=status_code, detail={"code": code, "message": str(exc)}) from exc


def _raise_deletion_error(exc: ModelDeletionError) -> None:
    raise HTTPException(status_code=exc.http_status, detail=exc.to_detail()) from exc


@router.get("/models")
def list_models(principal: Principal = Depends(require_permission("package.read"))) -> dict[str, Any]:
    return {"items": registry().list_models()}


@router.get("/models/{model_id}")
def get_model(model_id: int, principal: Principal = Depends(require_permission("package.read"))) -> dict[str, Any]:
    result = registry().get_model(model_id)
    if result is None:
        raise HTTPException(status_code=404, detail={"code": "E_MODEL_NOT_FOUND", "message": f"model not found: {model_id}"})
    return result


@router.get("/models/{model_id}/delete-check")
def check_model_delete(model_id: int, principal: Principal = Depends(require_permission("package.read"))) -> dict[str, Any]:
    try:
        return deletion_service().check_delete(model_id)
    except ModelDeletionError as exc:
        _raise_deletion_error(exc)


@router.delete("/models/{model_id}")
def delete_model(
    model_id: int,
    payload: DeleteModelRequest | None = None,
    principal: Principal = Depends(require_permission("package.delete")),
) -> dict[str, Any]:
    request = payload or DeleteModelRequest()
    try:
        result = deletion_service().delete_model(
            model_id=model_id,
            force=request.force,
            delete_files=request.delete_files,
            actor=principal.username,
            reason=request.reason,
        )
        record_model_audit_event(
            event_type="model.deleted",
            target_type="model",
            target_id=str(model_id),
            actor=principal.username,
            details={
                "model_id": model_id,
                "model_name": result.get("model_name"),
                "delete_files": result.get("delete_files"),
                "deleted_files": result.get("deleted_files"),
                "reason": request.reason,
                "preflight": result.get("preflight"),
            },
        )
        return result
    except ModelDeletionError as exc:
        record_model_audit_event(
            event_type="model.delete_rejected",
            target_type="model",
            target_id=str(model_id),
            actor=principal.username,
            details={"model_id": model_id, "reason": request.reason, "error": exc.to_detail()},
        )
        _raise_deletion_error(exc)


@router.get("/models/{model_id}/versions")
def list_model_versions(model_id: int, principal: Principal = Depends(require_permission("package.read"))) -> dict[str, Any]:
    result = registry().list_versions(model_id)
    if result is None:
        raise HTTPException(status_code=404, detail={"code": "E_MODEL_NOT_FOUND", "message": f"model not found: {model_id}"})
    return {"items": result}


@router.post("/models/{model_id}/versions/{version_id}/validate")
def validate_model_version(
    model_id: int,
    version_id: int,
    principal: Principal = Depends(require_permission("package.upload")),
) -> dict[str, Any]:
    try:
        result = registry().validate_version(model_id=model_id, version_id=version_id)
        record_model_audit_event(
            event_type="model.version.validated",
            target_type="model_version",
            target_id=str(version_id),
            actor=principal.username,
            details={"model_id": model_id, "version_id": version_id, "version": result.get("version")},
        )
        return result
    except ModelRegistryError as exc:
        record_model_audit_event(
            event_type="model.version.validation_failed",
            target_type="model_version",
            target_id=str(version_id),
            actor=principal.username,
            details={"model_id": model_id, "version_id": version_id, "message": str(exc)},
        )
        _raise_registry_error(exc, code="E_MODEL_VERSION_VALIDATE_FAILED")


@router.post("/models/{model_id}/versions/{version_id}/promote")
def promote_model_version(
    model_id: int,
    version_id: int,
    payload: PromoteRequest | None = None,
    principal: Principal = Depends(require_permission("package.upload")),
) -> dict[str, Any]:
    reason = payload.reason if payload else "manual promote"
    try:
        result = registry().promote_version(
            model_id=model_id,
            version_id=version_id,
            actor=principal.username,
            reason=reason,
        )
        record_model_audit_event(
            event_type="model.version.promoted",
            target_type="model",
            target_id=str(model_id),
            actor=principal.username,
            details={
                "model_id": model_id,
                "version_id": version_id,
                "active_version": result.get("active_version"),
                "family_fingerprint": result.get("family_fingerprint"),
                "reason": reason,
            },
        )
        return result
    except ModelRegistryError as exc:
        record_model_audit_event(
            event_type="model.version.promote_failed",
            target_type="model",
            target_id=str(model_id),
            actor=principal.username,
            details={"model_id": model_id, "version_id": version_id, "reason": reason, "message": str(exc)},
        )
        _raise_registry_error(exc, code="E_MODEL_VERSION_PROMOTE_FAILED")


@router.post("/models/{model_id}/rollback")
def rollback_model(
    model_id: int,
    payload: RollbackRequest | None = None,
    principal: Principal = Depends(require_permission("package.upload")),
) -> dict[str, Any]:
    reason = payload.reason if payload else "manual rollback"
    try:
        result = registry().rollback(
            model_id=model_id,
            actor=principal.username,
            reason=reason,
        )
        record_model_audit_event(
            event_type="model.version.rollback",
            target_type="model",
            target_id=str(model_id),
            actor=principal.username,
            details={
                "model_id": model_id,
                "active_version": result.get("active_version"),
                "active_version_id": result.get("active_version_id"),
                "family_fingerprint": result.get("family_fingerprint"),
                "reason": reason,
            },
        )
        return result
    except ModelRegistryError as exc:
        record_model_audit_event(
            event_type="model.version.rollback_failed",
            target_type="model",
            target_id=str(model_id),
            actor=principal.username,
            details={"model_id": model_id, "reason": reason, "message": str(exc)},
        )
        _raise_registry_error(exc, code="E_MODEL_ROLLBACK_FAILED")


@router.get("/instances/{instance_id}/model-requirement")
def get_instance_model_requirement(
    instance_id: int,
    principal: Principal = Depends(require_permission("instance.read")),
) -> dict[str, Any]:
    try:
        return registry().get_instance_model_requirement(instance_id=instance_id)
    except ModelRegistryError as exc:
        _raise_registry_error(exc, code="E_MODEL_REQUIREMENT_RESOLVE_FAILED")


@router.get("/instances/{instance_id}/model-binding/health")
def get_instance_model_binding_health(
    instance_id: int,
    principal: Principal = Depends(require_permission("instance.read")),
) -> dict[str, Any]:
    try:
        return guard().evaluate_instance_binding(instance_id=instance_id, raise_on_error=False)
    except ModelOperationError as exc:
        _raise_model_operation_error(exc)


@router.post("/instances/{instance_id}/model-binding", status_code=status.HTTP_201_CREATED)
def bind_instance_model(
    instance_id: int,
    payload: BindModelRequest,
    principal: Principal = Depends(require_permission("instance.update")),
) -> dict[str, Any]:
    try:
        preflight = guard().validate_candidate_binding(
            instance_id=instance_id,
            model_id=payload.model_id,
            binding_mode=payload.binding_mode,
            model_version_id=payload.model_version_id,
        )
        result = registry().bind_instance(
            instance_id=instance_id,
            model_id=payload.model_id,
            binding_mode=payload.binding_mode,
            model_version_id=payload.model_version_id,
        )
        health = guard().evaluate_instance_binding(instance_id=instance_id, raise_on_error=False)
        record_model_audit_event(
            event_type="model.binding.created_or_updated",
            target_type="plugin_instance",
            target_id=str(instance_id),
            actor=principal.username,
            details={
                "instance_id": instance_id,
                "model_id": payload.model_id,
                "binding_mode": payload.binding_mode,
                "model_version_id": payload.model_version_id,
                "family_fingerprint": result.get("family_fingerprint"),
                "preflight_status": preflight.get("status"),
                "health_status": health.get("status"),
                "healthy": health.get("healthy"),
            },
        )
        return {**result, "health": health}
    except ModelOperationError as exc:
        record_model_audit_event(
            event_type="model.binding.rejected",
            target_type="plugin_instance",
            target_id=str(instance_id),
            actor=principal.username,
            details={"instance_id": instance_id, "payload": payload.model_dump(), "error": exc.to_detail()},
        )
        _raise_model_operation_error(exc)
    except ModelRegistryError as exc:
        record_model_audit_event(
            event_type="model.binding.rejected",
            target_type="plugin_instance",
            target_id=str(instance_id),
            actor=principal.username,
            details={"instance_id": instance_id, "payload": payload.model_dump(), "message": str(exc)},
        )
        _raise_registry_error(exc, code="E_MODEL_BINDING_FAILED")


@router.get("/instances/{instance_id}/model-binding")
def get_instance_model_binding(
    instance_id: int,
    principal: Principal = Depends(require_permission("instance.read")),
) -> dict[str, Any]:
    result = registry().get_instance_binding(instance_id=instance_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "E_MODEL_BINDING_NOT_FOUND", "message": f"model binding not found for instance: {instance_id}"},
        )
    try:
        health = guard().evaluate_instance_binding(instance_id=instance_id, raise_on_error=False)
    except ModelOperationError:
        health = None
    return {**result, "health": health}


@router.delete("/instances/{instance_id}/model-binding", status_code=status.HTTP_204_NO_CONTENT)
def delete_instance_model_binding(
    instance_id: int,
    principal: Principal = Depends(require_permission("instance.update")),
) -> None:
    existing = registry().get_instance_binding(instance_id=instance_id)
    deleted = registry().delete_instance_binding(instance_id=instance_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={"code": "E_MODEL_BINDING_NOT_FOUND", "message": f"model binding not found for instance: {instance_id}"},
        )
    record_model_audit_event(
        event_type="model.binding.deleted",
        target_type="plugin_instance",
        target_id=str(instance_id),
        actor=principal.username,
        details={"instance_id": instance_id, "previous_binding": existing or {}},
    )
