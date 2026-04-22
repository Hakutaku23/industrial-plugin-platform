from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from platform_api.core.config import settings
from platform_api.services.runtime_errors import (
    RustRunnerBinaryNotFound,
    RustRunnerBridgeError,
)
from platform_api.services.runtime_protocol import (
    ExecuteTaskRequestModel,
    ExecuteTaskResultModel,
    RustRunnerResult,
)


class RustRunnerBridge:
    def __init__(self, binary_path: str | Path | None = None) -> None:
        self.binary_path = self._resolve_binary(binary_path)

    def execute_function(
        self,
        *,
        package_dir: Path,
        entry_file: str,
        callable_name: str,
        payload: dict[str, Any],
        timeout_sec: int,
        memory_mb: int | None,
        cpu_limit: float | None,
        working_dir: str,
        runtime_env: dict[str, str],
        capabilities: dict[str, Any],
        task_id: str,
        run_id: str,
        trigger_type: str,
    ) -> RustRunnerResult:
        task_work_dir = settings.run_storage_dir / run_id
        request = ExecuteTaskRequestModel(
            schema_version='runner-task/v1',
            task_id=task_id,
            run_id=run_id,
            trigger_type=trigger_type,
            environment=settings.environment,
            plugin={
                'package_name': package_dir.name,
                'version': 'unknown',
                'package_dir': str(package_dir),
                'entry_mode': 'function',
                'entry_file': entry_file,
                'callable': callable_name,
            },
            runtime={
                'timeout_sec': timeout_sec,
                'memory_mb': memory_mb,
                'cpu_limit': cpu_limit,
                'working_dir': working_dir or '.',
                'env': runtime_env,
                'filesystem_mode': capabilities.get('filesystem', 'scoped'),
                'network_enabled': bool(capabilities.get('network', False)),
                'subprocess_enabled': bool(capabilities.get('subprocess', False)),
            },
            sandbox={
                'work_root': str(settings.run_storage_dir),
                'task_work_dir': str(task_work_dir),
                'result_file': 'result.json',
                'input_file': 'input.json',
                'cleanup_enabled': bool(settings.runner.cleanup_enabled),
                'cleanup_max_age_sec': int(settings.runner.cleanup_max_age_sec),
                'cleanup_max_run_dirs': int(settings.runner.cleanup_max_run_dirs),
                'cleanup_min_keep_runs': int(settings.runner.cleanup_min_keep_runs),
                'cleanup_stale_incomplete_age_sec': int(settings.runner.cleanup_stale_incomplete_age_sec),
                'cleanup_sweep_interval_sec': int(settings.runner.cleanup_sweep_interval_sec),
                'cleanup_state_file': '.runner-cleanup-state',
            },
            payload=payload,
        )
        completed = subprocess.run(
            [str(self.binary_path), 'execute-task'],
            input=json.dumps(request.__dict__, ensure_ascii=False),
            text=True,
            capture_output=True,
            timeout=max(5, int(timeout_sec) + 5),
            check=False,
            cwd=str(settings.project_root),
        )
        raw_stdout = completed.stdout.strip()
        if not raw_stdout:
            raise RustRunnerBridgeError(
                f'Rust runner returned empty stdout: {completed.stderr[-1000:]}'
            )
        try:
            parsed = json.loads(raw_stdout)
        except json.JSONDecodeError as exc:
            raise RustRunnerBridgeError(
                f'Rust runner stdout is not valid JSON: {raw_stdout[-1000:]}'
            ) from exc
        result = ExecuteTaskResultModel(
            raw=parsed,
            status=str(parsed.get('status', 'infra_error')),
            exit_code=int(parsed.get('exit_code', completed.returncode)),
            plugin_result=parsed.get('plugin_result') or {},
            error=parsed.get('error') or {},
            stderr=str(parsed.get('stderr', '')),
            timing=dict(parsed.get('timing') or {}),
            resource_usage=dict(parsed.get('resource_usage') or {}),
        )
        plugin_result = result.plugin_result or {}
        return RustRunnerResult(
            status=str(plugin_result.get('status', result.status)),
            outputs=dict(plugin_result.get('outputs') or {}),
            logs=[str(item) for item in plugin_result.get('logs') or []],
            metrics=dict(plugin_result.get('metrics') or {}),
            stderr=result.stderr,
            returncode=result.exit_code,
            error_code=str(result.error.get('code', '')),
            error_message=str(result.error.get('message', '')),
            backend='rust_runner',
            task_work_dir=str(task_work_dir),
            timing=result.timing,
            resource_usage=result.resource_usage,
            raw_status=result.status,
        )

    def _resolve_binary(self, binary_path: str | Path | None) -> Path:
        configured = binary_path or settings.runner.binary_path
        if configured:
            candidate = Path(configured)
            if not candidate.is_absolute():
                candidate = (settings.project_root / candidate).resolve()
        else:
            candidate = (settings.project_root / 'target/release/ipp_runner_core').resolve()
        if not candidate.exists():
            raise RustRunnerBinaryNotFound(
                f'Rust runner binary not found: {candidate}'
            )
        return candidate
