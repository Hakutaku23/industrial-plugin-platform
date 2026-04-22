from __future__ import annotations

from fastapi import HTTPException, status

from platform_api.api.common import store
from platform_api.services.license_manager import get_license_manager
from platform_api.services.metadata_store import MetadataStore


class LicenseDeniedError(RuntimeError):
    def __init__(self, code: str, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


READONLY_STATUSES = {
    'VALID_GRACE',
    'INVALID_SIGNATURE',
    'INVALID_SCHEMA',
    'INVALID_PRODUCT',
    'INVALID_VERSION_RANGE',
    'INVALID_SUBJECT',
    'NOT_YET_VALID',
    'EXPIRED',
    'TIME_ROLLBACK_SUSPECTED',
    'LICENSE_NOT_FOUND',
    'INTERNAL_ERROR',
}


def _manager_snapshot() -> dict:
    return get_license_manager().snapshot()


def assert_feature(feature: str) -> None:
    snapshot = _manager_snapshot()
    if snapshot['status'] in READONLY_STATUSES:
        raise LicenseDeniedError('E_LICENSE_FEATURE_DENIED', f'license status does not allow operation: {snapshot["status"]}', {'feature': feature, 'license_status': snapshot['status']})
    entitlements = snapshot.get('entitlements') or {}
    if not entitlements.get(feature, False):
        raise LicenseDeniedError('E_LICENSE_FEATURE_DENIED', f'license does not allow feature: {feature}', {'feature': feature, 'license_status': snapshot['status']})


def assert_quota(quota_name: str, current: int) -> None:
    snapshot = _manager_snapshot()
    quotas = snapshot.get('quotas') or {}
    limit = quotas.get(quota_name)
    if limit is None:
        return
    if int(current) >= int(limit):
        raise LicenseDeniedError('E_LICENSE_QUOTA_EXCEEDED', f'quota exceeded: {quota_name}', {'quota_name': quota_name, 'quota_limit': limit, 'quota_current': current})


def assert_instance_create_allowed(metadata_store: MetadataStore | None = None) -> None:
    assert_feature('allow_instance_create')
    items = (metadata_store or store()).list_plugin_instances()
    assert_quota('max_instances', len(items))


def assert_instance_run_allowed() -> None:
    assert_feature('allow_instance_run')


def assert_schedule_allowed(metadata_store: MetadataStore | None = None, *, enabling: bool = True) -> None:
    if not enabling:
        return
    assert_feature('allow_schedule')
    items = (metadata_store or store()).list_plugin_instances()
    scheduled = len([item for item in items if item.get('schedule_enabled')])
    assert_quota('max_scheduled_instances', scheduled)


def can_real_writeback() -> bool:
    snapshot = _manager_snapshot()
    if snapshot['status'] != 'VALID':
        return False
    entitlements = snapshot.get('entitlements') or {}
    return bool(entitlements.get('allow_real_writeback', False))


def is_scheduler_allowed() -> bool:
    snapshot = _manager_snapshot()
    if snapshot['status'] != 'VALID':
        return False
    return bool((snapshot.get('entitlements') or {}).get('allow_schedule', False))


def to_http_exception(exc: LicenseDeniedError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={'code': exc.code, 'message': str(exc), 'details': exc.details})
