from __future__ import annotations

from platform_api.services.license_manager import license_manager
from platform_api.services.metadata_store import MetadataStore


class LicenseGuardError(PermissionError):
    pass


def _require_valid_base():
    snapshot = license_manager.get_snapshot()
    if snapshot.valid:
        return snapshot
    raise LicenseGuardError(f'License denied: {snapshot.status.value} - {snapshot.message}')


def ensure_instance_create_allowed(*, store: MetadataStore):
    snapshot = _require_valid_base()
    limit = snapshot.entitlements.get('max_instances')
    if limit is not None and len(store.list_plugin_instances()) >= int(limit):
        raise LicenseGuardError(f'Instance quota exceeded: max_instances={limit}')
    return snapshot


def ensure_package_upload_allowed(*, store: MetadataStore):
    snapshot = _require_valid_base()
    limit = snapshot.entitlements.get('max_packages')
    if limit is not None and len(store.list_plugin_packages()) >= int(limit):
        raise LicenseGuardError(f'Package quota exceeded: max_packages={limit}')
    return snapshot


def ensure_data_source_create_allowed(*, store: MetadataStore):
    snapshot = _require_valid_base()
    limit = snapshot.entitlements.get('max_data_sources')
    if limit is not None and len(store.list_data_sources()) >= int(limit):
        raise LicenseGuardError(f'Data source quota exceeded: max_data_sources={limit}')
    return snapshot


def ensure_manual_run_allowed():
    snapshot = _require_valid_base()
    if not bool(snapshot.entitlements.get('allow_manual_run', True)):
        raise LicenseGuardError('License does not allow manual execution')
    return snapshot


def ensure_schedule_enabled_allowed(*, enabled: bool):
    snapshot = license_manager.get_snapshot()
    if not enabled:
        return snapshot
    if not snapshot.valid:
        raise LicenseGuardError(f'License denied: {snapshot.status.value} - {snapshot.message}')
    if not bool(snapshot.entitlements.get('allow_schedule', True)):
        raise LicenseGuardError('License does not allow schedule enablement')
    return snapshot


def ensure_schedule_dispatch_allowed():
    snapshot = _require_valid_base()
    if not bool(snapshot.entitlements.get('allow_schedule', True)):
        raise LicenseGuardError('License does not allow scheduled dispatch')
    return snapshot


def ensure_writeback_allowed():
    snapshot = _require_valid_base()
    if not bool(snapshot.entitlements.get('allow_real_writeback', True)):
        raise LicenseGuardError('License does not allow real writeback')
    return snapshot
