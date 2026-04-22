from __future__ import annotations

from fastapi import APIRouter, Depends

from platform_api.core.config import settings
from platform_api.security import Principal, require_permission
from platform_api.services.scheduler import scheduler

router = APIRouter(prefix='/api/v1', tags=['scheduler'])


@router.get('/scheduler/status')
def scheduler_status(principal: Principal = Depends(require_permission('system.read'))) -> dict[str, object]:
    return {
        'enabled': settings.scheduler.enabled,
        **scheduler.status_snapshot(),
    }


@router.get('/scheduler/locks')
def scheduler_locks(principal: Principal = Depends(require_permission('system.read'))) -> dict[str, object]:
    return {
        'items': scheduler.lock_snapshot(),
    }
