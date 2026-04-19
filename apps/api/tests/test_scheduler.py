from datetime import UTC, datetime
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "runner"))

from platform_api.services.scheduler import InstanceScheduler


class InstanceSchedulerTests(unittest.TestCase):
    def test_next_fixed_rate_time_handles_sqlite_naive_and_utc_aware_times(self) -> None:
        scheduler = InstanceScheduler(poll_interval_sec=1.0)

        next_time = scheduler._next_fixed_rate_time(
            scheduled_for=datetime(2026, 4, 19, 9, 56, 30),
            finished_at=datetime(2026, 4, 19, 9, 56, 31, tzinfo=UTC),
            interval_sec=30,
        )

        self.assertEqual(next_time, datetime(2026, 4, 19, 9, 57, 0))
        self.assertIsNone(next_time.tzinfo)


if __name__ == "__main__":
    unittest.main()
