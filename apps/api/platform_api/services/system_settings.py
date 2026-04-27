from __future__ import annotations

import json
import os
import tempfile
import threading
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from platform_api.core.config import settings


class SystemSettingsError(ValueError):
    """Raised when runtime system settings are invalid."""


@dataclass(frozen=True)
class SettingSpec:
    path: tuple[str, ...]
    label: str
    description: str
    value_type: str
    editable: bool
    minimum: int | float | None = None
    maximum: int | float | None = None


DEFAULT_RUNTIME_SETTINGS: dict[str, Any] = {
    "maintenance": {
        "run_directory_cleanup": {
            "enabled": True,
            "interval_sec": 3600,
            "initial_delay_sec": 10,
            "max_age_sec": 3600,
            "stale_incomplete_age_sec": 24 * 3600,
            "min_keep_runs": 20,
            "max_run_dirs": 500,
            "dry_run": False,
        },
        "database_cleanup": {
            "enabled": True,
            "interval_sec": 3600,
            "initial_delay_sec": 20,
            "retention_days": 7,
            "min_keep_runs": 50,
            "include_audit_events": True,
            "dry_run": False,
        },
    },
    "runner": {
        "default_timeout_sec": settings.runner.default_timeout_sec,
        "max_timeout_sec": settings.runner.max_timeout_sec,
        "max_stdout_bytes": settings.runner.max_stdout_bytes,
        "max_stderr_bytes": settings.runner.max_stderr_bytes,
        "max_output_json_bytes": settings.runner.max_output_json_bytes,
        "max_workdir_total_bytes": settings.runner.max_workdir_total_bytes,
        "allow_network_default": settings.runner.allow_network_default,
        "allow_subprocess_default": settings.runner.allow_subprocess_default,
    },
    "scheduler": {
        "enabled": settings.scheduler.enabled,
        "mode": settings.scheduler.mode,
        "poll_interval_sec": settings.scheduler.poll_interval_sec,
        "max_workers": settings.scheduler.max_workers,
        "lock_ttl_sec": settings.scheduler.lock_ttl_sec,
    },
    "storage": {
        "package_storage_dir": str(settings.package_storage_dir),
        "run_storage_dir": str(settings.run_storage_dir),
        "metadata_database": str(settings.metadata_database),
    },
    "security": {
        "enabled": settings.security.enabled,
        "session_ttl_sec": settings.security.session_ttl_sec,
        "max_request_body_bytes": settings.security.max_request_body_bytes,
    },
}

_SETTING_SPECS: list[SettingSpec] = [
    SettingSpec(("maintenance", "run_directory_cleanup", "enabled"), "启用 runs 目录清理", "定期删除 var/runs/run-* 历史运行目录。", "bool", True),
    SettingSpec(("maintenance", "run_directory_cleanup", "interval_sec"), "runs 清理间隔秒", "后台线程两次 runs 目录清理之间的间隔。", "int", True, 60, 7 * 24 * 3600),
    SettingSpec(("maintenance", "run_directory_cleanup", "initial_delay_sec"), "runs 启动延迟秒", "API 启动后首次执行 runs 目录清理前的延迟。", "int", True, 0, 3600),
    SettingSpec(("maintenance", "run_directory_cleanup", "max_age_sec"), "runs 目录保留秒", "已完成运行目录超过该时间后可被清理，默认 1 小时。", "int", True, 60, 365 * 24 * 3600),
    SettingSpec(("maintenance", "run_directory_cleanup", "stale_incomplete_age_sec"), "未完成目录保留秒", "没有 result.json 的运行目录超过该时间后才可被清理。", "int", True, 3600, 365 * 24 * 3600),
    SettingSpec(("maintenance", "run_directory_cleanup", "min_keep_runs"), "runs 最小保留数量", "始终保留最新 N 个 run-* 目录。", "int", True, 0, 100000),
    SettingSpec(("maintenance", "run_directory_cleanup", "max_run_dirs"), "runs 最大目录数量", "超过该数量时清理最旧目录，仍受最小保留数量保护。", "int", True, 10, 1000000),
    SettingSpec(("maintenance", "run_directory_cleanup", "dry_run"), "runs 清理演练", "只记录将被清理的目录，不实际删除。", "bool", True),
    SettingSpec(("maintenance", "database_cleanup", "enabled"), "启用数据库历史清理", "定期清理运行记录、运行日志、回写记录和可选审计记录。", "bool", True),
    SettingSpec(("maintenance", "database_cleanup", "interval_sec"), "数据库清理间隔秒", "后台线程两次数据库历史记录清理之间的间隔。", "int", True, 60, 7 * 24 * 3600),
    SettingSpec(("maintenance", "database_cleanup", "initial_delay_sec"), "数据库启动延迟秒", "API 启动后首次执行数据库清理前的延迟。", "int", True, 0, 3600),
    SettingSpec(("maintenance", "database_cleanup", "retention_days"), "数据库保留天数", "仅保留最近 N 天运行记录，默认 7 天。", "int", True, 1, 3650),
    SettingSpec(("maintenance", "database_cleanup", "min_keep_runs"), "数据库最小运行记录数", "始终保留最新 N 条运行记录，避免测试环境被清空。", "int", True, 0, 100000),
    SettingSpec(("maintenance", "database_cleanup", "include_audit_events"), "清理审计记录", "是否同时清理超过保留期的 audit_events。", "bool", True),
    SettingSpec(("maintenance", "database_cleanup", "dry_run"), "数据库清理演练", "只统计将被删除的记录，不实际删除。", "bool", True),
    SettingSpec(("runner", "default_timeout_sec"), "Runner 默认超时", "来自静态配置；当前页面只展示，不做热修改。", "int", False),
    SettingSpec(("runner", "max_stdout_bytes"), "stdout 截断字节数", "来自静态配置；当前页面只展示，不做热修改。", "int", False),
    SettingSpec(("scheduler", "mode"), "调度器模式", "来自静态配置；变更需要重启服务。", "str", False),
    SettingSpec(("storage", "run_storage_dir"), "运行目录", "来自静态配置；不允许前端修改。", "str", False),
    SettingSpec(("storage", "metadata_database"), "元数据库", "来自静态配置；不允许前端修改。", "str", False),
    SettingSpec(("security", "enabled"), "安全模式", "来自静态配置；不允许前端修改。", "bool", False),
]

