import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from platform_api.core.config import settings
from platform_api.services.connectors import ConnectorError, build_connector, ensure_tag_access
from platform_api.services.execution_lock import LockManagerError, RedisExecutionLockManager
from platform_api.services.instance_validation import BindingValidationError, validate_execution_inputs
from platform_api.services.manifest import PluginManifest
from platform_api.services.metadata_store import MetadataStore, PluginInstanceModel
from platform_runner.executor import LocalPythonRunner, RunnerExecutionError


class PluginExecutionError(ValueError):
    """Raised when a plugin version cannot be executed by the local MVP runner."""


def execute_plugin_version(
    *,
    package_name: str,
    version: str,
    inputs: dict[str, Any],
    config: dict[str, Any],
    trigger_type: str = "manual",
    instance_id: int | None = None,
    store: MetadataStore | None = None,
) -> dict[str, Any]:
    metadata_store = store or MetadataStore(settings.metadata_database)
    version_record = metadata_store.get_plugin_version(package_name, version)
    if version_record is None:
        raise PluginExecutionError(f"plugin version not found: {package_name}@{version}")

    manifest = PluginManifest.model_validate(version_record["manifest"])
    if manifest.spec.plugin_type != "python" or manifest.spec.entry.mode != "function":
        raise PluginExecutionError("local MVP execution only supports python:function plugins")

    try:
        validate_execution_inputs(manifest=manifest, inputs=inputs)
    except BindingValidationError as exc:
        raise PluginExecutionError(str(exc)) from exc

    run_id = f"run-{uuid.uuid4().hex}"
    started_at = datetime.now(UTC)
    payload = {
        "context": {
            "run_id": run_id,
            "instance_id": instance_id,
            "plugin": package_name,
            "version": version,
            "timestamp": started_at.isoformat(),
            "attempt": 1,
            "trigger_type": trigger_type,
            "environment": settings.environment,
        },
        "inputs": inputs,
        "config": config,
        "capabilities": manifest.spec.permissions.model_dump(),
    }

    outputs: dict[str, Any] = {}
    metrics: dict[str, Any] = {}
    logs: list[dict[str, str]] = [{"source": "runner", "level": "INFO", "message": "local run started"}]
    error: dict[str, Any] | None = None
    status = "FAILED"

    try:
        package_dir = _resolve_package_path(str(version_record["package_path"]))
        runner_result = LocalPythonRunner().execute_function(
            package_dir=package_dir,
            entry_file=manifest.spec.entry.file or "",
            callable_name=manifest.spec.entry.callable or "",
            payload=payload,
            timeout_sec=manifest.spec.runtime.timeout_sec,
        )
        outputs = runner_result.outputs
        metrics = runner_result.metrics
        logs.extend({"source": "plugin", "level": "INFO", "message": message} for message in runner_result.logs)
        if runner_result.stderr:
            logs.append({"source": "plugin_stderr", "level": "WARN", "message": runner_result.stderr[-2000:]})
        status = _map_plugin_status(runner_result.status)
    except subprocess.TimeoutExpired as exc:
        status = "TIMED_OUT"
        error = {"code": "E_TIMEOUT", "message": str(exc)}
        logs.append({"source": "runner", "level": "ERROR", "message": "plugin execution timed out"})
    except RunnerExecutionError as exc:
        status = "FAILED"
        error = {"code": "E_RUNTIME_FAILED", "message": str(exc)}
        logs.append({"source": "runner", "level": "ERROR", "message": str(exc)})

    finished_at = datetime.now(UTC)
    recorded = metadata_store.record_plugin_run(
        run_id=run_id,
        package_id=int(version_record["package_id"]),
        version_id=int(version_record["id"]),
        instance_id=instance_id,
        trigger_type=trigger_type,
        environment=settings.environment,
        status=status,
        inputs=inputs,
        outputs=outputs,
        metrics=metrics,
        logs=logs,
        error=error,
        started_at=started_at,
        finished_at=finished_at,
    )

    return {"id": recorded.id, "run_id": recorded.run_id, "status": recorded.status, "outputs": outputs, "metrics": metrics, "error": error or {}}


