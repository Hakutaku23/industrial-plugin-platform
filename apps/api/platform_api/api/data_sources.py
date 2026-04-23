from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from platform_api.api.common import client_ip, store
from platform_api.security import Principal, require_permission
from platform_api.services.license_guard import LicenseGuardError, ensure_data_source_create_allowed

router = APIRouter(prefix='/api/v1', tags=['data-sources'])


class DataSourceRequest(BaseModel):
    name: str
    connector_type: str = Field(pattern='^(mock|redis|tdengine)$')
    config: dict[str, Any] = Field(default_factory=dict)
    read_enabled: bool = True
    write_enabled: bool = False


@router.post('/data-sources', status_code=status.HTTP_201_CREATED)
def create_data_source(request: DataSourceRequest, principal: Principal = Depends(require_permission('datasource.create'))) -> dict[str, object]:
    metadata_store = store()
    try:
        ensure_data_source_create_allowed(store=metadata_store)
        result = metadata_store.create_data_source(
            name=request.name,
            connector_type=request.connector_type,
            config=request.config,
            read_enabled=request.read_enabled,
            write_enabled=request.write_enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LicenseGuardError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    metadata_store.record_audit_event(
        event_type='security.datasource.created',
        target_type='data_source',
        target_id=str(result.id),
        actor=principal.username,
        details={'name': result.name, 'connector_type': result.connector_type},
    )
    return {'id': result.id, 'name': result.name, 'connector_type': result.connector_type, 'status': result.status}


@router.put('/data-sources/{data_source_id}')
def update_data_source(data_source_id: int, request: DataSourceRequest, principal: Principal = Depends(require_permission('datasource.update'))) -> dict[str, object]:
    metadata_store = store()
    try:
        result = metadata_store.update_data_source(
            data_source_id=data_source_id,
            name=request.name,
            connector_type=request.connector_type,
            config=request.config,
            read_enabled=request.read_enabled,
            write_enabled=request.write_enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail=f'data source not found: {data_source_id}')
    metadata_store.record_audit_event(
        event_type='security.datasource.updated',
        target_type='data_source',
        target_id=str(result.id),
        actor=principal.username,
        details={'name': result.name, 'connector_type': result.connector_type},
    )
    return {'id': result.id, 'name': result.name, 'connector_type': result.connector_type, 'status': result.status}


@router.get('/data-sources')
def list_data_sources(principal: Principal = Depends(require_permission('datasource.read'))) -> dict[str, object]:
    return {'items': store().list_data_sources()}


@router.delete('/data-sources/{data_source_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_data_source(data_source_id: int, request: Request, principal: Principal = Depends(require_permission('datasource.delete'))) -> None:
    metadata_store = store()
    deleted = metadata_store.delete_data_source(data_source_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f'data source not found: {data_source_id}')
    metadata_store.record_audit_event(
        event_type='security.datasource.deleted',
        target_type='data_source',
        target_id=str(data_source_id),
        actor=principal.username,
        details={'ip': client_ip(request)},
    )
