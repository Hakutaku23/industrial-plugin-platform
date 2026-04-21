from datetime import UTC, datetime
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "runner"))

from platform_api.core.config import settings
from platform_api.services.metadata_store import (
    MetadataStore,
    PluginInstanceModel,
    PluginPackageModel,
    PluginVersionModel,
)
from platform_api.services.scheduler import InstanceScheduler


class _FakeLockManager:
    def __init__(self) -> None:
        self.locked: set[int] = set()

    def acquire(self, instance_id: int, *, ttl_sec: int):
        if instance_id in self.locked:
            return None
        self.locked.add(instance_id)
        return object()

    def release(self, lease) -> None:
        return None

    def is_locked(self, instance_id: int) -> bool:
        return instance_id in self.locked


class InstanceSchedulerTests(unittest.TestCase):
    def test_next_fixed_rate_time_handles_sqlite_naive_and_utc_aware_times(self) -> None:
        scheduler = InstanceScheduler(poll_interval_sec=1.0, lock_manager=_FakeLockManager())

        next_time = scheduler._next_fixed_rate_time(
            scheduled_for=datetime(2026, 4, 19, 9, 56, 30),
            finished_at=datetime(2026, 4, 19, 9, 56, 31, tzinfo=UTC),
            interval_sec=30,
        )

        self.assertEqual(next_time, datetime(2026, 4, 19, 9, 57, 0))
        self.assertIsNone(next_time.tzinfo)

    def test_handle_locked_due_instance_records_skipped_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "platform.sqlite3"
            store = MetadataStore(db_path)
            store.initialize()

            now = datetime(2026, 4, 19, 9, 56, 0)
            with store.session_factory() as session:
                package = PluginPackageModel(
                    name="demo-plugin",
                    display_name="Demo Plugin",
                    description="demo",
                    status="validated",
                    created_at=now,
                    updated_at=now,
                )
                session.add(package)
                session.flush()

                version = PluginVersionModel(
                    package_id=package.id,
                    version="0.1.0",
                    digest="digest-demo",
                    package_path=str(Path(tmpdir) / "pkg"),
                    manifest_json='{"apiVersion":"plugin.platform/v1","kind":"PluginPackage","metadata":{"name":"demo-plugin","displayName":"Demo Plugin","version":"0.1.0","author":"tester","description":"demo","tags":[]},"spec":{"pluginType":"python","packageFormat":"directory","entry":{"mode":"function","file":"runtime/main.py","callable":"run"},"runtime":{"workingDir":".","timeoutSec":30,"env":{}},"schedule":{"type":"interval","intervalSec":30},"inputs":[],"outputs":[],"permissions":{"network":false,"filesystem":"scoped","writeback":false,"subprocess":false}},"compatibility":{"platformApi":"0.1","runnerApi":"0.1","supportedEnvironments":[]}}',
                    status="validated",
                    created_at=now,
                    updated_at=now,
                )
                session.add(version)
                session.flush()

                instance = PluginInstanceModel(
                    name="demo-instance",
                    package_id=package.id,
                    version_id=version.id,
                    input_bindings_json="[]",
                    output_bindings_json="[]",
                    config_json="{}",
                    writeback_enabled=0,
                    schedule_enabled=1,
                    schedule_interval_sec=30,
                    last_scheduled_run_at=None,
                    next_scheduled_run_at=datetime(2026, 4, 19, 9, 56, 30),
                    status="running",
                    created_at=now,
                    updated_at=now,
                )
                session.add(instance)
                session.commit()
                instance_id = instance.id

            scheduler = InstanceScheduler(poll_interval_sec=1.0, lock_manager=_FakeLockManager())
            scheduler._handle_locked_due_instance(
                store=store,
                instance_id=instance_id,
                scheduled_for=datetime(2026, 4, 19, 9, 56, 30),
                observed_at=datetime(2026, 4, 19, 9, 57, 5),
            )

            runs = store.list_plugin_runs(instance_id=instance_id)
            self.assertEqual(sum(1 for item in runs if item["status"] == "SKIPPED"), 2)


if __name__ == "__main__":
    unittest.main()
