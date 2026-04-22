from __future__ import annotations

import json
import subprocess
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from platform_api.core.config import settings
from platform_api.services.execution_lock import RedisExecutionLockManager
from platform_api.services.scheduler_dispatch import recover_instances_without_lock
from platform_api.services.scheduler_runtime_state import snapshot as scheduler_runtime_snapshot


class InstanceScheduler:
    def __init__(self) -> None:
        self.lock_manager = RedisExecutionLockManager.from_settings()
        self._process: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()
        self._started_at: datetime | None = None
        self._last_error: str | None = None
        self._worker_id = f'scheduler-{uuid.uuid4().hex[:12]}'

    def start(self) -> None:
        if not settings.scheduler.enabled:
            return
        with self._lock:
            if self._process and self._process.poll() is None:
                return
            recover_instances_without_lock(force=True)
            binary = self._resolve_binary()
            config = {
                'base_url': settings.scheduler.internal_base_url.rstrip('/'),
                'internal_token': settings.scheduler.internal_token,
                'tick_interval_ms': settings.scheduler.daemon_tick_interval_ms,
                'idle_min_interval_ms': settings.scheduler.daemon_idle_min_interval_ms,
                'idle_max_interval_ms': settings.scheduler.daemon_idle_max_interval_ms,
                'error_backoff_ms': settings.scheduler.daemon_error_backoff_ms,
                'max_due_batch': settings.scheduler.daemon_max_due_batch,
                'max_parallel_dispatch': settings.scheduler.daemon_max_parallel_dispatch,
                'request_timeout_sec': int(settings.scheduler.internal_request_timeout_sec),
                'worker_id': self._worker_id,
            }
            self._process = subprocess.Popen(
                [str(binary), 'daemon', '--config-json', json.dumps(config, ensure_ascii=False)],
                cwd=str(settings.project_root),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            self._started_at = datetime.now(UTC)
            self._last_error = None

    def stop(self) -> None:
        with self._lock:
            process = self._process
            self._process = None
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    def tick(self) -> None:
        recover_instances_without_lock(force=False)

    def status_snapshot(self) -> dict[str, Any]:
        process = self._process
        alive = bool(process and process.poll() is None)
        payload = {
            'mode': 'rust-daemon',
            'thread_alive': alive,
            'daemon_pid': process.pid if alive and process else None,
            'worker_id': self._worker_id,
            'started_at': self._started_at.isoformat() if self._started_at else None,
            'last_error': self._last_error,
            'daemon_tick_interval_ms': settings.scheduler.daemon_tick_interval_ms,
            'daemon_idle_min_interval_ms': settings.scheduler.daemon_idle_min_interval_ms,
            'daemon_idle_max_interval_ms': settings.scheduler.daemon_idle_max_interval_ms,
            'daemon_error_backoff_ms': settings.scheduler.daemon_error_backoff_ms,
            'recovery_interval_sec': settings.scheduler.recovery_interval_sec,
        }
        payload.update(scheduler_runtime_snapshot())
        return payload

    def lock_snapshot(self, *, limit: int = 200) -> list[dict[str, Any]]:
        return self.lock_manager.list_active_locks(limit=limit)

    def _resolve_binary(self) -> Path:
        configured = settings.scheduler.daemon_binary_path
        if configured:
            candidate = Path(configured)
            if not candidate.is_absolute():
                candidate = (settings.project_root / candidate).resolve()
        else:
            candidate = (settings.project_root / 'target/release/ipp_scheduler_core').resolve()
        if not candidate.exists():
            raise FileNotFoundError(f'Rust scheduler binary not found: {candidate}')
        return candidate


scheduler = InstanceScheduler()
