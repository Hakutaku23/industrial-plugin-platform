from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from platform_api.api.common import store
from platform_api.security import Principal, require_permission
from platform_api.services.execution import PluginExecutionError, execute_plugin_instance_locked

router = APIRouter(prefix='/api/v1', tags=['instances'])


class PluginInstanceRequest(BaseModel):
    name: str
    package_name: str
    version: str
    input_bindings: list[dict[str, Any]] = Field(default_factory=list)
    output_bindings: list[dict[str, Any]] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    writeback_enabled: bool = False
    schedule_enabled: bool = False
    schedule_interval_sec: int = Field(default=30, ge=5, le=86400)


class InstanceScheduleRequest(BaseModel):
    enabled: bool
    interval_sec: int | None = Field(default=None, ge=5, le=86400)


@router.post('/instances', status_code=status.HTTP_201_CREATED)
def upsert_plugin_instance(
    request: PluginInstanceRequest,
    principal: Principal = Depends(require_permission('instance.create')),
) -> dict[str, object]:
    metadata_store = store()
    result = metadata_store.upsert_plugin_instance(
        name=request.name,
        package_name=request.package_name,
        version=request.version,
        input_bindings=request.input_bindings,
        output_bindings=request.output_bindings,
        config=request.config,
        writeback_enabled=request.writeback_enabled,
        schedule_enabled=request.schedule_enabled,
        schedule_interval_sec=request.schedule_interval_sec,
    )
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f'plugin version not found: {request.package_name}@{request.version}',
        )
    metadata_store.record_audit_event(
        event_type='security.instance.created',
        target_type='plugin_instance',
        target_id=str(result.id),
        actor=principal.username,
        details={'name': result.name, 'package': request.package_name, 'version': request.version},
    )
    return {'id': result.id, 'name': result.name, 'status': result.status}


@router.put('/instances/{instance_id}')
def update_plugin_instance(
    instance_id: int,
    request: PluginInstanceRequest,
    principal: Principal = Depends(require_permission('instance.update')),
) -> dict[str, object]:
    metadata_store = store()
    result = metadata_store.update_plugin_instance(
        instance_id=instance_id,
        name=request.name,
        package_name=request.package_name,
        version=request.version,
        input_bindings=request.input_bindings,
        output_bindings=request.output_bindings,
        config=request.config,
        writeback_enabled=request.writeback_enabled,
        schedule_enabled=request.schedule_enabled,
        schedule_interval_sec=request.schedule_interval_sec,
    )
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f'plugin instance or version not found: {instance_id}',
        )
    metadata_store.record_audit_event(
        event_type='security.instance.updated',
        target_type='plugin_instance',
        target_id=str(result.id),
        actor=principal.username,
        details={'name': result.name, 'package': request.package_name, 'version': request.version},
    )
    return {'id': result.id, 'name': result.name, 'status': result.status}


@router.get('/instances')
def list_plugin_instances(principal: Principal = Depends(require_permission('instance.read'))) -> dict[str, object]:
    return {'items': store().list_plugin_instances()}


@router.patch('/instances/{instance_id}/schedule')
def update_plugin_instance_schedule(
    instance_id: int,
    request: InstanceScheduleRequest,
    principal: Principal = Depends(require_permission('instance.schedule.update')),
) -> dict[str, object]:
    metadata_store = store()
    result = metadata_store.set_plugin_instance_schedule(
        instance_id=instance_id,
        enabled=request.enabled,
        interval_sec=request.interval_sec,
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f'plugin instance not found: {instance_id}')
    metadata_store.record_audit_event(
        event_type='security.instance.schedule_updated',
        target_type='plugin_instance',
        target_id=str(instance_id),
        actor=principal.username,
        details={'enabled': request.enabled, 'interval_sec': request.interval_sec},
    )
    return result


@router.delete('/instances/{instance_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_plugin_instance(
    instance_id: int,
    principal: Principal = Depends(require_permission('instance.delete')),
) -> None:
    metadata_store = store()
    deleted = metadata_store.delete_plugin_instance(instance_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f'plugin instance not found: {instance_id}')
    metadata_store.record_audit_event(
        event_type='security.instance.deleted',
        target_type='plugin_instance',
        target_id=str(instance_id),
        actor=principal.username,
        details={},
    )


@router.post('/instances/{instance_id}/runs', status_code=status.HTTP_201_CREATED)
def run_plugin_instance(
    instance_id: int,
    principal: Principal = Depends(require_permission('instance.run')),
) -> dict[str, object]:
    try:
        result = execute_plugin_instance_locked(instance_id=instance_id)
    except PluginExecutionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    store().record_audit_event(
        event_type='security.instance.run_triggered',
        target_type='plugin_instance',
        target_id=str(instance_id),
        actor=principal.username,
        details={'run_id': result.get('run_id'), 'status': result.get('status')},
    )
    return result