def execute_plugin_instance(
    *,
    instance_id: int,
    trigger_type: str = "manual",
    store: MetadataStore | None = None,
) -> dict[str, Any]:
    metadata_store = store or MetadataStore(settings.metadata_database)
    instance = metadata_store.get_plugin_instance(instance_id)
    if instance is None:
        raise PluginExecutionError(f"plugin instance not found: {instance_id}")

    resolved_inputs: dict[str, Any] = {}
    try:
        resolved_inputs = _resolve_bound_inputs(instance, metadata_store)
    except Exception as exc:
        return _record_failed_instance_run(metadata_store=metadata_store, instance=instance, trigger_type=trigger_type, inputs=resolved_inputs, error_code="E_INPUT_BINDING_FAILED", error_message=str(exc))

    try:
        result = execute_plugin_version(
            package_name=instance["package_name"],
            version=instance["version"],
            inputs=resolved_inputs,
            config=instance["config"],
            trigger_type=trigger_type,
            instance_id=instance_id,
            store=metadata_store,
        )
    except PluginExecutionError as exc:
        return _record_failed_instance_run(metadata_store=metadata_store, instance=instance, trigger_type=trigger_type, inputs=resolved_inputs, error_code="E_EXECUTION_SETUP_FAILED", error_message=str(exc))

    try:
        writeback = _apply_output_bindings(run_id=result["run_id"], outputs=result["outputs"], instance=instance, store=metadata_store)
    except Exception as exc:
        metadata_store.record_audit_event(event_type="plugin.instance.writeback_failed", target_type="plugin_instance", target_id=str(instance_id), details={"message": str(exc), "run_id": result["run_id"], "exception_type": type(exc).__name__})
        writeback = [{"output_name": "*", "data_source_id": -1, "target_tag": "*", "value": None, "status": "failed", "reason": str(exc), "dry_run": True}]
    return {**result, "inputs": resolved_inputs, "writeback": writeback}


def execute_plugin_instance_locked(
    *,
    instance_id: int,
    trigger_type: str = "manual",
    store: MetadataStore | None = None,
    lock_manager: RedisExecutionLockManager | None = None,
) -> dict[str, Any]:
    metadata_store = store or MetadataStore(settings.metadata_database)
    manager = lock_manager or RedisExecutionLockManager.from_settings()
    ttl_sec = resolve_instance_lock_ttl_sec(instance_id=instance_id, store=metadata_store)

    try:
        lease = manager.acquire(instance_id, ttl_sec=ttl_sec)
    except LockManagerError as exc:
        try:
            metadata_store.record_audit_event(
                event_type="plugin.instance.lock_error",
                target_type="plugin_instance",
                target_id=str(instance_id),
                details={"message": str(exc), "phase": "acquire", "trigger_type": trigger_type},
            )
        except Exception:
            pass
        raise PluginExecutionError(str(exc)) from exc
    if lease is None:
        try:
            metadata_store.record_audit_event(
                event_type="plugin.instance.lock_conflict",
                target_type="plugin_instance",
                target_id=str(instance_id),
                details={"message": "plugin instance is already running", "trigger_type": trigger_type},
            )
        except Exception:
            pass
        raise PluginExecutionError(f"plugin instance is already running: {instance_id}")

    running_at = _db_now()
    _mark_instance_running(metadata_store, instance_id=instance_id, running_at=running_at)
    try:
        return execute_plugin_instance(
            instance_id=instance_id,
            trigger_type=trigger_type,
            store=metadata_store,
        )
    finally:
        try:
            _finalize_instance_after_execution(
                metadata_store,
                instance_id=instance_id,
                finished_at=_db_now(),
            )
        finally:
            try:
                manager.release(lease)
            except LockManagerError as exc:
                try:
                    metadata_store.record_audit_event(
                        event_type="plugin.instance.lock_error",
                        target_type="plugin_instance",
                        target_id=str(instance_id),
                        details={"message": str(exc), "phase": "release", "trigger_type": trigger_type},
                    )
                except Exception:
                    pass
                raise


