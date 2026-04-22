from __future__ import annotations

from datetime import UTC, datetime
from threading import Lock
from typing import Any

_STATE: dict[str, Any] = {
    'last_worker_id': None,
    'last_due_poll_at': None,
    'last_claim_at': None,
    'last_execute_at': None,
    'last_complete_at': None,
    'due_poll_count': 0,
    'claim_count': 0,
    'execute_count': 0,
    'complete_count': 0,
    'last_due_count': 0,
    'last_next_due_in_ms': None,
    'last_suggested_poll_interval_ms': None,
    'last_scheduled_for': None,
    'last_claimed_at': None,
    'last_run_started_at': None,
    'last_run_finished_at': None,
    'last_error': None,
}
_LOCK = Lock()


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def note_due_poll(*, worker_id: str | None, due_count: int, next_due_in_ms: int | None, suggested_poll_interval_ms: int | None) -> None:
    with _LOCK:
        _STATE['last_worker_id'] = worker_id or _STATE.get('last_worker_id')
        _STATE['last_due_poll_at'] = _utcnow()
        _STATE['due_poll_count'] = int(_STATE.get('due_poll_count', 0)) + 1
        _STATE['last_due_count'] = int(due_count)
        _STATE['last_next_due_in_ms'] = next_due_in_ms
        _STATE['last_suggested_poll_interval_ms'] = suggested_poll_interval_ms


def note_claim(*, worker_id: str | None, scheduled_for: datetime, claimed_at: datetime) -> None:
    with _LOCK:
        _STATE['last_worker_id'] = worker_id or _STATE.get('last_worker_id')
        _STATE['last_claim_at'] = _utcnow()
        _STATE['claim_count'] = int(_STATE.get('claim_count', 0)) + 1
        _STATE['last_scheduled_for'] = scheduled_for
        _STATE['last_claimed_at'] = claimed_at


def note_execute(*, worker_id: str | None, scheduled_for: datetime | None, claimed_at: datetime | None) -> None:
    with _LOCK:
        _STATE['last_worker_id'] = worker_id or _STATE.get('last_worker_id')
        _STATE['last_execute_at'] = _utcnow()
        _STATE['execute_count'] = int(_STATE.get('execute_count', 0)) + 1
        if scheduled_for is not None:
            _STATE['last_scheduled_for'] = scheduled_for
        if claimed_at is not None:
            _STATE['last_claimed_at'] = claimed_at
        _STATE['last_run_started_at'] = _utcnow()


def note_complete(*, worker_id: str | None, finished_at: datetime) -> None:
    with _LOCK:
        _STATE['last_worker_id'] = worker_id or _STATE.get('last_worker_id')
        _STATE['last_complete_at'] = _utcnow()
        _STATE['complete_count'] = int(_STATE.get('complete_count', 0)) + 1
        _STATE['last_run_finished_at'] = finished_at


def note_error(message: str) -> None:
    with _LOCK:
        _STATE['last_error'] = str(message)


def snapshot() -> dict[str, Any]:
    with _LOCK:
        return {
            'runtime_observation': {
                'last_worker_id': _STATE.get('last_worker_id'),
                'last_due_poll_at': _iso(_STATE.get('last_due_poll_at')),
                'last_claim_at': _iso(_STATE.get('last_claim_at')),
                'last_execute_at': _iso(_STATE.get('last_execute_at')),
                'last_complete_at': _iso(_STATE.get('last_complete_at')),
                'due_poll_count': int(_STATE.get('due_poll_count', 0)),
                'claim_count': int(_STATE.get('claim_count', 0)),
                'execute_count': int(_STATE.get('execute_count', 0)),
                'complete_count': int(_STATE.get('complete_count', 0)),
                'last_due_count': int(_STATE.get('last_due_count', 0)),
                'last_next_due_in_ms': _STATE.get('last_next_due_in_ms'),
                'last_suggested_poll_interval_ms': _STATE.get('last_suggested_poll_interval_ms'),
                'last_scheduled_for': _iso(_STATE.get('last_scheduled_for')),
                'last_claimed_at': _iso(_STATE.get('last_claimed_at')),
                'last_run_started_at': _iso(_STATE.get('last_run_started_at')),
                'last_run_finished_at': _iso(_STATE.get('last_run_finished_at')),
                'last_error': _STATE.get('last_error'),
            }
        }
