from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from platform_api.core.config import settings
from platform_api.services.execution import (
    PluginExecutionError,
    execute_plugin_instance,
    execute_plugin_version,
)
from platform_api.services.instance_validation import (
    BindingValidationError,
    validate_instance_bindings,
)
from platform_api.services.manifest import PluginManifest
from platform_api.services.metadata_store import MetadataStore
from platform_api.services.package_storage import PackageStorage, PackageStorageError
from platform_api.services.scheduler import scheduler

router = APIRouter(prefix="/api/v1")


def _metadata_target() -> str | object:
    return getattr(settings, 'metadata_database', getattr(settings, 'metadata_db_path'))


def _store() -> MetadataStore:
    return MetadataStore(_metadata_target())


def _load_manifest(package_name: str, version: str) -> PluginManifest:
    version_record = _store().get_plugin_version(package_name, version)
    if version_record is None:
        raise HTTPException(
            status_code=404,
            detail=f"plugin version not found: {package_name}@{version}",
        )
    return PluginManifest.model_validate(version_record["manifest"])


class RunRequest(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)


class DataSourceRequest(BaseModel):
    name: str
    connector_type: str = Field(pattern="^(mock|redis)$")
    config: dict[str, Any] = Field(default_factory=dict)
    read_enabled: bool = True
    write_enabled: bool = False


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


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/scheduler/status")
def scheduler_status() -> dict[str, object]:
    return {
        "enabled": settings.scheduler.enabled,
        **scheduler.status_snapshot(),
    }


@router.post("/packages", status_code=status.HTTP_201_CREATED)
async def upload_package(
    request: Request,
    filename: str = Query(..., min_length=1),
) -> dict[str, object]:
    content = await request.body()
    if not content:
        raise HTTPException(status_code=400, detail="package body is empty")

    storage = PackageStorage(settings.package_storage_dir)
    try:
        record = storage.add_archive_bytes(filename=filename, content=content)
    except PackageStorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    registration = _store().register_package_upload(record)

    return {
        "package_id": registration.package_id,
        "version_id": registration.version_id,
        "audit_event_id": registration.audit_event_id,
        "name": record.manifest.metadata.name,
        "version": record.manifest.metadata.version,
        "status": registration.status,
        "digest": record.digest,
        "package_dir": str(record.package_dir),
        "manifest": record.manifest.model_dump(by_alias=True),
    }


@router.get("/packages")
def list_packages() -> dict[str, object]:
    return {"items": _store().list_plugin_packages()}


@router.get("/packages/{package_name}/versions")
def list_package_versions(package_name: str) -> dict[str, object]:
    versions = _store().list_plugin_versions(package_name)
    if versions is None:
        raise HTTPException(status_code=404, detail=f"plugin package not found: {package_name}")
    return {"items": versions}


@router.delete("/packages/{package_name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_package(package_name: str) -> None:
    deleted = _store().delete_plugin_package(package_name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"plugin package not found: {package_name}")


@router.post("/data-sources", status_code=status.HTTP_201_CREATED)
def upsert_data_source(request: DataSourceRequest) -> dict[str, object]:
    result = _store().upsert_data_source(
        name=request.name,
        connector_type=request.connector_type,
        config=request.config,
        read_enabled=request.read_enabled,
        write_enabled=request.write_enabled,
    )
    return {
        "id": result.id,
        "name": result.name,
        "connector_type": result.connector_type,
        "status": result.status,
    }


@router.get("/data-sources")
def list_data_sources() -> dict[str, object]:
    return {"items": _store().list_data_sources()}


@router.delete("/data-sources/{data_source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_data_source(data_source_id: int) -> None:
    deleted = _store().delete_data_source(data_source_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"data source not found: {data_source_id}")


@router.post("/instances", status_code=status.HTTP_201_CREATED)
def upsert_plugin_instance(request: PluginInstanceRequest) -> dict[str, object]:
    manifest = _load_manifest(request.package_name, request.version)
    try:
        validate_instance_bindings(
            manifest=manifest,
            input_bindings=request.input_bindings,
            output_bindings=request.output_bindings,
        )
    except BindingValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result = _store().upsert_plugin_instance(
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
            detail=f"plugin version not found: {request.package_name}@{request.version}",
        )
    return {"id": result.id, "name": result.name, "status": result.status}


@router.put("/instances/{instance_id}")
def update_plugin_instance(instance_id: int, request: PluginInstanceRequest) -> dict[str, object]:
    manifest = _load_manifest(request.package_name, request.version)
    try:
        validate_instance_bindings(
            manifest=manifest,
            input_bindings=request.input_bindings,
            output_bindings=request.output_bindings,
        )
    except BindingValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result = _store().update_plugin_instance(
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
            detail=f"plugin instance or version not found: {instance_id}",
        )
    return {"id": result.id, "name": result.name, "status": result.status}


@router.get("/instances")
def list_plugin_instances() -> dict[str, object]:
    return {"items": _store().list_plugin_instances()}


@router.patch("/instances/{instance_id}/schedule")
def update_plugin_instance_schedule(
    instance_id: int,
    request: InstanceScheduleRequest,
) -> dict[str, object]:
    result = _store().set_plugin_instance_schedule(
        instance_id=instance_id,
        enabled=request.enabled,
        interval_sec=request.interval_sec,
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"plugin instance not found: {instance_id}")
    return result


@router.delete("/instances/{instance_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plugin_instance(instance_id: int) -> None:
    deleted = _store().delete_plugin_instance(instance_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"plugin instance not found: {instance_id}")


@router.post("/instances/{instance_id}/runs", status_code=status.HTTP_201_CREATED)
def run_plugin_instance(instance_id: int) -> dict[str, object]:
    try:
        return execute_plugin_instance(instance_id=instance_id)
    except PluginExecutionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/packages/{package_name}/versions/{version}/runs", status_code=status.HTTP_201_CREATED)
def run_package_version(package_name: str, version: str, request: RunRequest) -> dict[str, object]:
    try:
        return execute_plugin_version(
            package_name=package_name,
            version=version,
            inputs=request.inputs,
            config=request.config,
        )
    except PluginExecutionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/runs")
def list_runs(package_name: str | None = None, instance_id: int | None = None) -> dict[str, object]:
    return {
        "items": _store().list_plugin_runs(
            package_name=package_name,
            instance_id=instance_id,
        )
    }


@router.get("/runs/{run_id}/logs")
def list_run_logs(run_id: str) -> dict[str, object]:
    return {"items": _store().list_run_logs(run_id)}


@router.get("/writeback-records")
def list_writeback_records(run_id: str | None = None) -> dict[str, object]:
    return {"items": _store().list_writeback_records(run_id)}


@router.get("/audit-events")
def list_audit_events() -> dict[str, object]:
    return {"items": _store().list_audit_events()}
