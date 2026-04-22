from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select

from platform_api.core.config import settings
from platform_api.services.execution import (
    execute_plugin_instance,
    resolve_instance_lock_ttl_sec,
)
from platform_api.services.execution_lock import (
    InstanceExecutionLease,
    RedisExecutionLockManager,
)
from platform_api.services.metadata_store import (
    AuditEventModel,
    MetadataStore,
    PluginInstanceModel,
    PluginPackageModel,
    PluginRunModel,
    PluginVersionModel,
    RunLogModel,
)
from platform_api.services.scheduler_runtime_state import note_claim, note_complete, note_due_poll, note_error, note_execute

_LAST_RECOVERY_AT: datetime | None = None


def get_due_snapshot(*, limit: int = 50, worker_id: str | None = None) -> dict[str, Any]:
    store = MetadataStore(settings.metadata_database)
    now = _db_now()
    recovered_count = _maybe_recover_instances_without_lock(store, now=now)
    with store.session_factory() as session:
        due_rows = session.scalars(
            select(PluginInstanceModel)
            .where(
                PluginInstanceModel.schedule_enabled == 1,
                or_(
                    PluginInstanceModel.next_scheduled_run_at.is_(None),
                    PluginInstanceModel.next_scheduled_run_at <= now,
                ),
            )
            .order_by(PluginInstanceModel.next_scheduled_run_at, PluginInstanceModel.id)
            .limit(max(1, int(limit)))
        ).all()

        items: list[dict[str, Any]] = []
        for row in due_rows:
            scheduled_for = row.next_scheduled_run_at or now
            items.append(
                {
                    'id': row.id,
                    'name': row.name,
                    'schedule_interval_sec': int(row.schedule_interval_sec or 30),
                    'scheduled_for': _as_db_time(scheduled_for).isoformat(),
                }
            )

        next_scheduled_row = session.scalars(
            select(PluginInstanceModel)
            .where(
                PluginInstanceModel.schedule_enabled == 1,
                PluginInstanceModel.next_scheduled_run_at.is_not(None),
            )
            .order_by(PluginInstanceModel.next_scheduled_run_at, PluginInstanceModel.id)
            .limit(1)
        ).first()

    next_due_in_ms: int | None = None
    if next_scheduled_row is not None and next_scheduled_row.next_scheduled_run_at is not None:
        delta_ms = int((_as_db_time(next_scheduled_row.next_scheduled_run_at) - now).total_seconds() * 1000)
        next_due_in_ms = max(0, delta_ms)

    suggested_poll_interval_ms = _suggest_poll_interval_ms(items=items, next_due_in_ms=next_due_in_ms)
    note_due_poll(
        worker_id=worker_id,
        due_count=len(items),
        next_due_in_ms=next_due_in_ms,
        suggested_poll_interval_ms=suggested_poll_interval_ms,
    )
    return {
        'items': items,
        'next_due_in_ms': next_due_in_ms,
        'suggested_poll_interval_ms': suggested_poll_interval_ms,
        'recovered_count': recovered_count,
    }


def claim_due_instance(
    *,
    instance_id: int,
    scheduled_for: datetime,
    worker_id: str,
) -> dict[str, Any]:
    store = MetadataStore(settings.metadata_database)
    lock_manager = RedisExecutionLockManager.from_settings()
    ttl_sec = resolve_instance_lock_ttl_sec(instance_id=instance_id, store=store)
    lease = lock_manager.acquire(instance_id, ttl_sec=ttl_sec)
    if lease is None:
        _handle_locked_due_instance(
            store=store,
            instance_id=instance_id,
            scheduled_for=scheduled_for,
            observed_at=_db_now(),
        )
        return {'claimed': False, 'lease_key': None, 'lease_token': None, 'claimed_at': None}

    claimed_at = _db_now()
    claimed = _claim_due_scheduled_instance(
        store=store,
        instance_id=instance_id,
        scheduled_for=scheduled_for,
        claimed_at=claimed_at,
    )
    if claimed is None:
        lock_manager.release(lease)
        return {'claimed': False, 'lease_key': None, 'lease_token': None, 'claimed_at': None}

    store.record_audit_event(
        event_type='scheduler.task.claimed',
        target_type='plugin_instance',
        target_id=str(instance_id),
        details={
            'worker_id': worker_id,
            'scheduled_for': scheduled_for.isoformat(),
            'claimed_at': claimed_at.isoformat(),
        },
    )
    note_claim(worker_id=worker_id, scheduled_for=scheduled_for, claimed_at=claimed_at)
    return {
        'claimed': True,
        'lease_key': lease.key,
        'lease_token': lease.token,
        'claimed_at': claimed_at.isoformat(),
    }


