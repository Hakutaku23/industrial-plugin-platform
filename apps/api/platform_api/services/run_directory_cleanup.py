from __future__ import annotations

import fcntl
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from platform_api.core.config import settings
from platform_api.services.metadata_store import MetadataStore
from platform_api.services.system_settings import get_run_directory_cleanup_settings


@dataclass(frozen=True)
class RunDirectoryCleanupReport:
    enabled: bool
    dry_run: bool
    scanned: int
    deleted: int
    skipped_recent: int
    skipped_protected: int
    bytes_deleted: int
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "dry_run": self.dry_run,
            "scanned": self.scanned,
            "deleted": self.deleted,
            "skipped_recent": self.skipped_recent,
            "skipped_protected": self.skipped_protected,
            "bytes_deleted": self.bytes_deleted,
            "message": self.message,
        }


class RunDirectoryCleanupService:
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._last_report: dict[str, Any] | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="ipp-run-dir-cleanup", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def last_report(self) -> dict[str, Any] | None:
        return self._last_report

    def run_once(self, *, dry_run: bool | None = None) -> dict[str, Any]:
        report = cleanup_run_directories(dry_run=dry_run).as_dict()
        self._last_report = report
        return report

    def _loop(self) -> None:
        initial_delay = int(get_run_directory_cleanup_settings().get("initial_delay_sec", 10))
        if self._stop.wait(max(0, initial_delay)):
            return
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception as exc:  # noqa: BLE001
                self._last_report = {"enabled": False, "error": str(exc), "message": "run directory cleanup failed"}
            interval = int(get_run_directory_cleanup_settings().get("interval_sec", 3600))
            if self._stop.wait(max(60, interval)):
                return


run_directory_cleanup_service = RunDirectoryCleanupService()


def cleanup_run_directories(*, dry_run: bool | None = None) -> RunDirectoryCleanupReport:
    config = get_run_directory_cleanup_settings()
    enabled = bool(config.get("enabled", True))
    effective_dry_run = bool(config.get("dry_run", False) if dry_run is None else dry_run)
    if not enabled and dry_run is None:
        return RunDirectoryCleanupReport(False, effective_dry_run, 0, 0, 0, 0, 0, "run directory cleanup is disabled")

    run_root = settings.run_storage_dir.resolve()
    run_root.mkdir(parents=True, exist_ok=True)
    lock_path = run_root / ".run-cleanup.lock"
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return RunDirectoryCleanupReport(enabled, effective_dry_run, 0, 0, 0, 0, 0, "another run directory cleanup is active")
        try:
            return _cleanup_locked(run_root=run_root, config=config, dry_run=effective_dry_run)
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _cleanup_locked(*, run_root: Path, config: dict[str, Any], dry_run: bool) -> RunDirectoryCleanupReport:
    now = time.time()
    max_age_sec = int(config.get("max_age_sec", 3600))
    stale_incomplete_age_sec = int(config.get("stale_incomplete_age_sec", 24 * 3600))
    min_keep_runs = int(config.get("min_keep_runs", 20))
    max_run_dirs = int(config.get("max_run_dirs", 500))

    run_dirs = sorted(
        [path for path in run_root.iterdir() if path.is_dir() and path.name.startswith("run-")],
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    protected = {path for path in run_dirs[: max(0, min_keep_runs)]}
    scanned = len(run_dirs)
    deleted = 0
    skipped_recent = 0
    skipped_protected = 0
    bytes_deleted = 0

    for index, path in enumerate(run_dirs):
        if path in protected:
            skipped_protected += 1
            continue
        age_sec = max(0, int(now - path.stat().st_mtime))
        complete = (path / "result.json").exists()
        age_limit = max_age_sec if complete else stale_incomplete_age_sec
        too_many = index >= max_run_dirs
        if age_sec < age_limit and not too_many:
            skipped_recent += 1
            continue
        size = _directory_size(path)
        if not dry_run:
            shutil.rmtree(path, ignore_errors=True)
        deleted += 1
        bytes_deleted += size

    report = RunDirectoryCleanupReport(True, dry_run, scanned, deleted, skipped_recent, skipped_protected, bytes_deleted, "run directory cleanup completed")
    _audit(report)
    return report


def _directory_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file() or item.is_symlink():
                total += item.stat().st_size
        except OSError:
            continue
    return total


def _audit(report: RunDirectoryCleanupReport) -> None:
    try:
        MetadataStore(settings.metadata_database).record_audit_event(
            event_type="maintenance.run_directory_cleanup.completed",
            target_type="run_storage",
            target_id=str(settings.run_storage_dir),
            details=report.as_dict(),
        )
    except Exception:
        pass