def resolve_instance_lock_ttl_sec(
    *,
    instance_id: int,
    store: MetadataStore | None = None,
) -> int:
    metadata_store = store or MetadataStore(settings.metadata_database)
    ttl_sec = max(30, int(settings.scheduler.lock_ttl_sec))
    instance = metadata_store.get_plugin_instance(instance_id)
    if instance is None:
        return ttl_sec

    version_record = metadata_store.get_plugin_version(instance["package_name"], instance["version"])
    if version_record is None:
        return ttl_sec

    try:
        manifest = PluginManifest.model_validate(version_record["manifest"])
        timeout_sec = int(manifest.spec.runtime.timeout_sec)
    except Exception:
        timeout_sec = int(settings.runner.default_timeout_sec)

    return max(ttl_sec, timeout_sec + 30)


def _record_failed_instance_run(*, metadata_store: MetadataStore, instance: dict[str, Any], trigger_type: str, inputs: dict[str, Any], error_code: str, error_message: str) -> dict[str, Any]:
    started_at = datetime.now(UTC)
    version_record = metadata_store.get_plugin_version(instance["package_name"], instance["version"])
    if version_record is None:
        raise PluginExecutionError(f"plugin version not found for instance: {instance['package_name']}@{instance['version']}")
    run_id = f"run-{uuid.uuid4().hex}"
    recorded = metadata_store.record_plugin_run(
        run_id=run_id,
        package_id=int(version_record["package_id"]),
        version_id=int(version_record["id"]),
        instance_id=int(instance["id"]),
        trigger_type=trigger_type,
        environment=settings.environment,
        status="FAILED",
        inputs=inputs,
        outputs={},
        metrics={},
        logs=[{"source": "scheduler" if trigger_type == "schedule" else "runner", "level": "ERROR", "message": error_message}],
        error={"code": error_code, "message": error_message},
        started_at=started_at,
        finished_at=datetime.now(UTC),
    )
    return {"id": recorded.id, "run_id": recorded.run_id, "status": recorded.status, "inputs": inputs, "outputs": {}, "metrics": {}, "error": {"code": error_code, "message": error_message}, "writeback": []}


def _resolve_package_path(package_path: str) -> Path:
    path = Path(package_path)
    return path if path.is_absolute() else (settings.project_root / path).resolve()


def _map_plugin_status(status: str) -> str:
    normalized = status.lower()
    if normalized == "success":
        return "COMPLETED"
    if normalized == "partial_success":
        return "PARTIAL_SUCCESS"
    return "FAILED"


def _resolve_bound_inputs(instance: dict[str, Any], store: MetadataStore) -> dict[str, Any]:
    resolved: dict[str, Any] = {}
    for binding in instance["input_bindings"]:
        input_name = str(binding.get("input_name", "")).strip()
        data_source = store.get_data_source(int(binding["data_source_id"]))
        if data_source is None:
            raise PluginExecutionError(f"input data source not found: {binding['data_source_id']}")
        connector = build_connector(data_source, store)
        binding_type = str(binding.get("binding_type", "single")).lower()
        try:
            if binding_type == "batch":
                output_format = str(binding.get("output_format", "named-map")).lower()
                source_mappings = _normalize_source_mappings(binding.get("source_mappings"))
                source_tags = _normalize_tags(binding.get("source_tags"))

                if output_format == "named-map" and not input_name:
                    if not source_mappings:
                        raise PluginExecutionError("named-map batch input binding without input_name has no source_mappings")
                    read_tags = _unique_tags([item["tag"] for item in source_mappings])
                    values_by_tag = connector.read_tags(read_tags)
                    for item in source_mappings:
                        resolved[item["key"]] = values_by_tag[item["tag"]]
                    continue

                read_tags = _unique_tags([item["tag"] for item in source_mappings] if source_mappings else source_tags)
                if not read_tags:
                    raise PluginExecutionError(f"batch input binding has no source tags: {input_name}")
                values_by_tag = connector.read_tags(read_tags)
                if output_format == "ordered-list":
                    ordered_tags = source_tags or read_tags
                    resolved[input_name] = [values_by_tag[tag] for tag in ordered_tags]
                elif output_format == "named-map":
                    resolved[input_name] = ({item["key"]: values_by_tag[item["tag"]] for item in source_mappings} if source_mappings else {tag: values_by_tag[tag] for tag in read_tags})
                else:
                    raise PluginExecutionError(f"unsupported batch input output_format for {input_name}: {output_format}")
                continue

            source_tag = str(binding.get("source_tag", "")).strip()
            if not source_tag:
                raise PluginExecutionError(f"single input binding has no source tag: {input_name}")
            resolved[input_name] = connector.read_tag(source_tag)
        except ConnectorError as exc:
            raise PluginExecutionError(f"input binding failed for {input_name}: {exc}") from exc
    return resolved


