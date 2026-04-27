from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response

from platform_api.security import Principal, require_permission
from platform_api.services.license_manager import license_manager

router = APIRouter(prefix='/api/v1', tags=['license'])


@router.get('/license/status')
def get_license_status(principal: Principal = Depends(require_permission('system.read'))) -> dict[str, object]:
    return license_manager.get_snapshot(force_refresh=True).model_dump()


@router.get('/license/fingerprint')
def get_license_fingerprint(principal: Principal = Depends(require_permission('system.read'))) -> dict[str, object]:
    return license_manager.fingerprint_payload()


@router.get('/license/fingerprint/download')
def download_license_fingerprint(principal: Principal = Depends(require_permission('system.read'))) -> Response:
    payload = license_manager.fingerprint_payload()
    return Response(
        content=json.dumps(payload, ensure_ascii=False, indent=2),
        media_type='application/json',
        headers={'Content-Disposition': 'attachment; filename="license-fingerprint.json"'},
    )


@router.get('/license/revocations')
def get_license_revocations(principal: Principal = Depends(require_permission('system.read'))) -> dict[str, object]:
    path = license_manager.revocations_file_path
    if not path.exists():
        return {'revoked_license_ids': [], 'path': str(path)}
    try:
        parsed = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f'revocation registry invalid: {exc}') from exc
    return {'path': str(path), **parsed}


@router.post('/license', status_code=status.HTTP_201_CREATED)
async def upload_license(
    request: Request,
    principal: Principal = Depends(require_permission('user.update')),
) -> dict[str, object]:
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail='license body is empty')
    try:
        snapshot = license_manager.save_license_text(body.decode('utf-8'))
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail=f'license.lic must be utf-8 text: {exc}') from exc
    return snapshot.model_dump()
