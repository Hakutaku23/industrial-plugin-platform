from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from platform_api.core.config import settings
from platform_api.services.runtime_errors import RustRunnerBinaryNotFound, RustRunnerBridgeError
from platform_api.services.runtime_protocol import ExecuteTaskRequestModel, ExecuteTaskResultModel, RustRunnerResult


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
        entry_type: str | None = None,
        entry_module: str | None = None,
    ) -> RustRunnerResult:
        task_work_dir = settings.run_storage_dir / run_id
        resolved_entry_type = _resolve_entry_type(entry_file=entry_file, entry_type=entry_type)
        resolved_entry_module = entry_module or (entry_file if resolved_entry_type == "module" else None)
        request = ExecuteTaskRequestModel(
            schema_version='runner-task/v2',
            task_id=task_id,
            run_id=run_id,
            trigger_type=trigger_type,
            environment=settings.environment,
            plugin={
                'package_name': package_dir.name,
                'version': 'unknown',
                'package_dir': str(package_dir),
                'entry_mode': 'function',
                'entry_type': resolved_entry_type,
                'entry_file': entry_file if resolved_entry_type == 'file' else None,
                'entry_module': resolved_entry_module if resolved_entry_type == 'module' else None,
                'callable': callable_name,
            },
            runtime={
                'timeout_sec': int(timeout_sec),
                'memory_mb': memory_mb,
                'cpu_limit': cpu_limit,
                'working_dir': working_dir or '.',
                'env': _stable_numeric_runtime_env(runtime_env),
                'filesystem_mode': capabilities.get('filesystem', 'scoped'),
                'network_enabled': bool(capabilities.get('network', settings.runner.allow_network_default)),
                'subprocess_enabled': bool(capabilities.get('subprocess', settings.runner.allow_subprocess_default)),
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
                'max_stdout_bytes': int(settings.runner.max_stdout_bytes),
                'max_stderr_bytes': int(settings.runner.max_stderr_bytes),
                'max_output_json_bytes': int(settings.runner.max_output_json_bytes),
                'max_workdir_total_bytes': int(settings.runner.max_workdir_total_bytes),
            },
            payload=payload,
        )

        try:
            completed = subprocess.run(
                [str(self.binary_path), 'execute-task'],
                input=json.dumps(request.__dict__, ensure_ascii=False),
                text=True,
                capture_output=True,
                timeout=max(5, int(timeout_sec) + 5),
                check=False,
                cwd=str(settings.project_root),
                env=self._runner_env(),
            )
        except subprocess.TimeoutExpired as exc:
            raise RustRunnerBridgeError(f'Rust runner process timed out: {exc}') from exc

        raw_stdout = completed.stdout.strip()
        if not raw_stdout:
            raise RustRunnerBridgeError(f'Rust runner returned empty stdout: {completed.stderr[-1000:]}')
        try:
            parsed = json.loads(raw_stdout)
        except json.JSONDecodeError as exc:
            raise RustRunnerBridgeError(f'Rust runner stdout is not valid JSON: {raw_stdout[-1000:]}') from exc

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

    def _runner_env(self) -> dict[str, str]:
        env = os.environ.copy()
        if settings.runner.python_executable:
            env['IPP_PLUGIN_PYTHON'] = str(settings.runner.python_executable)

        runner_root = (settings.project_root / 'apps/runner').resolve()
        api_root = (settings.project_root / 'apps/api').resolve()
        pythonpath_parts = [str(runner_root), str(api_root)]
        existing_pythonpath = env.get('PYTHONPATH')
        if existing_pythonpath:
            pythonpath_parts.append(existing_pythonpath)
        env['PYTHONPATH'] = os.pathsep.join(pythonpath_parts)

        configured_host = os.getenv('PLATFORM_RUNNER_FUNCTION_HOST_PATH', '').strip()
        function_host_path = Path(configured_host).resolve() if configured_host else runner_root / 'platform_runner' / 'function_host.py'
        if function_host_path.exists():
            env['IPP_FUNCTION_HOST_PATH'] = str(function_host_path)
        return env

    def _resolve_binary(self, binary_path: str | Path | None) -> Path:
        configured = binary_path or settings.runner.binary_path
        if configured:
            candidate = Path(configured)
            if not candidate.is_absolute():
                candidate = (settings.project_root / candidate).resolve()
        else:
            candidate = (settings.project_root / 'target/release/ipp_runner_core').resolve()
        if not candidate.exists():
            raise RustRunnerBinaryNotFound(f'Rust runner binary not found: {candidate}')
        return candidate


def _resolve_entry_type(*, entry_file: str, entry_type: str | None) -> str:
    normalized = str(entry_type or '').strip().lower()
    if normalized in {'file', 'module'}:
        return normalized
    entry_text = str(entry_file or '').strip()
    if entry_text and not entry_text.endswith('.py') and '/' not in entry_text and '\\' not in entry_text:
        return 'module'
    return 'file'


def _stable_numeric_runtime_env(runtime_env: dict[str, str] | None) -> dict[str, str]:
    """Merge manifest env with safe single-thread defaults for BLAS/OpenMP libraries."""
    stable_defaults = {
        'OPENBLAS_NUM_THREADS': '1',
        'OMP_NUM_THREADS': '1',
        'MKL_NUM_THREADS': '1',
        'NUMEXPR_NUM_THREADS': '1',
        'VECLIB_MAXIMUM_THREADS': '1',
        'BLIS_NUM_THREADS': '1',
        'JOBLIB_MULTIPROCESSING': '0',
        'SKLEARN_ALLOW_INVALID_OPENMP': '1',
    }
    merged: dict[str, str] = dict(stable_defaults)
    for key, value in dict(runtime_env or {}).items():
        key_text = str(key).strip()
        if not key_text:
            continue
        merged[key_text] = str(value)
    return merged