def execute_claimed_instance(*, instance_id: int, worker_id: str | None = None, scheduled_for: datetime | None = None, claimed_at: datetime | None = None) -> dict[str, Any]:
    store = MetadataStore(settings.metadata_database)
    note_execute(worker_id=worker_id, scheduled_for=scheduled_for, claimed_at=claimed_at)
    execution_context: dict[str, Any] = {}
    if scheduled_for is not None:
        execution_context['scheduled_for'] = scheduled_for.isoformat()
    if claimed_at is not None:
        execution_context['claimed_at'] = claimed_at.isoformat()
    if worker_id:
        execution_context['scheduler_worker_id'] = worker_id
    return execute_plugin_instance(
        instance_id=instance_id,
        trigger_type='schedule',
        store=store,
        execution_context=execution_context or None,
    )


def complete_due_instance(
    *,
    instance_id: int,
    lease_key: str,
    lease_token: str,
    worker_id: str | None = None,
) -> dict[str, Any]:
    store = MetadataStore(settings.metadata_database)
    lock_manager = RedisExecutionLockManager.from_settings()
    finished_at = _db_now()
    try:
        _finalize_scheduled_instance_run(
            store=store,
            instance_id=instance_id,
            finished_at=finished_at,
        )
    finally:
        lock_manager.release(
            InstanceExecutionLease(
                instance_id=int(instance_id),
                key=str(lease_key),
                token=str(lease_token),
            )
        )
    note_complete(worker_id=worker_id, finished_at=finished_at)
    return {'completed': True, 'instance_id': instance_id, 'finished_at': finished_at.isoformat()}


def recover_instances_without_lock(*, force: bool = True) -> int:
    store = MetadataStore(settings.metadata_database)
    now = _db_now()
    if force:
        return _recover_instances_without_lock(store, now=now)
    return _maybe_recover_instances_without_lock(store, now=now)


def _maybe_recover_instances_without_lock(store: MetadataStore, *, now: datetime) -> int:
    global _LAST_RECOVERY_AT
    interval = max(1, int(settings.scheduler.recovery_interval_sec))
    if _LAST_RECOVERY_AT is not None and (now - _LAST_RECOVERY_AT).total_seconds() < interval:
        return 0
    recovered = _recover_instances_without_lock(store, now=now)
    _LAST_RECOVERY_AT = now
    return recovered


def _recover_instances_without_lock(store: MetadataStore, *, now: datetime) -> int:
    recovered: list[int] = []
    lock_manager = RedisExecutionLockManager.from_settings()
    with store.session_factory() as session:
        rows = session.scalars(
            select(PluginInstanceModel).where(PluginInstanceModel.status == 'running')
        ).all()

        for row in rows:
            if lock_manager.is_locked(row.id):
                continue
            interval_sec = max(5, int(row.schedule_interval_sec or 30))
            if row.schedule_enabled:
                if row.next_scheduled_run_at is None:
                    row.next_scheduled_run_at = _align_to_interval_boundary(now, interval_sec)
                row.status = 'scheduled'
            else:
                row.next_scheduled_run_at = None
                row.status = 'configured'
            row.updated_at = now
            recovered.append(row.id)

        session.commit()

    for instance_id in recovered:
        try:
            store.record_audit_event(
                event_type='plugin.instance.schedule_recovered',
                target_type='plugin_instance',
                target_id=str(instance_id),
                details={'message': 'Recovered running instance without Redis lock'},
            )
        except Exception as exc:
            note_error(f'recovery audit failed: {exc}')
    return len(recovered)


def _claim_due_scheduled_instance(
    *,
    store: MetadataStore,
    instance_id: int,
    scheduled_for: datetime,
    claimed_at: datetime,
) -> dict[str, Any] | None:
    with store.session_factory() as session:
        row = session.get(PluginInstanceModel, instance_id)
        if row is None or not row.schedule_enabled:
            return None

        current_due = _as_db_time(row.next_scheduled_run_at) if row.next_scheduled_run_at else scheduled_for
        if current_due > scheduled_for:
            return None

        interval_sec = max(5, int(row.schedule_interval_sec or 30))
        row.status = 'running'
        row.next_scheduled_run_at = _next_fixed_rate_time(
            scheduled_for=scheduled_for,
            finished_at=claimed_at,
            interval_sec=interval_sec,
        )
        row.updated_at = claimed_at
        session.commit()

        return {
            'id': row.id,
            'name': row.name,
            'scheduled_for': scheduled_for,
            'schedule_interval_sec': interval_sec,
        }