def _apply_output_bindings(*, run_id: str, outputs: dict[str, Any], instance: dict[str, Any], store: MetadataStore) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for binding in instance["output_bindings"]:
        output_name = binding["output_name"]
        data_source_id = int(binding["data_source_id"])
        dry_run = bool(binding.get("dry_run", True))
        binding_type = str(binding.get("binding_type", "single")).lower()

        if binding_type == "batch":
            results.extend(_apply_batch_output_binding(run_id=run_id, outputs=outputs, instance=instance, store=store, output_name=output_name, data_source_id=data_source_id, target_tags=_normalize_tags(binding.get("target_tags")), dry_run=dry_run))
            continue

        target_tag = str(binding.get("target_tag", "")).strip()
        value = outputs.get(output_name)

        if output_name not in outputs:
            results.append(_record_writeback_result(store=store, run_id=run_id, output_name=output_name, data_source_id=data_source_id, target_tag=target_tag, value=None, status="blocked", reason="output_missing", dry_run=dry_run))
            continue

        if not target_tag:
            results.append(_record_writeback_result(store=store, run_id=run_id, output_name=output_name, data_source_id=data_source_id, target_tag="*", value=value, status="blocked", reason="target_tag_empty", dry_run=dry_run))
            continue

        data_source = store.get_data_source(data_source_id)
        if data_source is None:
            results.append(_record_writeback_result(store=store, run_id=run_id, output_name=output_name, data_source_id=data_source_id, target_tag=target_tag, value=value, status="blocked", reason="data_source_not_found", dry_run=dry_run))
            continue

        try:
            ensure_tag_access(data_source, target_tag, "write")
        except ConnectorError as exc:
            results.append(_record_writeback_result(store=store, run_id=run_id, output_name=output_name, data_source_id=data_source_id, target_tag=target_tag, value=value, status="blocked", reason=str(exc), dry_run=dry_run))
            continue

        if dry_run or not instance["writeback_enabled"]:
            results.append(_record_writeback_result(store=store, run_id=run_id, output_name=output_name, data_source_id=data_source_id, target_tag=target_tag, value=value, status="dry_run", reason="writeback disabled or dry_run binding", dry_run=True))
            continue

        try:
            build_connector(data_source, store).write_tag(target_tag, value)
            status = "success"
            reason = ""
        except ConnectorError as exc:
            status = "failed"
            reason = str(exc)

        results.append(_record_writeback_result(store=store, run_id=run_id, output_name=output_name, data_source_id=data_source_id, target_tag=target_tag, value=value, status=status, reason=reason, dry_run=False))
    return results


