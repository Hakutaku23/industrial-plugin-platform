from __future__ import annotations

from fastapi import APIRouter, Depends

from platform_api.api.common import store
from platform_api.security import Principal, require_permission

router = APIRouter(prefix='/api/v1', tags=['runs'])


@router.get('/runs')
def list_runs(
    package_name: str | None = None,
    instance_id: int | None = None,
    principal: Principal = Depends(require_permission('run.read')),
) -> dict[str, object]:
    return {
        'items': store().list_plugin_runs(
            package_name=package_name,
            instance_id=instance_id,
        )
    }


@router.get('/runs/{run_id}/logs')
def list_run_logs(run_id: str, principal: Principal = Depends(require_permission('run.read'))) -> dict[str, object]:
    return {'items': store().list_run_logs(run_id)}


@router.get('/writeback-records')
def list_writeback_records(
    run_id: str | None = None,
    principal: Principal = Depends(require_permission('run.read')),
) -> dict[str, object]:
    return {'items': store().list_writeback_records(run_id)}


@router.get('/audit-events')
def list_audit_events(principal: Principal = Depends(require_permission('audit.read'))) -> dict[str, object]:
    return {'items': store().list_audit_events()}
