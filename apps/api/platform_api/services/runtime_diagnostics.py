from __future__ import annotations

from pathlib import Path
from typing import Any

from platform_api.core.config import settings
from platform_api.services.metadata_store import MetadataStore
from platform_api.services.model_registry import ModelRegistry, ModelRegistryError


class RuntimeDiagnosticsError(ValueError):
    """Raised when runtime diagnostics cannot be produced."""


class RuntimeDiagnostics:
    """Read-only diagnostics for model binding and plugin run runtime state.

    This service intentionally does not mutate plugin instances, model records, or run records.
    It is used by the second-version observability page and API endpoints.
    """

    def __init__(self, store: MetadataStore | None = None, registry: ModelRegistry | None = None) -> None:
        self.store = store or MetadataStore(settings.metadata_database)
        self.registry = registry or ModelRegistry()

    def list_model_binding_health(self) -> dict[str, Any]:
        instances = self.store.list_plugin_instances()
        items = [self.instance_model_binding_health(int(item["id"])) for item in instances]
        summary: dict[str, int] = {}
        severity_summary: dict[str, int] = {}
        for item in items:
            summary[item["status"]] = summary.get(item["status"], 0) + 1
            severity_summary[item["severity"]] = severity_summary.get(item["severity"], 0) + 1
        return {
            "items": items,
            "summary": summary,
            "severity_summary": severity_summary,
            "total": len(items),
        }

    def instance_model_binding_health(self, instance_id: int) -> dict[str, Any]:
        instance = self.store.get_plugin_instance(int(instance_id))
        if instance is None:
            raise RuntimeDiagnosticsError(f"plugin instance not found: {instance_id}")

        version_record = self.store.get_plugin_version(
            str(instance.get("package_name", "")),
            str(instance.get("version", "")),
        )
        manifest = version_record.get("manifest") if version_record else None
        dependency = _extract_model_dependency(manifest if isinstance(manifest, dict) else {})
        required_family = _string_first(
            dependency,
            "familyFingerprint",
            "family_fingerprint",
            "modelFamilyFingerprint",
            "model_family_fingerprint",
        )
        dependency_required = bool(dependency and dependency.get("required", bool(required_family)))
        required_artifacts = _string_list(
            dependency.get("requiredArtifacts") if dependency else None,
            dependency.get("required_artifacts") if dependency else None,
        )

        base = {
            "instance_id": int(instance_id),
            "instance_name": instance.get("name"),
            "package_name": instance.get("package_name"),
            "plugin_version": instance.get("version"),
            "plugin_model_required": dependency_required,
            "plugin_family_fingerprint": required_family,
            "required_artifacts": required_artifacts,
        }

        if not dependency_required and not required_family:
            return {
                **base,
                "status": "NO_MODEL_REQUIREMENT",
                "severity": "info",
                "message": "插件 manifest 未声明模型依赖；该实例不需要模型绑定。",
                "binding": None,
                "model": None,
                "version": None,
                "artifact_check": _artifact_check(required_artifacts, {}, None),
            }

        try:
            binding = self.registry.get_instance_binding(instance_id=int(instance_id))
        except Exception as exc:  # noqa: BLE001
            return {
                **base,
                "status": "BINDING_LOOKUP_FAILED",
                "severity": "error",
                "message": str(exc),
                "binding": None,
                "model": None,
                "version": None,
                "artifact_check": _artifact_check(required_artifacts, {}, None),
            }

        if binding is None:
            return {
                **base,
                "status": "REQUIRED_UNBOUND",
                "severity": "error",
                "message": "插件声明需要模型，但实例尚未绑定兼容模型。",
                "binding": None,
                "model": None,
                "version": None,
                "artifact_check": _artifact_check(required_artifacts, {}, None),
            }

        model = self.registry.get_model(int(binding["model_id"]))
        if model is None:
            return {
                **base,
                "status": "MODEL_NOT_FOUND",
                "severity": "error",
                "message": "绑定记录指向的模型不存在。",
                "binding": binding,
                "model": None,
                "version": None,
                "artifact_check": _artifact_check(required_artifacts, {}, None),
            }

        if required_family and model.get("family_fingerprint") != required_family:
            return {
                **base,
                "status": "FINGERPRINT_MISMATCH",
                "severity": "error",
                "message": "插件声明的 family_fingerprint 与模型 family_fingerprint 不一致。",
                "binding": binding,
                "model": model,
                "version": None,
                "artifact_check": _artifact_check(required_artifacts, {}, None),
            }

        version = self._resolve_bound_model_version(binding=binding, model=model)
        if version is None:
            missing_status = "ACTIVE_VERSION_MISSING" if binding.get("binding_mode") == "current" else "FIXED_VERSION_MISSING"
            return {
                **base,
                "status": missing_status,
                "severity": "error",
                "message": "当前绑定无法解析到有效模型版本。",
                "binding": binding,
                "model": model,
                "version": None,
                "artifact_check": _artifact_check(required_artifacts, {}, None),
            }

        if required_family and version.get("family_fingerprint") != required_family:
            return {
                **base,
                "status": "VERSION_FINGERPRINT_MISMATCH",
                "severity": "error",
                "message": "插件声明的 family_fingerprint 与绑定模型版本不一致。",
                "binding": binding,
                "model": model,
                "version": _version_summary(version),
                "artifact_check": _artifact_check(required_artifacts, version.get("artifacts") or {}, version.get("artifact_dir")),
            }

        artifact_check = _artifact_check(required_artifacts, version.get("artifacts") or {}, version.get("artifact_dir"))
        if artifact_check["missing_required_keys"]:
            return {
                **base,
                "status": "REQUIRED_ARTIFACT_MISSING",
                "severity": "error",
                "message": "模型版本缺少插件声明的 requiredArtifacts。",
                "binding": binding,
                "model": model,
                "version": _version_summary(version),
                "artifact_check": artifact_check,
            }
        if artifact_check["missing_files"]:
            return {
                **base,
                "status": "ARTIFACT_FILE_MISSING",
                "severity": "error",
                "message": "模型版本 artifacts 声明文件在磁盘上不存在。",
                "binding": binding,
                "model": model,
                "version": _version_summary(version),
                "artifact_check": artifact_check,
            }

        if version.get("status") not in {"ACTIVE", "VALIDATED"}:
            return {
                **base,
                "status": "VERSION_NOT_ACTIVE_OR_VALIDATED",
                "severity": "warning",
                "message": "模型版本存在，但状态不是 ACTIVE 或 VALIDATED。",
                "binding": binding,
                "model": model,
                "version": _version_summary(version),
                "artifact_check": artifact_check,
            }

        return {
            **base,
            "status": "OK",
            "severity": "ok",
            "message": "模型绑定与插件声明兼容，所需 artifacts 可用。",
            "binding": binding,
            "model": model,
            "version": _version_summary(version),
            "artifact_check": artifact_check,
        }

    def run_diagnostics(self, run_id: str) -> dict[str, Any]:
        runs = self.store.list_plugin_runs()
        run = next((item for item in runs if item.get("run_id") == run_id), None)
        if run is None:
            raise RuntimeDiagnosticsError(f"plugin run not found: {run_id}")

        logs = self.store.list_run_logs(run_id)
        writebacks = self.store.list_writeback_records(run_id)
        model_metrics = _extract_model_metrics(run.get("metrics") or {})
        binding_health = None
        if run.get("instance_id") is not None:
            try:
                binding_health = self.instance_model_binding_health(int(run["instance_id"]))
            except Exception as exc:  # noqa: BLE001
                binding_health = {
                    "status": "BINDING_DIAGNOSTIC_FAILED",
                    "severity": "warning",
                    "message": str(exc),
                }

        return {
            "run": run,
            "model_metrics": model_metrics,
            "model_binding_health": binding_health,
            "writeback_summary": _writeback_summary(writebacks),
            "writebacks": writebacks,
            "logs": logs,
            "suggestions": _suggestions(run=run, logs=logs, writebacks=writebacks, binding_health=binding_health),
        }

    def _resolve_bound_model_version(self, *, binding: dict[str, Any], model: dict[str, Any]) -> dict[str, Any] | None:
        versions = self.registry.list_versions(int(model["id"])) or []
        if binding.get("binding_mode") == "fixed_version":
            version_id = binding.get("model_version_id")
        else:
            version_id = model.get("active_version_id")
        if version_id is None:
            return None
        return next((item for item in versions if int(item.get("id", -1)) == int(version_id)), None)