def _apply_batch_output_binding(*, run_id: str, outputs: dict[str, Any], instance: dict[str, Any], store: MetadataStore, output_name: str, data_source_id: int, target_tags: list[str], dry_run: bool) -> list[dict[str, Any]]:
    if not target_tags:
        return [_record_writeback_result(store=store, run_id=run_id, output_name=output_name, data_source_id=data_source_id, target_tag="*", value=None, status="blocked", reason="target_tags_empty", dry_run=dry_run)]
    if output_name not in outputs:
        return [_record_writeback_result(store=store, run_id=run_id, output_name=output_name, data_source_id=data_source_id, target_tag=target_tag, value=None, status="blocked", reason="output_missing", dry_run=dry_run) for target_tag in target_tags]
    output_value = outputs[output_name]
    if not isinstance(output_value, dict):
        return [_record_writeback_result(store=store, run_id=run_id, output_name=output_name, data_source_id=data_source_id, target_tag=target_tag, value=None, status="blocked", reason="batch_output_must_be_object", dry_run=dry_run) for target_tag in target_tags]
    data_source = store.get_data_source(data_source_id)
    if data_source is None:
        return [_record_writeback_result(store=store, run_id=run_id, output_name=output_name, data_source_id=data_source_id, target_tag=target_tag, value=output_value.get(target_tag), status="blocked", reason="data_source_not_found", dry_run=dry_run) for target_tag in target_tags]

    results: list[dict[str, Any]] = []
    writable_values: dict[str, Any] = {}
    for target_tag in target_tags:
        if target_tag not in output_value:
            results.append(_record_writeback_result(store=store, run_id=run_id, output_name=output_name, data_source_id=data_source_id, target_tag=target_tag, value=None, status="blocked", reason="target_value_missing", dry_run=dry_run))
            continue
        value = output_value[target_tag]
        try:
            ensure_tag_access(data_source, target_tag, "write")
        except ConnectorError as exc:
            results.append(_record_writeback_result(store=store, run_id=run_id, output_name=output_name, data_source_id=data_source_id, target_tag=target_tag, value=value, status="blocked", reason=str(exc), dry_run=dry_run))
            continue
        writable_values[target_tag] = value

    if not writable_values:
        return results
    if dry_run or not instance["writeback_enabled"]:
        for target_tag, value in writable_values.items():
            results.append(_record_writeback_result(store=store, run_id=run_id, output_name=output_name, data_source_id=data_source_id, target_tag=target_tag, value=value, status="dry_run", reason="writeback disabled or dry_run binding", dry_run=True))
        return results

    try:
        write_results = build_connector(data_source, store).write_tags(writable_values)
    except Exception as exc:
        write_results = {target_tag: {"status": "failed", "value": value, "reason": str(exc)} for target_tag, value in writable_values.items()}

    for target_tag, write_result in write_results.items():
        results.append(_record_writeback_result(store=store, run_id=run_id, output_name=output_name, data_source_id=data_source_id, target_tag=target_tag, value=write_result.get("value"), status=str(write_result.get("status", "failed")), reason=str(write_result.get("reason", "")), dry_run=False))
    return results


def _normalize_source_mappings(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    mappings: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        tag = str(item.get("tag", "")).strip()
        key = str(item.get("key", "")).strip()
        if not tag or not key:
            continue
        mappings.append({"tag": tag, "key": key})
    return mappings


def _normalize_tags(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    tags: list[str] = []
    seen: set[str] = set()
    for item in value:
        tag = str(item).strip()
        if not tag or tag in seen:
            continue
        tags.append(tag)
        seen.add(tag)
    return tags


def _unique_tags(tags: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        normalized = str(tag).strip()
        if not normalized or normalized in seen:
            continue
        unique.append(normalized)
        seen.add(normalized)
    return unique


def _record_writeback_result(*, store: MetadataStore, run_id: str, output_name: str, data_source_id: int, target_tag: str, value: Any, status: str, reason: str, dry_run: bool) -> dict[str, Any]:
    store.record_writeback(run_id=run_id, output_name=output_name, data_source_id=data_source_id, target_tag=target_tag, value=value, status=status, reason=reason, dry_run=dry_run)
    return {"output_name": output_name, "data_source_id": data_source_id, "target_tag": target_tag, "value": value, "status": status, "reason": reason, "dry_run": dry_run}


def _mark_instance_running(store: MetadataStore, *, instance_id: int, running_at: datetime) -> None:
    with store.session_factory() as session:
        row = session.get(PluginInstanceModel, instance_id)
        if row is None:
            return
        row.status = "running"
        row.updated_at = running_at
        session.commit()


def _finalize_instance_after_execution(store: MetadataStore, *, instance_id: int, finished_at: datetime) -> None:
    with store.session_factory() as session:
        row = session.get(PluginInstanceModel, instance_id)
        if row is None:
            return
        if row.schedule_enabled:
            row.status = "scheduled"
        else:
            row.status = "configured"
            row.next_scheduled_run_at = None
        row.updated_at = finished_at
        session.commit()


def _db_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
