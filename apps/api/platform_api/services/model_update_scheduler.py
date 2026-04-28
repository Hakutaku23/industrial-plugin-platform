from __future__ import annotations

import os
import threading
import time
from datetime import UTC, datetime
from typing import Any

from platform_api.services.model_update_jobs import ModelUpdateJobStore


class ModelUpdateSchedulerService:
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._started_at: datetime | None = None
        self._last_scan_at: datetime | None = None
        self._last_result: dict[str, Any] | None = None

    def start(self) -> None:
        if not _env_bool("PLATFORM_MODEL_UPDATE_SCHEDULER_ENABLED", True):
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._started_at = datetime.now(UTC)
        self._thread = threading.Thread(target=self._loop, name="model-update-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def status(self) -> dict[str, Any]:
        return {
            "enabled": _env_bool("PLATFORM_MODEL_UPDATE_SCHEDULER_ENABLED", True),
            "running": bool(self._thread and self._thread.is_alive()),
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "last_scan_at": self._last_scan_at.isoformat() if self._last_scan_at else None,
            "last_result": self._last_result,
            "interval_sec": _env_int("PLATFORM_MODEL_UPDATE_SCHEDULER_INTERVAL_SEC", 30),
            "max_due_batch": _env_int("PLATFORM_MODEL_UPDATE_SCHEDULER_MAX_DUE_BATCH", 5),
        }

    def _loop(self) -> None:
        initial_delay = _env_int("PLATFORM_MODEL_UPDATE_SCHEDULER_INITIAL_DELAY_SEC", 10)
        if initial_delay > 0:
            self._stop.wait(initial_delay)
        while not self._stop.is_set():
            self._scan_once()
            self._stop.wait(_env_int("PLATFORM_MODEL_UPDATE_SCHEDULER_INTERVAL_SEC", 30))

    def _scan_once(self) -> None:
        self._last_scan_at = datetime.now(UTC)
        try:
            self._last_result = ModelUpdateJobStore().run_due_jobs(
                limit=_env_int("PLATFORM_MODEL_UPDATE_SCHEDULER_MAX_DUE_BATCH", 5),
                actor="model-update-scheduler",
            )
        except Exception as exc:  # noqa: BLE001
            self._last_result = {"status": "failed", "error": str(exc)}


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError:
        return default


model_update_scheduler_service = ModelUpdateSchedulerService()
