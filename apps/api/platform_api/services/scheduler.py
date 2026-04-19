import threading
import traceback
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select

from platform_api.core.config import settings
from platform_api.services.execution import execute_plugin_instance
from platform_api.services.metadata_store import MetadataStore, PluginInstanceModel


class InstanceScheduler:
    """In-process scheduler for the local MVP API service.

    Reliability fixes in this version:
    - catch all exceptions at the scheduler loop boundary so one bad run does not kill the thread
    - reclaim stale instances left in `running`
    - finalize each scheduled run with fixed-rate timing to avoid cumulative drift
    """

    def __init__(self, *, poll_interval_sec: float) -> None:
        self.poll_interval_sec = max(0.1, float(poll_interval_sec))
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_tick_started_at: datetime | None = None
        self._last_tick_finished_at: datetime | None = None
        self._last_error: str | None = None
        self._consecutive_failures = 0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        # recover any stale instances from a previous dead scheduler before starting
        try:
            self._recover_stale_running_instances(
                MetadataStore(settings.metadata_database),
                now=self._db_now(),
            )
        except Exception:
            # best-effort recovery; do not block startup
            pass
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

    def tick(self) -> None:
        now = self._db_now()
        store = MetadataStore(settings.metadata_database)

        # recover instances that were left in `running` because of a previous crash or hard failure
        self._recover_stale_running_instances(store, now=now)

        due_instances = self._claim_due_scheduled_instances(store, now=now)
        for instance in due_instances:
            instance_id = int(instance["id"])
            scheduled_for = instance["scheduled_for"]
            started_at = self._db_now()
            try:
                execute_plugin_instance(
                    instance_id=instance_id,
                    trigger_type="schedule",
                    store=store,
                )
            except Exception as exc:  # noqa: BLE001
                # execute_plugin_instance now records most failures itself, but keep an audit trail here too
                try:
                    store.record_audit_event(
                        event_type="plugin.instance.schedule_failed",
                        target_type="plugin_instance",
                        target_id=str(instance_id),
                        details={
                            "message": str(exc),
                            "exception_type": type(exc).__name__,
                            "scheduled_for": scheduled_for.isoformat() if isinstance(scheduled_for, datetime) else str(scheduled_for),
                            "started_at": started_at.isoformat(),
                        },
                    )
                except Exception:
                    pass
            finally:
                try:
                    self._finalize_scheduled_instance_run(
                        store=store,
                        instance_id=instance_id,
                        scheduled_for=scheduled_for,
                        finished_at=self._db_now(),
                    )
                except Exception as finish_exc:  # noqa: BLE001
                    # Never let finalization kill the scheduler thread.
                    self._last_error = f"finalize failed for instance {instance_id}: {finish_exc}"
                    try:
                        store.record_audit_event(
                            event_type="plugin.instance.schedule_finalize_failed",
                            target_type="plugin_instance",
                            target_id=str(instance_id),
                            details={
                                "message": str(finish_exc),
                                "exception_type": type(finish_exc).__name__,
                            },
                        )
                    except Exception:
                        pass

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
                    pass
            finally:
                self._stop_event.wait(self.poll_interval_sec)

    def status_snapshot(self) -> dict[str, Any]:
        return {
            "thread_alive": bool(self._thread and self._thread.is_alive()),
            "poll_interval_sec": self.poll_interval_sec,
            "last_tick_started_at": self._last_tick_started_at.isoformat() if self._last_tick_started_at else None,
            "last_tick_finished_at": self._last_tick_finished_at.isoformat() if self._last_tick_finished_at else None,
            "last_error": self._last_error,
            "consecutive_failures": self._consecutive_failures,
        }

    def _claim_due_scheduled_instances(self, store: MetadataStore, *, now: datetime, limit: int = 10) -> list[dict[str, Any]]:
        with store.session_factory() as session:
            rows = session.scalars(
                select(PluginInstanceModel)
                .where(
                    PluginInstanceModel.schedule_enabled == 1,
                    PluginInstanceModel.status != "running",
                    or_(
                        PluginInstanceModel.next_scheduled_run_at.is_(None),
                        PluginInstanceModel.next_scheduled_run_at <= now,
                    ),
                )
                .order_by(PluginInstanceModel.next_scheduled_run_at, PluginInstanceModel.id)
                .limit(limit)
            ).all()

            claimed: list[dict[str, Any]] = []
            for row in rows:
                scheduled_for = row.next_scheduled_run_at or now
                row.status = "running"
                row.updated_at = now
                claimed.append(
                    {
                        "id": row.id,
                        "name": row.name,
                        "schedule_interval_sec": row.schedule_interval_sec,
                        "scheduled_for": scheduled_for,
                    }
                )
            session.commit()
            return claimed

    def _recover_stale_running_instances(self, store: MetadataStore, *, now: datetime) -> int:
        """Move stale `running` instances back to schedulable state.

        This prevents a single crash from leaving the instance permanently invisible
        to the scheduler.
        """
        recovered: list[int] = []
        with store.session_factory() as session:
            rows = session.scalars(
                select(PluginInstanceModel).where(PluginInstanceModel.status == "running")
            ).all()

            for row in rows:
                interval_sec = max(5, int(row.schedule_interval_sec or 30))
                grace_sec = max(interval_sec * 4, int(self.poll_interval_sec) * 10, 60)
                last_activity = row.updated_at or row.last_scheduled_run_at or row.created_at
                if last_activity is None:
                    continue
                if last_activity > now - timedelta(seconds=grace_sec):
                    continue

                row.status = "scheduled" if row.schedule_enabled else "stopped"
                if row.schedule_enabled:
                    scheduled_for = row.next_scheduled_run_at or last_activity
                    row.next_scheduled_run_at = self._next_fixed_rate_time(
                        scheduled_for=scheduled_for,
                        finished_at=now,
                        interval_sec=interval_sec,
                    )
                else:
                    row.next_scheduled_run_at = None
                row.updated_at = now
                recovered.append(row.id)

            session.commit()

        for instance_id in recovered:
            try:
                store.record_audit_event(
                    event_type="plugin.instance.schedule_recovered",
                    target_type="plugin_instance",
                    target_id=str(instance_id),
                    details={"message": "Recovered stale running instance"},
                )
            except Exception:
                pass
        return len(recovered)

    def _finalize_scheduled_instance_run(
        self,
        *,
        store: MetadataStore,
        instance_id: int,
        scheduled_for: datetime,
        finished_at: datetime,
    ) -> None:
        with store.session_factory() as session:
            row = session.get(PluginInstanceModel, instance_id)
            if row is None:
                return

            row.last_scheduled_run_at = finished_at
            if row.schedule_enabled:
                interval_sec = max(5, int(row.schedule_interval_sec or 30))
                row.next_scheduled_run_at = self._next_fixed_rate_time(
                    scheduled_for=scheduled_for,
                    finished_at=finished_at,
                    interval_sec=interval_sec,
                )
                row.status = "scheduled"
            else:
                row.next_scheduled_run_at = None
                row.status = "stopped"
            row.updated_at = finished_at
            session.commit()

    def _next_fixed_rate_time(
        self,
        *,
        scheduled_for: datetime,
        finished_at: datetime,
        interval_sec: int,
    ) -> datetime:
        """Advance on the planned schedule grid instead of `finished_at + interval`."""
        scheduled_for = self._as_db_time(scheduled_for)
        finished_at = self._as_db_time(finished_at)
        interval = timedelta(seconds=max(5, int(interval_sec or 30)))
        next_time = scheduled_for
        while next_time <= finished_at:
            next_time += interval
        return next_time

    def _db_now(self) -> datetime:
        return datetime.now(UTC).replace(tzinfo=None)

    def _as_db_time(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value
        return value.astimezone(UTC).replace(tzinfo=None)


scheduler = InstanceScheduler(poll_interval_sec=settings.scheduler.poll_interval_sec)
