from __future__ import annotations

import fcntl
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select

from platform_api.core.config import settings
from platform_api.services.metadata_store import (
    AuditEventModel,
    MetadataStore,
    PluginRunModel,
    RunLogModel,
    WritebackRecordModel,
)
from platform_api.services.system_settings import get_database_cleanup_settings


@dataclass(frozen=True)
class DatabaseCleanupReport:
    enabled: bool
    dry_run: bool
    retention_days: int
    cutoff: str
    plugin_runs: int
    run_logs: int
    writeback_records: int
    audit_events: int
    protected_run_count: int
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "dry_run": self.dry_run,
            "retention_days": self.retention_days,
            "cutoff": self.cutoff,
            "plugin_runs": self.plugin_runs,
            "run_logs": self.run_logs,
            "writeback_records": self.writeback_records,
            "audit_events": self.audit_events,
            "protected_run_count": self.protected_run_count,
            "message": self.message,
        }


class DatabaseCleanupService:
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._last_report: dict[str, Any] | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="ipp-database-cleanup", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def last_report(self) -> dict[str, Any] | None:
        return self._last_report

    def run_once(self, *, dry_run: bool | None = None) -> dict[str, Any]:
        report = cleanup_database_records(dry_run=dry_run).as_dict()
        self._last_report = report
        return report

    def _loop(self) -> None:
        initial_delay = int(get_database_cleanup_settings().get("initial_delay_sec", 20))
        if self._stop.wait(max(0, initial_delay)):
            return
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception as exc:  # noqa: BLE001
                self._last_report = {"enabled": False, "error": str(exc), "message": "database cleanup failed"}
            interval = int(get_database_cleanup_settings().get("interval_sec", 3600))
            if self._stop.wait(max(60, interval)):
                return


database_cleanup_service = DatabaseCleanupService()


def cleanup_database_records(*, dry_run: bool | None = None) -> DatabaseCleanupReport:
    config = get_database_cleanup_settings()
    enabled = bool(config.get("enabled", True))
    effective_dry_run = bool(config.get("dry_run", False) if dry_run is None else dry_run)
    retention_days = int(config.get("retention_days", 7))
    retention_days = max(1, retention_days)
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=retention_days)
    if not enabled and dry_run is None:
        return DatabaseCleanupReport(False, effective_dry_run, retention_days, cutoff.isoformat(), 0, 0, 0, 0, 0, "database cleanup is disabled")

    run_root = settings.run_storage_dir.resolve()
    run_root.mkdir(parents=True, exist_ok=True)
    lock_path = run_root / ".db-cleanup.lock"
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return DatabaseCleanupReport(enabled, effective_dry_run, retention_days, cutoff.isoformat(), 0, 0, 0, 0, 0, "another database cleanup is active")
        try:
            return _cleanup_locked(config=config, cutoff=cutoff, retention_days=retention_days, dry_run=effective_dry_run)
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _cleanup_locked(*, config: dict[str, Any], cutoff: datetime, retention_days: int, dry_run: bool) -> DatabaseCleanupReport:
    store = MetadataStore(settings.metadata_database)
    store.initialize()
    min_keep_runs = max(0, int(config.get("min_keep_runs", 50)))
    include_audit_events = bool(config.get("include_audit_events", True))

    with store.session_factory() as session:
        protected_run_ids = set(
            session.scalars(
                select(PluginRunModel.run_id)
                .order_by(PluginRunModel.created_at.desc(), PluginRunModel.id.desc())
                .limit(min_keep_runs)
            ).all()
        )

        query = select(PluginRunModel.run_id).where(PluginRunModel.created_at < cutoff)
        if protected_run_ids:
            query = query.where(~PluginRunModel.run_id.in_(protected_run_ids))
        run_ids_to_delete = set(session.scalars(query).all())

        run_logs_count = _count_run_logs(session, cutoff, run_ids_to_delete)
        writeback_count = _count_writebacks(session, cutoff, run_ids_to_delete)
        plugin_runs_count = len(run_ids_to_delete)
        audit_count = _count_audits(session, cutoff) if include_audit_events else 0

        if not dry_run:
            if run_ids_to_delete:
                session.execute(delete(RunLogModel).where(RunLogModel.run_id.in_(run_ids_to_delete)))
                session.execute(delete(WritebackRecordModel).where(WritebackRecordModel.run_id.in_(run_ids_to_delete)))
                session.execute(delete(PluginRunModel).where(PluginRunModel.run_id.in_(run_ids_to_delete)))
            session.execute(delete(RunLogModel).where(RunLogModel.created_at < cutoff))
            session.execute(delete(WritebackRecordModel).where(WritebackRecordModel.created_at < cutoff))
            if include_audit_events:
                session.execute(delete(AuditEventModel).where(AuditEventModel.created_at < cutoff))
            session.commit()

    report = DatabaseCleanupReport(
        enabled=True,
        dry_run=dry_run,
        retention_days=retention_days,
        cutoff=cutoff.isoformat(),
        plugin_runs=plugin_runs_count,
        run_logs=run_logs_count,
        writeback_records=writeback_count,
        audit_events=audit_count,
        protected_run_count=len(protected_run_ids),
        message="database cleanup completed",
    )
    _audit(report)
    return report


def _count_run_logs(session, cutoff: datetime, run_ids: set[str]) -> int:
    total = 0
    if run_ids:
        total += int(session.scalar(select(func.count()).select_from(RunLogModel).where(RunLogModel.run_id.in_(run_ids))) or 0)
    total += int(session.scalar(select(func.count()).select_from(RunLogModel).where(RunLogModel.created_at < cutoff)) or 0)
    return total


def _count_writebacks(session, cutoff: datetime, run_ids: set[str]) -> int:
    total = 0
    if run_ids:
        total += int(session.scalar(select(func.count()).select_from(WritebackRecordModel).where(WritebackRecordModel.run_id.in_(run_ids))) or 0)
    total += int(session.scalar(select(func.count()).select_from(WritebackRecordModel).where(WritebackRecordModel.created_at < cutoff)) or 0)
    return total


def _count_audits(session, cutoff: datetime) -> int:
    return int(session.scalar(select(func.count()).select_from(AuditEventModel).where(AuditEventModel.created_at < cutoff)) or 0)


def _audit(report: DatabaseCleanupReport) -> None:
    try:
        MetadataStore(settings.metadata_database).record_audit_event(
            event_type="maintenance.database_cleanup.completed",
            target_type="metadata_database",
            target_id=str(settings.metadata_database),
            details=report.as_dict(),
        )
    except Exception:
        pass
