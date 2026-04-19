import threading
from datetime import UTC, datetime

from platform_api.core.config import settings
from platform_api.services.execution import PluginExecutionError, execute_plugin_instance
from platform_api.services.metadata_store import MetadataStore


class InstanceScheduler:
    """Small in-process scheduler for the local MVP API service."""

    def __init__(self, *, poll_interval_sec: float) -> None:
        self.poll_interval_sec = poll_interval_sec
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="instance-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def tick(self) -> None:
        store = MetadataStore(settings.metadata_database)
        due_instances = store.claim_due_scheduled_instances(now=datetime.now(UTC))
        for instance in due_instances:
            instance_id = int(instance["id"])
            try:
                execute_plugin_instance(
                    instance_id=instance_id,
                    trigger_type="schedule",
                    store=store,
                )
            except PluginExecutionError as exc:
                store.record_audit_event(
                    event_type="plugin.instance.schedule_failed",
                    target_type="plugin_instance",
                    target_id=str(instance_id),
                    details={"message": str(exc)},
                )
            finally:
                store.finish_scheduled_instance_run(
                    instance_id=instance_id,
                    finished_at=datetime.now(UTC),
                )

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            self.tick()
            self._stop_event.wait(self.poll_interval_sec)


scheduler = InstanceScheduler(poll_interval_sec=settings.scheduler.poll_interval_sec)
