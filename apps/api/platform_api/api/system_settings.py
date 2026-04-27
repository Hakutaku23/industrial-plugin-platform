from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from platform_api.security import Principal, require_permission
from platform_api.services.database_cleanup import database_cleanup_service
from platform_api.services.run_directory_cleanup import run_directory_cleanup_service
from platform_api.services.system_settings import SystemSettingsError, SystemSettingsStore


router = APIRouter(prefix="/api/v1", tags=["system-settings"])


class UpdateSystemSettingsRequest(BaseModel):
    settings: dict[str, Any] = Field(default_factory=dict)


class ManualCleanupRequest(BaseModel):
    dry_run: bool | None = None


def store() -> SystemSettingsStore:
    return SystemSettingsStore()


@router.get("/system-settings")
def get_system_settings(principal: Principal = Depends(require_permission("system.read"))) -> dict[str, Any]:
    return {"settings": store().get(), "catalog": store().catalog()}


@router.put("/system-settings")
def update_system_settings(
    payload: UpdateSystemSettingsRequest,
    principal: Principal = Depends(require_permission("system.read")),
) -> dict[str, Any]:
    try:
        return {"settings": store().update(payload.settings, actor=principal.username), "catalog": store().catalog()}
    except SystemSettingsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/system-settings/catalog")
def get_system_settings_catalog(principal: Principal = Depends(require_permission("system.read"))) -> dict[str, Any]:
    return store().catalog()


@router.get("/system-settings/maintenance/status")
def get_maintenance_status(principal: Principal = Depends(require_permission("system.read"))) -> dict[str, Any]:
    return {
        "run_directory_cleanup": run_directory_cleanup_service.last_report(),
        "database_cleanup": database_cleanup_service.last_report(),
    }


@router.post("/system-settings/maintenance/run-directory-cleanup")
def run_run_directory_cleanup(
    payload: ManualCleanupRequest | None = None,
    principal: Principal = Depends(require_permission("system.read")),
) -> dict[str, Any]:
    return run_directory_cleanup_service.run_once(dry_run=(payload.dry_run if payload else None))


@router.post("/system-settings/maintenance/database-cleanup")
def run_database_cleanup(
    payload: ManualCleanupRequest | None = None,
    principal: Principal = Depends(require_permission("system.read")),
) -> dict[str, Any]:
    return database_cleanup_service.run_once(dry_run=(payload.dry_run if payload else None))
