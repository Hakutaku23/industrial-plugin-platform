from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from platform_api.security import Principal, require_permission
from platform_api.services.license_manager import get_license_manager

router = APIRouter(prefix='/api/v1', tags=['license'])


@router.get('/license/status')
def get_license_status(principal: Principal = Depends(require_permission('system.read'))) -> dict[str, object]:
    return get_license_manager().snapshot()


@router.get('/license/fingerprint')
def get_license_fingerprint(principal: Principal = Depends(require_permission('system.read'))) -> dict[str, object]:
    return get_license_manager().export_fingerprint()


@router.post('/license')
async def upload_license(file: UploadFile = File(...), principal: Principal = Depends(require_permission('user.assign_roles'))) -> dict[str, object]:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail='license body is empty')
    return get_license_manager().replace_license(content)
