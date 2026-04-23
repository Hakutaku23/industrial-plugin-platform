from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends

from platform_api.core.config import settings
from platform_api.security import Principal, require_permission
from platform_api.services.license_manager import license_manager
from platform_api.services.metadata_store import MetadataStore
from platform_api.services.scheduler import scheduler

router = APIRouter(prefix='/api/v1', tags=['observability'])


@router.get('/observability/summary')
def observability_summary(
    principal: Principal = Depends(require_permission('system.read')),
) -> dict[str, object]:
    store = MetadataStore(settings.metadata_database)
    audit_events = _select_recent_observability_events(store.list_audit_events())
    recent_schedule_runs = _select_recent_schedule_runs(store.list_plugin_runs())
    schedule_run_stats = _summarize_schedule_runs(recent_schedule_runs)
    return {
        'scheduler': {
            'enabled': settings.scheduler.enabled,
            **scheduler.status_snapshot(),
        },
        'locks': scheduler.lock_snapshot(limit=100),
        'license': license_manager.get_snapshot(force_refresh=False).model_dump(),
        'recent_events': audit_events,
        'recent_schedule_runs': recent_schedule_runs[:20],
        'schedule_run_stats': schedule_run_stats,
        'generated_at': datetime.now(UTC).isoformat(),
    }


def _select_recent_observability_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prefixes = (
        'scheduler.',
        'plugin.instance.schedule_',
        'plugin.instance.lock_',
        'plugin.run.skipped',
        'license.',
        'security.license.',
    )
    matched = [item for item in events if str(item.get('event_type', '')).startswith(prefixes)]
    matched.sort(key=lambda item: str(item.get('created_at', '')), reverse=True)
    return matched[:40]


def _select_recent_schedule_runs(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matched = [item for item in runs if str(item.get('trigger_type')) == 'schedule']
    matched.sort(key=lambda item: str(item.get('started_at', '')), reverse=True)
    return matched[:50]


def _summarize_schedule_runs(runs: list[dict[str, Any]]) -> dict[str, int]:
    now = datetime.now(UTC)
    window = now - timedelta(hours=24)
    summary = {
        'completed_24h': 0,
        'failed_24h': 0,
        'timed_out_24h': 0,
        'skipped_24h': 0,
        'partial_success_24h': 0,
    }
    for item in runs:
        started_at = _parse_iso(item.get('started_at'))
        if started_at is None or started_at < window:
            continue
        status = str(item.get('status', '')).upper()
        if status == 'COMPLETED':
            summary['completed_24h'] += 1
        elif status == 'FAILED':
            summary['failed_24h'] += 1
        elif status == 'TIMED_OUT':
            summary['timed_out_24h'] += 1
        elif status == 'SKIPPED':
            summary['skipped_24h'] += 1
        elif status == 'PARTIAL_SUCCESS':
            summary['partial_success_24h'] += 1
    return summary


def _parse_iso(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
