from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RustRunnerResult:
    status: str
    outputs: dict[str, Any]
    logs: list[str]
    metrics: dict[str, Any]
    stderr: str
    returncode: int
    error_code: str = ''
    error_message: str = ''
    backend: str = 'rust_runner'
    task_work_dir: str | None = None
    timing: dict[str, Any] = field(default_factory=dict)
    resource_usage: dict[str, Any] = field(default_factory=dict)
    raw_status: str = ''


@dataclass(frozen=True)
class ExecuteTaskRequestModel:
    schema_version: str
    task_id: str
    run_id: str
    trigger_type: str
    environment: str
    plugin: dict[str, Any]
    runtime: dict[str, Any]
    sandbox: dict[str, Any]
    payload: dict[str, Any]


@dataclass(frozen=True)
class ExecuteTaskResultModel:
    raw: dict[str, Any]
    status: str
    exit_code: int
    plugin_result: dict[str, Any] = field(default_factory=dict)
    error: dict[str, Any] = field(default_factory=dict)
    stderr: str = ''
    timing: dict[str, Any] = field(default_factory=dict)
    resource_usage: dict[str, Any] = field(default_factory=dict)
