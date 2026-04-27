from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from platform_api.security import Principal, require_permission
from platform_api.services.runtime_diagnostics import RuntimeDiagnostics, RuntimeDiagnosticsError


router = APIRouter(prefix="/api/v1", tags=["runtime-diagnostics"])


def diagnostics() -> RuntimeDiagnostics:
    return RuntimeDiagnostics()


@router.get("/runtime-diagnostics/model-bindings")
def list_model_binding_health(
    principal: Principal = Depends(require_permission("instance.read")),
) -> dict[str, Any]:
    return diagnostics().list_model_binding_health()


@router.get("/instances/{instance_id}/model-binding/diagnostics")
def get_instance_model_binding_diagnostics(
    instance_id: int,
    principal: Principal = Depends(require_permission("instance.read")),
) -> dict[str, Any]:
    try:
        return diagnostics().instance_model_binding_health(instance_id)
    except RuntimeDiagnosticsError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs/{run_id}/diagnostics")
def get_run_diagnostics(
    run_id: str,
    principal: Principal = Depends(require_permission("run.read")),
) -> dict[str, Any]:
    try:
        return diagnostics().run_diagnostics(run_id)
    except RuntimeDiagnosticsError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