def _extract_model_dependency(manifest: dict[str, Any]) -> dict[str, Any] | None:
    candidates: list[Any] = [manifest.get("modelDependency"), manifest.get("model_dependency")]
    spec = manifest.get("spec")
    if isinstance(spec, dict):
        candidates.extend([spec.get("modelDependency"), spec.get("model_dependency")])
    for candidate in candidates:
        if isinstance(candidate, dict):
            return candidate
    return None


def _string_first(record: dict[str, Any] | None, *keys: str) -> str | None:
    if not record:
        return None
    for key in keys:
        value = str(record.get(key) or "").strip()
        if value:
            return value
    return None


def _string_list(*values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, list):
            continue
        for item in value:
            normalized = str(item).strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
    return result


def _artifact_check(required_artifacts: list[str], artifacts: dict[str, Any], artifact_dir: str | None) -> dict[str, Any]:
    artifact_keys = sorted(str(key) for key in artifacts.keys())
    missing_required_keys = [key for key in required_artifacts if key not in artifacts]
    missing_files: list[str] = []
    present_files: list[str] = []
    root = Path(artifact_dir).resolve() if artifact_dir else None
    if root is not None:
        for key, spec in artifacts.items():
            if not isinstance(spec, dict):
                continue
            relative_path = str(spec.get("path") or "").strip()
            if not relative_path:
                continue
            target = (root / relative_path).resolve()
            if root not in target.parents and target != root:
                missing_files.append(f"{key}: path escapes artifact_dir")
                continue
            if target.exists():
                present_files.append(str(key))
            else:
                missing_files.append(f"{key}: {relative_path}")
    return {
        "required_artifacts": required_artifacts,
        "artifact_keys": artifact_keys,
        "missing_required_keys": missing_required_keys,
        "missing_files": missing_files,
        "present_files": present_files,
        "artifact_dir": artifact_dir,
    }