_EDITABLE_PATHS = {spec.path: spec for spec in _SETTING_SPECS if spec.editable}
_LOCK = threading.RLock()


def system_settings_path() -> Path:
    return (settings.project_root / "var/system-settings.json").resolve()


class SystemSettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or system_settings_path()

    def get(self) -> dict[str, Any]:
        with _LOCK:
            payload = _deep_merge(deepcopy(DEFAULT_RUNTIME_SETTINGS), self._read_raw())
            return _normalize_settings(payload)

    def update(self, patch: dict[str, Any], *, actor: str = "local-dev") -> dict[str, Any]:
        if not isinstance(patch, dict):
            raise SystemSettingsError("settings payload must be an object")
        with _LOCK:
            current = self.get()
            editable_patch = _filter_editable_patch(patch)
            merged = _deep_merge(current, editable_patch)
            normalized = _normalize_settings(merged)
            self._write_atomic(normalized)
            return normalized

    def catalog(self) -> dict[str, Any]:
        values = self.get()
        return {
            "settings_file": str(self.path),
            "items": [
                {
                    "path": ".".join(spec.path),
                    "label": spec.label,
                    "description": spec.description,
                    "type": spec.value_type,
                    "editable": spec.editable,
                    "minimum": spec.minimum,
                    "maximum": spec.maximum,
                    "value": _get_nested(values, spec.path),
                }
                for spec in _SETTING_SPECS
            ],
        }

    def _read_raw(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            parsed = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemSettingsError(f"system settings file is invalid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise SystemSettingsError("system settings file must contain an object")
        return parsed

    def _write_atomic(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(prefix="system-settings-", suffix=".json", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)


def get_runtime_settings() -> dict[str, Any]:
    return SystemSettingsStore().get()


def get_run_directory_cleanup_settings() -> dict[str, Any]:
    return get_runtime_settings().get("maintenance", {}).get("run_directory_cleanup", {})


def get_database_cleanup_settings() -> dict[str, Any]:
    return get_runtime_settings().get("maintenance", {}).get("database_cleanup", {})


def _filter_editable_patch(patch: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for path, spec in _EDITABLE_PATHS.items():
        found, value = _try_get_nested(patch, path)
        if not found:
            continue
        _set_nested(result, path, _coerce_value(value, spec))
    return result


def _normalize_settings(payload: dict[str, Any]) -> dict[str, Any]:
    result = _deep_merge(deepcopy(DEFAULT_RUNTIME_SETTINGS), payload)
    for path, spec in _EDITABLE_PATHS.items():
        found, value = _try_get_nested(result, path)
        if found:
            _set_nested(result, path, _coerce_value(value, spec))
    return result


def _coerce_value(value: Any, spec: SettingSpec) -> Any:
    if spec.value_type == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "true", "yes", "on"}:
                return True
            if lowered in {"0", "false", "no", "off"}:
                return False
        raise SystemSettingsError(f"{'.'.join(spec.path)} must be boolean")
    if spec.value_type == "int":
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise SystemSettingsError(f"{'.'.join(spec.path)} must be integer") from exc
        if spec.minimum is not None and parsed < int(spec.minimum):
            raise SystemSettingsError(f"{'.'.join(spec.path)} must be >= {spec.minimum}")
        if spec.maximum is not None and parsed > int(spec.maximum):
            raise SystemSettingsError(f"{'.'.join(spec.path)} must be <= {spec.maximum}")
        return parsed
    if spec.value_type == "float":
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise SystemSettingsError(f"{'.'.join(spec.path)} must be number") from exc
        if spec.minimum is not None and parsed < float(spec.minimum):
            raise SystemSettingsError(f"{'.'.join(spec.path)} must be >= {spec.minimum}")
        if spec.maximum is not None and parsed > float(spec.maximum):
            raise SystemSettingsError(f"{'.'.join(spec.path)} must be <= {spec.maximum}")
        return parsed
    if spec.value_type == "str":
        return str(value)
    return value


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _try_get_nested(payload: dict[str, Any], path: tuple[str, ...]) -> tuple[bool, Any]:
    cursor: Any = payload
    for key in path:
        if not isinstance(cursor, dict) or key not in cursor:
            return False, None
        cursor = cursor[key]
    return True, cursor


def _get_nested(payload: dict[str, Any], path: tuple[str, ...]) -> Any:
    found, value = _try_get_nested(payload, path)
    return value if found else None


def _set_nested(payload: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    cursor = payload
    for key in path[:-1]:
        next_value = cursor.get(key)
        if not isinstance(next_value, dict):
            next_value = {}
            cursor[key] = next_value
        cursor = next_value
    cursor[path[-1]] = value
