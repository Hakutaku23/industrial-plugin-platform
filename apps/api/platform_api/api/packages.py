from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response as RawResponse
from pydantic import BaseModel, Field

from platform_api.api.common import client_ip, store
from platform_api.core.config import settings
from platform_api.security import Principal, require_permission
from platform_api.services.execution import PluginExecutionError, execute_plugin_version
from platform_api.services.license_guard import LicenseGuardError, ensure_manual_run_allowed, ensure_package_upload_allowed
from platform_api.services.package_storage import PackageStorage, PackageStorageError
from platform_api.services.plugin_template import build_python_function_template_archive

router = APIRouter(prefix='/api/v1', tags=['packages'])


class RunRequest(BaseModel):
    inputs: dict[str, object] = Field(default_factory=dict)
    config: dict[str, object] = Field(default_factory=dict)


@router.get('/templates/python-function-package.zip')
def download_python_function_template(principal: Principal = Depends(require_permission('package.read'))) -> RawResponse:
    archive = build_python_function_template_archive()
    headers = {
        'Content-Disposition': 'attachment; filename="python-function-plugin-template.zip"',
        'Cache-Control': 'no-store',
    }
    return RawResponse(content=archive, media_type='application/zip', headers=headers)


@router.post('/packages', status_code=status.HTTP_201_CREATED)
async def upload_package(
    request: Request,
    filename: str = Query(..., min_length=1),
    principal: Principal = Depends(require_permission('package.upload')),
) -> dict[str, object]:
    metadata_store = store()
    try:
        ensure_package_upload_allowed(store=metadata_store)
    except LicenseGuardError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    content = await request.body()
    if not content:
        raise HTTPException(status_code=400, detail='package body is empty')

    storage = PackageStorage(settings.package_storage_dir)
    try:
        record = storage.add_archive_bytes(filename=filename, content=content)
    except PackageStorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    registration = metadata_store.register_package_upload(record)
    metadata_store.record_audit_event(
        event_type='security.package.uploaded',
        target_type='plugin_version',
        target_id=str(registration.version_id),
        actor=principal.username,
        details={'filename': filename, 'package': record.manifest.metadata.name, 'version': record.manifest.metadata.version},
    )

    return {
        'package_id': registration.package_id,
        'version_id': registration.version_id,
        'audit_event_id': registration.audit_event_id,
        'name': record.manifest.metadata.name,
        'version': record.manifest.metadata.version,
        'status': registration.status,
        'digest': record.digest,
        'package_dir': str(record.package_dir),
        'manifest': record.manifest.model_dump(by_alias=True),
    }


@router.get('/packages')
def list_packages(principal: Principal = Depends(require_permission('package.read'))) -> dict[str, object]:
    return {'items': store().list_plugin_packages()}


@router.get('/packages/{package_name}/versions')
def list_package_versions(package_name: str, principal: Principal = Depends(require_permission('package.read'))) -> dict[str, object]:
    versions = store().list_plugin_versions(package_name)
    if versions is None:
        raise HTTPException(status_code=404, detail=f'plugin package not found: {package_name}')
    return {'items': versions}


@router.delete('/packages/{package_name}', status_code=status.HTTP_204_NO_CONTENT)
def delete_package(package_name: str, request: Request, principal: Principal = Depends(require_permission('package.delete'))) -> None:
    metadata_store = store()
    deleted = metadata_store.delete_plugin_package(package_name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f'plugin package not found: {package_name}')
    metadata_store.record_audit_event(
        event_type='security.package.deleted',
        target_type='plugin_package',
        target_id=package_name,
        actor=principal.username,
        details={'package': package_name, 'ip': client_ip(request)},
    )


@router.post('/packages/{package_name}/versions/{version}/runs', status_code=status.HTTP_201_CREATED)
def run_package_version(package_name: str, version: str, request: RunRequest, principal: Principal = Depends(require_permission('instance.run'))) -> dict[str, object]:
    try:
        ensure_manual_run_allowed()
        result = execute_plugin_version(package_name=package_name, version=version, inputs=request.inputs, config=request.config)
    except PluginExecutionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LicenseGuardError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    store().record_audit_event(
        event_type='security.package_version.run_triggered',
        target_type='plugin_version',
        target_id=f'{package_name}@{version}',
        actor=principal.username,
        details={'run_id': result.get('run_id'), 'status': result.get('status')},
    )
    return result
