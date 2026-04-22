from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from platform_api.core.config import settings
from platform_api.security import Principal, require_permission
from platform_api.ui import frontend_is_available

router = APIRouter(prefix='/api/v1', tags=['system'])


@router.get('/health')
def health() -> dict[str, str]:
    return {'status': 'ok'}


@router.get('/security/status')
def security_status() -> dict[str, Any]:
    return {
        'enabled': settings.security.enabled,
        'auth_mode': 'local-session',
        'session_cookie_name': settings.security.session_cookie_name,
    }


@router.get('/system/runtime')
def system_runtime(principal: Principal = Depends(require_permission('system.read'))) -> dict[str, Any]:
    return {
        'environment': settings.environment,
        'security_enabled': settings.security.enabled,
        'auth_mode': 'local-session' if settings.security.enabled else 'disabled',
        'ui_mode': 'static-dist' if frontend_is_available() else 'vite-dev',
        'scheduler_enabled': settings.scheduler.enabled,
    }
