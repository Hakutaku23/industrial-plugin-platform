import json
import logging
import threading
import traceback
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select

from platform_api.core.config import settings
from platform_api.services.execution import execute_plugin_instance, resolve_instance_lock_ttl_sec
from platform_api.services.execution_lock import InstanceExecutionLease, RedisExecutionLockManager
from platform_api.services.metadata_store import (
    AuditEventModel,
    MetadataStore,
    PluginInstanceModel,
    PluginPackageModel,
    PluginRunModel,
    PluginVersionModel,
    RunLogModel,
)

logger = logging.getLogger(__name__)


class InstanceScheduler:
    """In-process scheduler for the local MVP API service.

    Current behavior:
    - dispatch scheduled executions to a thread pool to avoid blocking the scheduler loop
    - use Redis instance locks as the single execution mutex source
    - record skipped schedule slots when the lock is already held
    """

    def __init__(
        self,
        *,
        poll_interval_sec: float,
        max_workers: int | None = None,
        lock_manager: RedisExecutionLockManager | None = None,
    ) -> None:
        self.poll_interval_sec = max(0.1, float(poll_interval_sec))
        self.max_workers = max(1, int(max_workers or settings.scheduler.max_workers))
        self.lock_manager = lock_manager or RedisExecutionLockManager.from_settings()
        self.executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="instance-worker",
        )
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_tick_started_at: datetime | None = None
        self._last_tick_finished_at: datetime | None = None
        self._last_error: str | None = None
        self._consecutive_failures = 0
        self._futures: set[Future[Any]] = set()
        self._futures_lock = threading.Lock()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        try:
            self._recover_instances_without_lock(
                MetadataStore(settings.metadata_database),
                now=self._db_now(),
            )
        except Exception:
            logger.exception("scheduler startup recovery failed")
        self._thread = threading.Thread(
            target=self._run_loop,
            name="instance-scheduler",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self.executor.shutdown(wait=True)

    def tick(self) -> None:
        now = self._db_now()
        store = MetadataStore(settings.metadata_database)

        self._recover_instances_without_lock(store, now=now)

        due_instances = self._list_due_scheduled_instances(store, now=now)
        for instance in due_instances:
            instance_id = int(instance["id"])
            scheduled_for = self._as_db_time(instance["scheduled_for"])
            ttl_sec = resolve_instance_lock_ttl_sec(instance_id=instance_id, store=store)
            lease = self.lock_manager.acquire(instance_id, ttl_sec=ttl_sec)
            if lease is None:
                skipped_count = self._handle_locked_due_instance(
                    store=store,
                    instance_id=instance_id,
                    scheduled_for=scheduled_for,
                    observed_at=self._db_now(),
                )
                if skipped_count:
                    logger.info(
                        "instance %s skipped %s scheduled slot(s) because Redis lock is held",
                        instance_id,
                        skipped_count,
                    )
                continue

            claimed = self._claim_due_scheduled_instance(
                store=store,
                instance_id=instance_id,
                scheduled_for=scheduled_for,
                claimed_at=self._db_now(),
            )
            if claimed is None:
                self.lock_manager.release(lease)
                continue

            future = self.executor.submit(
                self._execute_scheduled_instance,
                claimed["id"],
                claimed["scheduled_for"],
                lease,
            )
            self._track_future(future)

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            self._last_tick_started_at = datetime.now(UTC)
            try:
                self.tick()
                self._last_tick_finished_at = datetime.now(UTC)
                self._last_error = None
                self._consecutive_failures = 0
            except Exception as exc:  # noqa: BLE001
                self._last_tick_finished_at = datetime.now(UTC)
                self._consecutive_failures += 1
                self._last_error = traceback.format_exc()
                try:
                    MetadataStore(settings.metadata_database).record_audit_event(
                        event_type="scheduler.loop.crashed",
                        target_type="scheduler",
                        target_id="instance-scheduler",
                        details={
                            "message": str(exc),
                            "exception_type": type(exc).__name__,
                            "consecutive_failures": self._consecutive_failures,
                        },
                    )
                except Exception:
                    logger.exception("failed to record scheduler crash audit event")
            finally:
                self._stop_event.wait(self.poll_interval_sec)

    def status_snapshot(self) -> dict[str, Any]:
        with self._futures_lock:
            inflight = len([future for future in self._futures if not future.done()])
        try:
            active_locks = self.lock_manager.list_active_locks(limit=200)
        except Exception as exc:  # noqa: BLE001
            active_locks = []
            lock_error = str(exc)
        else:
            lock_error = None
        return {
            "thread_alive": bool(self._thread and self._thread.is_alive()),
            "poll_interval_sec": self.poll_interval_sec,
            "max_workers": self.max_workers,
            "inflight_tasks": inflight,
            "active_lock_count": len(active_locks),
            "lock_observation_error": lock_error,
            "last_tick_started_at": self._last_tick_started_at.isoformat() if self._last_tick_started_at else None,
            "last_tick_finished_at": self._last_tick_finished_at.isoformat() if self._last_tick_finished_at else None,
            "last_error": self._last_error,
            "consecutive_failures": self._consecutive_failures,
        }

    def lock_snapshot(self, *, limit: int = 200) -> list[dict[str, Any]]:
        return self.lock_manager.list_active_locks(limit=limit)

    def _list_due_scheduled_instances(self, store: MetadataStore, *, now: datetime, limit: int = 50) -> list[dict[str, Any]]:
        with store.session_factory() as session:
            rows = session.scalars(
                select(PluginInstanceModel)
                .where(
                    PluginInstanceModel.schedule_enabled == 1,
                    or_(
                        PluginInstanceModel.next_scheduled_run_at.is_(None),
                        PluginInstanceModel.next_scheduled_run_at <= now,
                    ),
                )
                .order_by(PluginInstanceModel.next_scheduled_run_at, PluginInstanceModel.id)
                .limit(limit)
            ).all()

            result: list[dict[str, Any]] = []
            for row in rows:
                result.append(
                    {
                        "id": row.id,
                        "name": row.name,
                        "schedule_interval_sec": row.schedule_interval_sec,
                        "scheduled_for": row.next_scheduled_run_at or now,
                    }
                )
            return result

    def _claim_due_scheduled_instance(
        self,
        store: MetadataStore,
        *,
        instance_id: int,
        scheduled_for: datetime,
        claimed_at: datetime,
    ) -> dict[str, Any] | None:
        with store.session_factory() as session:
            row = session.get(PluginInstanceModel, instance_id)
            if row is None or not row.schedule_enabled:
                return None

            current_due = self._as_db_time(row.next_scheduled_run_at) if row.next_scheduled_run_at else scheduled_for
            if current_due > scheduled_for:
                return None

            interval_sec = max(5, int(row.schedule_interval_sec or 30))
            row.status = "running"
            row.next_scheduled_run_at = self._next_fixed_rate_time(
                scheduled_for=scheduled_for,
                finished_at=claimed_at,
                interval_sec=interval_sec,
            )
            row.updated_at = claimed_at
            session.commit()

            return {
                "id": row.id,
                "name": row.name,
                "scheduled_for": scheduled_for,
                "schedule_interval_sec": interval_sec,
            }

    def _handle_locked_due_instance(
        self,
        *,
        store: MetadataStore,
        instance_id: int,
        scheduled_for: datetime,
        observed_at: datetime,
    ) -> int:
        skipped_slots: list[datetime] = []
        with store.session_factory() as session:
            row = session.get(PluginInstanceModel, instance_id)
            if row is None or not row.schedule_enabled:
                return 0

            current_due = self._as_db_time(row.next_scheduled_run_at) if row.next_scheduled_run_at else scheduled_for
            if current_due > scheduled_for:
                return 0

            interval_sec = max(5, int(row.schedule_interval_sec or 30))
            interval = timedelta(seconds=interval_sec)
            next_due = scheduled_for
            while next_due <= observed_at:
                skipped_slots.append(next_due)
                next_due += interval

            row.next_scheduled_run_at = next_due
            row.updated_at = observed_at
            row.status = "running"
            session.commit()

        if skipped_slots:
            try:
                store.record_audit_event(
                    event_type="plugin.instance.lock_contended",
                    target_type="plugin_instance",
                    target_id=str(instance_id),
                    details={
                        "message": "scheduled execution skipped because Redis lock is already held",
                        "skipped_slots": [item.isoformat() for item in skipped_slots],
                    },
                )
            except Exception:
                logger.exception("failed to record lock contention audit event for instance %s", instance_id)

        for skipped_for in skipped_slots:
            try:
                self._record_skipped_run(
                    store=store,
                    instance_id=instance_id,
                    scheduled_for=skipped_for,
                    reason="Skipped because Redis execution lock is already held",
                )
            except Exception:
                logger.exception(
                    "failed to record skipped run for instance %s at %s",
                    instance_id,
                    skipped_for.isoformat(),
                )
        return len(skipped_slots)

    def _recover_instances_without_lock(self, store: MetadataStore, *, now: datetime) -> int:
        recovered: list[int] = []
        with store.session_factory() as session:
            rows = session.scalars(
                select(PluginInstanceModel).where(PluginInstanceModel.status == "running")
            ).all()

            for row in rows:
                if self.lock_manager.is_locked(row.id):
                    continue

                interval_sec = max(5, int(row.schedule_interval_sec or 30))
                if row.schedule_enabled:
                    if row.next_scheduled_run_at is None:
                        row.next_scheduled_run_at = self._align_to_interval_boundary(now, interval_sec)
                    row.status = "scheduled"
                else:
                    row.next_scheduled_run_at = None
                    row.status = "configured"
                row.updated_at = now
                recovered.append(row.id)

            session.commit()

        for instance_id in recovered:
            try:
                store.record_audit_event(
                    event_type="plugin.instance.schedule_recovered",
                    target_type="plugin_instance",
                    target_id=str(instance_id),
                    details={"message": "Recovered running instance without Redis lock"},
                )
            except Exception:
                logger.exception("failed to record recovery audit event for instance %s", instance_id)
        return len(recovered)

    def _execute_scheduled_instance(
        self,
        instance_id: int,
        scheduled_for: datetime,
        lease: InstanceExecutionLease,
    ) -> None:
        store = MetadataStore(settings.metadata_database)
        try:
            execute_plugin_instance(
                instance_id=instance_id,
                trigger_type="schedule",
                store=store,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("scheduled execution failed for instance %s", instance_id)
            try:
                store.record_audit_event(
                    event_type="plugin.instance.schedule_failed",
                    target_type="plugin_instance",
                    target_id=str(instance_id),
                    details={
                        "message": str(exc),
                        "exception_type": type(exc).__name__,
                        "scheduled_for": scheduled_for.isoformat(),
                    },
                )
            except Exception:
                logger.exception("failed to record schedule_failed audit event for instance %s", instance_id)
        finally:
            finished_at = self._db_now()
            try:
                self._finalize_scheduled_instance_run(
                    store=store,
                    instance_id=instance_id,
                    finished_at=finished_at,
                )
            finally:
                try:
                    self.lock_manager.release(lease)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("failed to release Redis lock for instance %s", instance_id)
                    try:
                        store.record_audit_event(
                            event_type="plugin.instance.lock_error",
                            target_type="plugin_instance",
                            target_id=str(instance_id),
                            details={"message": str(exc), "phase": "release", "trigger_type": "schedule"},
                        )
                    except Exception:
                        logger.exception("failed to record lock_error audit event for instance %s", instance_id)

    def _finalize_scheduled_instance_run(
        self,
        *,
        store: MetadataStore,
        instance_id: int,
        finished_at: datetime,
    ) -> None:
        with store.session_factory() as session:
            row = session.get(PluginInstanceModel, instance_id)
            if row is None:
                return

            row.last_scheduled_run_at = finished_at
            if row.schedule_enabled:
                if row.next_scheduled_run_at is None:
                    row.next_scheduled_run_at = self._align_to_interval_boundary(
                        finished_at,
                        max(5, int(row.schedule_interval_sec or 30)),
                    )
                row.status = "scheduled"
            else:
                row.next_scheduled_run_at = None
                row.status = "stopped"
            row.updated_at = finished_at
            session.commit()

    def _record_skipped_run(
        self,
        *,
        store: MetadataStore,
        instance_id: int,
        scheduled_for: datetime,
        reason: str,
    ) -> None:
        with store.session_factory() as session:
            row = session.execute(
                select(PluginInstanceModel, PluginPackageModel, PluginVersionModel)
                .join(PluginPackageModel, PluginPackageModel.id == PluginInstanceModel.package_id)
                .join(PluginVersionModel, PluginVersionModel.id == PluginInstanceModel.version_id)
                .where(PluginInstanceModel.id == instance_id)
            ).first()
            if row is None:
                return

            instance, package, version = row
            run_id = f"skip-{uuid.uuid4().hex}"
            created_at = datetime.now(UTC)
            started_at = self._as_db_time(scheduled_for)
            error = {
                "code": "E_SCHEDULE_SKIPPED",
                "message": reason,
                "scheduled_for": started_at.isoformat(),
            }
            run = PluginRunModel(
                run_id=run_id,
                package_id=package.id,
                version_id=version.id,
                instance_id=instance.id,
                trigger_type="schedule",
                environment=settings.environment,
                status="SKIPPED",
                attempt=1,
                inputs_json=json.dumps({}, ensure_ascii=False, sort_keys=True),
                outputs_json=json.dumps({}, ensure_ascii=False, sort_keys=True),
                metrics_json=json.dumps({}, ensure_ascii=False, sort_keys=True),
                error_json=json.dumps(error, ensure_ascii=False, sort_keys=True),
                created_at=created_at,
                started_at=started_at,
                finished_at=started_at,
            )
            session.add(run)
            session.flush()
            session.add(
                RunLogModel(
                    run_id=run_id,
                    source="scheduler",
                    level="WARN",
                    message=reason,
                    created_at=created_at,
                )
            )
            session.add(
                AuditEventModel(
                    event_type="plugin.run.skipped",
                    actor="local-dev",
                    target_type="plugin_run",
                    target_id=run_id,
                    details_json=json.dumps(
                        {
                            "status": "SKIPPED",
                            "instance_id": instance.id,
                            "scheduled_for": started_at.isoformat(),
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    created_at=created_at,
                )
            )
            session.commit()

    def _track_future(self, future: Future[Any]) -> None:
        with self._futures_lock:
            self._futures.add(future)

        def _discard(done_future: Future[Any]) -> None:
            with self._futures_lock:
                self._futures.discard(done_future)

        future.add_done_callback(_discard)

    def _next_fixed_rate_time(
        self,
        *,
        scheduled_for: datetime,
        finished_at: datetime,
        interval_sec: int,
    ) -> datetime:
        scheduled_for = self._as_db_time(scheduled_for)
        finished_at = self._as_db_time(finished_at)
        interval = timedelta(seconds=max(5, int(interval_sec or 30)))
        next_time = scheduled_for
        while next_time <= finished_at:
            next_time += interval
        return next_time

    def _align_to_interval_boundary(self, reference: datetime, interval_sec: int) -> datetime:
        reference = self._as_db_time(reference)
        interval = timedelta(seconds=max(5, int(interval_sec or 30)))
        epoch = datetime(1970, 1, 1)
        elapsed = max(0, int((reference - epoch).total_seconds()))
        step = int(interval.total_seconds())
        next_elapsed = (elapsed // step + 1) * step
        return epoch + timedelta(seconds=next_elapsed)

    def _db_now(self) -> datetime:
        return datetime.now(UTC).replace(tzinfo=None)

    def _as_db_time(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value
        return value.astimezone(UTC).replace(tzinfo=None)


scheduler = InstanceScheduler(
    poll_interval_sec=settings.scheduler.poll_interval_sec,
    max_workers=settings.scheduler.max_workers,
)