def _handle_locked_due_instance(
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

        current_due = _as_db_time(row.next_scheduled_run_at) if row.next_scheduled_run_at else scheduled_for
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
        row.status = 'running'
        session.commit()

    if skipped_slots:
        try:
            store.record_audit_event(
                event_type='plugin.instance.lock_contended',
                target_type='plugin_instance',
                target_id=str(instance_id),
                details={
                    'message': 'scheduled execution skipped because Redis lock is already held',
                    'skipped_slots': [item.isoformat() for item in skipped_slots],
                },
            )
        except Exception as exc:
            note_error(f'lock contention audit failed: {exc}')

    for skipped_for in skipped_slots:
        try:
            _record_skipped_run(
                store=store,
                instance_id=instance_id,
                scheduled_for=skipped_for,
                reason='Skipped because Redis execution lock is already held',
            )
        except Exception as exc:
            note_error(f'skipped run record failed: {exc}')
    return len(skipped_slots)


def _record_skipped_run(
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
        run_id = f'skip-{uuid.uuid4().hex}'
        created_at = datetime.now(UTC)
        started_at = _as_db_time(scheduled_for)
        error = {
            'code': 'E_SCHEDULE_SKIPPED',
            'message': reason,
            'scheduled_for': started_at.isoformat(),
        }
        run = PluginRunModel(
            run_id=run_id,
            package_id=package.id,
            version_id=version.id,
            instance_id=instance.id,
            trigger_type='schedule',
            environment=settings.environment,
            status='SKIPPED',
            attempt=1,
            inputs_json=json.dumps({}, ensure_ascii=False, sort_keys=True),
            outputs_json=json.dumps({}, ensure_ascii=False, sort_keys=True),
            metrics_json=json.dumps({
                'scheduler_backend': 'rust_daemon',
                'executor_backend': 'not_run',
                'scheduled_for': started_at.isoformat(),
            }, ensure_ascii=False, sort_keys=True),
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
                source='scheduler',
                level='WARN',
                message=reason,
                created_at=created_at,
            )
        )
        session.add(
            AuditEventModel(
                event_type='plugin.run.skipped',
                actor='local-dev',
                target_type='plugin_run',
                target_id=run_id,
                details_json=json.dumps(
                    {
                        'status': 'SKIPPED',
                        'instance_id': instance.id,
                        'scheduled_for': started_at.isoformat(),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                created_at=created_at,
            )
        )
        session.commit()


def _next_fixed_rate_time(
    *,
    scheduled_for: datetime,
    finished_at: datetime,
    interval_sec: int,
) -> datetime:
    scheduled_for = _as_db_time(scheduled_for)
    finished_at = _as_db_time(finished_at)
    interval = timedelta(seconds=max(5, int(interval_sec or 30)))
    next_time = scheduled_for
    while next_time <= finished_at:
        next_time += interval
    return next_time


def _align_to_interval_boundary(reference: datetime, interval_sec: int) -> datetime:
    reference = _as_db_time(reference)
    interval = timedelta(seconds=max(5, int(interval_sec or 30)))
    epoch = datetime(1970, 1, 1)
    elapsed = max(0, int((reference - epoch).total_seconds()))
    step = int(interval.total_seconds())
    next_elapsed = (elapsed // step + 1) * step
    return epoch + timedelta(seconds=next_elapsed)


def _suggest_poll_interval_ms(*, items: list[dict[str, Any]], next_due_in_ms: int | None) -> int:
    if items:
        return max(50, int(settings.scheduler.daemon_tick_interval_ms))
    idle_min = max(100, int(settings.scheduler.daemon_idle_min_interval_ms))
    idle_max = max(idle_min, int(settings.scheduler.daemon_idle_max_interval_ms))
    if next_due_in_ms is None:
        return idle_max
    if next_due_in_ms <= idle_min:
        return idle_min
    return min(idle_max, max(idle_min, next_due_in_ms))


def _db_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _as_db_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)
