from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from platform_api.security import Principal, require_permission
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


def registry() -> ModelRegistry:
    return ModelRegistry()


@router.get("/models")
def list_models(principal: Principal = Depends(require_permission("package.read"))) -> dict[str, Any]:
    return {"items": registry().list_models()}


@router.get("/models/{model_id}")
def get_model(model_id: int, principal: Principal = Depends(require_permission("package.read"))) -> dict[str, Any]:
    result = registry().get_model(model_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"model not found: {model_id}")
    return result


@router.get("/models/{model_id}/versions")
def list_model_versions(model_id: int, principal: Principal = Depends(require_permission("package.read"))) -> dict[str, Any]:
    result = registry().list_versions(model_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"model not found: {model_id}")
    return {"items": result}


@router.post("/models/{model_id}/versions/{version_id}/validate")
def validate_model_version(
    model_id: int,
    version_id: int,
    principal: Principal = Depends(require_permission("package.upload")),
) -> dict[str, Any]:
    try:
        return registry().validate_version(model_id=model_id, version_id=version_id)
    except ModelRegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/models/{model_id}/versions/{version_id}/promote")
def promote_model_version(
    model_id: int,
    version_id: int,
    payload: PromoteRequest | None = None,
    principal: Principal = Depends(require_permission("package.upload")),
) -> dict[str, Any]:
    try:
        return registry().promote_version(
            model_id=model_id,
            version_id=version_id,
            actor=principal.username,
            reason=(payload.reason if payload else "manual promote"),
        )
    except ModelRegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/models/{model_id}/rollback")
def rollback_model(
    model_id: int,
    payload: RollbackRequest | None = None,
    principal: Principal = Depends(require_permission("package.upload")),
) -> dict[str, Any]:
    try:
        return registry().rollback(
            model_id=model_id,
            actor=principal.username,
            reason=(payload.reason if payload else "manual rollback"),
        )
    except ModelRegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/instances/{instance_id}/model-requirement")
def get_instance_model_requirement(
    instance_id: int,
    principal: Principal = Depends(require_permission("instance.read")),
) -> dict[str, Any]:
    try:
        return registry().get_instance_model_requirement(instance_id=instance_id)
    except ModelRegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/instances/{instance_id}/model-binding", status_code=status.HTTP_201_CREATED)
def bind_instance_model(
    instance_id: int,
    payload: BindModelRequest,
    principal: Principal = Depends(require_permission("instance.update")),
) -> dict[str, Any]:
    try:
        return registry().bind_instance(
            instance_id=instance_id,
            model_id=payload.model_id,
            binding_mode=payload.binding_mode,
            model_version_id=payload.model_version_id,
        )
    except ModelRegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/instances/{instance_id}/model-binding")
def get_instance_model_binding(
    instance_id: int,
    principal: Principal = Depends(require_permission("instance.read")),
) -> dict[str, Any]:
    result = registry().get_instance_binding(instance_id=instance_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"model binding not found for instance: {instance_id}")
    return result


@router.delete("/instances/{instance_id}/model-binding", status_code=status.HTTP_204_NO_CONTENT)
def delete_instance_model_binding(
    instance_id: int,
    principal: Principal = Depends(require_permission("instance.update")),
) -> None:
    deleted = registry().delete_instance_binding(instance_id=instance_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"model binding not found for instance: {instance_id}")
