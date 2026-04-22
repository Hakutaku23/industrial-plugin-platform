from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query

from platform_api.core.config import settings
from platform_api.services.scheduler_dispatch import (
    claim_due_instance,
    complete_due_instance,
    execute_claimed_instance,
    get_due_snapshot,
)

router = APIRouter(prefix='/api/v1/internal/scheduler', tags=['internal-scheduler'])


def _check_internal_token(token: str | None) -> None:
    expected = settings.scheduler.internal_token
    if not token or token != expected:
        raise HTTPException(status_code=401, detail='invalid internal scheduler token')


@router.get('/due')
def list_due_instances(
    limit: int = Query(default=50, ge=1, le=200),
    worker_id: str | None = Query(default=None),
    x_ipp_internal_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_internal_token(x_ipp_internal_token)
    return get_due_snapshot(limit=limit, worker_id=worker_id)


@router.post('/claim')
def claim_instance(
    payload: dict[str, Any],
    x_ipp_internal_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_internal_token(x_ipp_internal_token)
    instance_id = int(payload['instance_id'])
    scheduled_for = datetime.fromisoformat(str(payload['scheduled_for']))
    worker_id = str(payload.get('worker_id', 'rust-scheduler'))
    return claim_due_instance(
        instance_id=instance_id,
        scheduled_for=scheduled_for,
        worker_id=worker_id,
    )


@router.post('/execute')
def execute_instance(
    payload: dict[str, Any],
    x_ipp_internal_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_internal_token(x_ipp_internal_token)
    instance_id = int(payload['instance_id'])
    worker_id = str(payload.get('worker_id', 'rust-scheduler'))
    scheduled_for = datetime.fromisoformat(str(payload['scheduled_for'])) if payload.get('scheduled_for') else None
    claimed_at = datetime.fromisoformat(str(payload['claimed_at'])) if payload.get('claimed_at') else None
    return execute_claimed_instance(
        instance_id=instance_id,
        worker_id=worker_id,
        scheduled_for=scheduled_for,
        claimed_at=claimed_at,
    )


@router.post('/complete')
def complete_instance(
    payload: dict[str, Any],
    x_ipp_internal_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_internal_token(x_ipp_internal_token)
    return complete_due_instance(
        instance_id=int(payload['instance_id']),
        lease_key=str(payload['lease_key']),
        lease_token=str(payload['lease_token']),
        worker_id=str(payload.get('worker_id', 'rust-scheduler')),
    )
