from datetime import datetime

from platform_api.services.scheduler_dispatch import _align_to_interval_boundary, _next_fixed_rate_time


def test_next_fixed_rate_time_skips_overdue_slots():
    scheduled_for = datetime(2026, 4, 23, 4, 0, 0)
    finished_at = datetime(2026, 4, 23, 4, 0, 41)
    next_due = _next_fixed_rate_time(
        scheduled_for=scheduled_for,
        finished_at=finished_at,
        interval_sec=30,
    )
    assert next_due == datetime(2026, 4, 23, 4, 1, 0)


def test_next_fixed_rate_time_keeps_next_slot_when_not_overrun():
    scheduled_for = datetime(2026, 4, 23, 4, 0, 0)
    finished_at = datetime(2026, 4, 23, 4, 0, 8)
    next_due = _next_fixed_rate_time(
        scheduled_for=scheduled_for,
        finished_at=finished_at,
        interval_sec=30,
    )
    assert next_due == datetime(2026, 4, 23, 4, 0, 30)


def test_align_to_interval_boundary_moves_to_future_boundary():
    reference = datetime(2026, 4, 23, 4, 0, 41)
    assert _align_to_interval_boundary(reference, 30) == datetime(2026, 4, 23, 4, 1, 0)