def _version_summary(version: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": version.get("id"),
        "version": version.get("version"),
        "status": version.get("status"),
        "family_fingerprint": version.get("family_fingerprint"),
        "artifact_dir": version.get("artifact_dir"),
        "artifacts": version.get("artifacts") or {},
        "created_at": version.get("created_at"),
        "activated_at": version.get("activated_at"),
    }


def _extract_model_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "model_name",
        "model_version",
        "model_artifact_id",
        "family_fingerprint",
        "model_binding_mode",
        "model_materialization_mode",
        "model_runtime_dir",
    )
    return {key: metrics.get(key) for key in keys if key in metrics}


def _writeback_summary(writebacks: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, int] = {}
    for item in writebacks:
        status = str(item.get("status") or "unknown")
        summary[status] = summary.get(status, 0) + 1
    return {
        "total": len(writebacks),
        "by_status": summary,
        "blocked": summary.get("blocked", 0),
        "failed": summary.get("failed", 0),
        "success": summary.get("success", 0),
        "dry_run": summary.get("dry_run", 0),
    }


def _suggestions(*, run: dict[str, Any], logs: list[dict[str, Any]], writebacks: list[dict[str, Any]], binding_health: dict[str, Any] | None) -> list[dict[str, str]]:
    suggestions: list[dict[str, str]] = []
    error = run.get("error") if isinstance(run.get("error"), dict) else {}
    error_code = str(error.get("code") or "")
    error_message = str(error.get("message") or "")

    if binding_health and binding_health.get("severity") in {"error", "warning"}:
        suggestions.append({
            "level": str(binding_health.get("severity")),
            "code": str(binding_health.get("status")),
            "message": str(binding_health.get("message")),
        })

    if error_code:
        suggestions.append({
            "level": "error",
            "code": error_code,
            "message": error_message or "运行失败，请检查 runner stderr 和插件日志。",
        })

    for item in writebacks:
        reason = str(item.get("reason") or "")
        if reason == "output_missing":
            suggestions.append({
                "level": "warning",
                "code": "WRITEBACK_OUTPUT_MISSING",
                "message": f"回写绑定输出 {item.get('output_name')} 未出现在插件 outputs 中；请检查插件输出名与回写 output_name 是否一致。",
            })
        elif str(item.get("status")) in {"blocked", "failed"}:
            suggestions.append({
                "level": "warning",
                "code": "WRITEBACK_NOT_SUCCESS",
                "message": f"回写 {item.get('output_name')} 状态为 {item.get('status')}: {reason}",
            })

    stderr_logs = [str(item.get("message") or "") for item in logs if str(item.get("source") or "").lower() in {"plugin_stderr", "runner"}]
    if error_code == "E_PROCESS_EXIT_NONZERO" and not stderr_logs:
        suggestions.append({
            "level": "info",
            "code": "CHECK_STDERR_LOG",
            "message": "插件非零退出，但运行日志未包含 stderr；请检查 var/runs/<run_id>/stderr.log。",
        })

    # Preserve order but deduplicate identical code/message pairs.
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in suggestions:
        key = (item["code"], item["message"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped
