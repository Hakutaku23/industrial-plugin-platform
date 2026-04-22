from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from platform_api.services.license_crypto import load_public_keys, verify_ed25519_signature
from platform_api.services.license_fingerprint import deployment_fingerprint, export_fingerprint_payload
from platform_api.services.license_models import LicenseEnvelope, LicenseStateRecord, LicenseStatus
from platform_api.services.license_state import detect_time_rollback, load_state_record, save_state_record


@dataclass
class LicenseSnapshot:
    status: str
    license_id: str | None
    readonly_mode: bool
    matched: bool
    payload: dict[str, Any]
    current_fingerprint: str
    licensed_fingerprint: str | None
    last_verified_at: str | None
    reason: str = ''


class LicenseManager:
    def __init__(self) -> None:
        self._snapshot = LicenseSnapshot(
            status=LicenseStatus.LICENSE_NOT_FOUND,
            license_id=None,
            readonly_mode=True,
            matched=False,
            payload={},
            current_fingerprint=deployment_fingerprint(),
            licensed_fingerprint=None,
            last_verified_at=None,
            reason='license not loaded',
        )

    def _license_file_path(self) -> Path:
        default_root = os.getenv('PLATFORM_LICENSE_DIR')
        if default_root:
            default_path = Path(default_root).resolve() / 'license.ipp.json'
        else:
            from platform_api.core.config import settings
            default_path = (settings.project_root / 'var/license/license.ipp.json').resolve()
        return Path(os.getenv('PLATFORM_LICENSE_FILE', str(default_path)))

    def _public_keys_path(self) -> Path:
        from platform_api.core.config import settings
        default_path = (settings.project_root / 'config/license_public_keys.json').resolve()
        return Path(os.getenv('PLATFORM_LICENSE_PUBLIC_KEYS_FILE', str(default_path)))

    def initialize(self) -> None:
        self.refresh()

    def refresh(self) -> LicenseSnapshot:
        record = load_state_record()
        rollback, record = detect_time_rollback(record=record)
        if rollback:
            self._snapshot = LicenseSnapshot(
                status=LicenseStatus.TIME_ROLLBACK_SUSPECTED,
                license_id=record.license_id,
                readonly_mode=True,
                matched=False,
                payload={},
                current_fingerprint=deployment_fingerprint(),
                licensed_fingerprint=record.last_deployment_fingerprint,
                last_verified_at=datetime.now(UTC).isoformat(),
                reason='time rollback suspected',
            )
            record.last_status = self._snapshot.status
            record.last_verified_at = self._snapshot.last_verified_at
            save_state_record(record)
            return self._snapshot

        license_path = self._license_file_path()
        if not license_path.exists():
            self._snapshot = LicenseSnapshot(
                status=LicenseStatus.LICENSE_NOT_FOUND,
                license_id=None,
                readonly_mode=True,
                matched=False,
                payload={},
                current_fingerprint=deployment_fingerprint(),
                licensed_fingerprint=None,
                last_verified_at=datetime.now(UTC).isoformat(),
                reason='license file not found',
            )
            record.last_status = self._snapshot.status
            record.last_verified_at = self._snapshot.last_verified_at
            save_state_record(record)
            return self._snapshot

        try:
            envelope = LicenseEnvelope.model_validate(json.loads(license_path.read_text(encoding='utf-8')))
        except Exception as exc:
            self._snapshot = LicenseSnapshot(
                status=LicenseStatus.INVALID_SCHEMA,
                license_id=None,
                readonly_mode=True,
                matched=False,
                payload={},
                current_fingerprint=deployment_fingerprint(),
                licensed_fingerprint=None,
                last_verified_at=datetime.now(UTC).isoformat(),
                reason=str(exc),
            )
            record.last_status = self._snapshot.status
            record.last_verified_at = self._snapshot.last_verified_at
            save_state_record(record)
            return self._snapshot

        public_keys = load_public_keys(self._public_keys_path())
        public_key = public_keys.get(envelope.kid)
        if public_key is None or not verify_ed25519_signature(public_key=public_key, payload=envelope.payload, signature_b64=envelope.signature):
            self._snapshot = LicenseSnapshot(
                status=LicenseStatus.INVALID_SIGNATURE,
                license_id=envelope.license_id,
                readonly_mode=True,
                matched=False,
                payload=envelope.payload,
                current_fingerprint=deployment_fingerprint(),
                licensed_fingerprint=((envelope.payload.get('subject') or {}).get('deployment_fingerprint')),
                last_verified_at=datetime.now(UTC).isoformat(),
                reason='signature invalid or key not found',
            )
            record.license_id = envelope.license_id
            record.last_status = self._snapshot.status
            record.last_verified_at = self._snapshot.last_verified_at
            save_state_record(record)
            return self._snapshot

        payload = envelope.payload
        product_code = (((payload.get('product') or {}).get('code')) or '').strip()
        expected_product_code = os.getenv('PLATFORM_LICENSE_PRODUCT_CODE', 'industrial-plugin-platform')
        current_fp = deployment_fingerprint()
        licensed_fp = ((payload.get('subject') or {}).get('deployment_fingerprint'))
        now = datetime.now(UTC)

        status = LicenseStatus.VALID
        reason = ''
        readonly = False
        matched = bool(licensed_fp and licensed_fp == current_fp)

        if product_code != expected_product_code:
            status = LicenseStatus.INVALID_PRODUCT
            readonly = True
            reason = 'product code mismatch'
        elif not matched:
            status = LicenseStatus.INVALID_SUBJECT
            readonly = True
            reason = 'deployment fingerprint mismatch'
        else:
            validity = payload.get('validity') or {}
            not_before = _parse_dt(validity.get('not_before'))
            expire_at = _parse_dt(validity.get('expire_at'))
            grace_days = int(validity.get('grace_days') or 0)
            if not_before and now < not_before:
                status = LicenseStatus.NOT_YET_VALID
                readonly = True
                reason = 'license not yet valid'
            elif expire_at and now > expire_at:
                if now <= expire_at + timedelta(days=grace_days):
                    status = LicenseStatus.VALID_GRACE
                    readonly = True
                    reason = 'license expired but grace period active'
                else:
                    status = LicenseStatus.EXPIRED
                    readonly = True
                    reason = 'license expired'

        snapshot = LicenseSnapshot(
            status=status,
            license_id=envelope.license_id,
            readonly_mode=readonly,
            matched=matched,
            payload=payload,
            current_fingerprint=current_fp,
            licensed_fingerprint=licensed_fp,
            last_verified_at=now.isoformat(),
            reason=reason,
        )
        self._snapshot = snapshot

        record.license_id = envelope.license_id
        record.last_status = snapshot.status
        record.last_verified_at = snapshot.last_verified_at
        record.last_deployment_fingerprint = current_fp
        record.last_payload_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode('utf-8')).hexdigest()
        save_state_record(record)
        return snapshot

    def snapshot(self) -> dict[str, Any]:
        snap = self._snapshot
        payload = snap.payload
        validity = payload.get('validity') or {}
        return {
            'status': snap.status,
            'license_id': snap.license_id,
            'edition': ((payload.get('product') or {}).get('edition')),
            'customer': payload.get('customer') or {},
            'validity': validity,
            'subject': {
                'bind_mode': ((payload.get('subject') or {}).get('bind_mode')),
                'current_fingerprint': snap.current_fingerprint,
                'licensed_fingerprint': snap.licensed_fingerprint,
                'matched': snap.matched,
            },
            'entitlements': payload.get('entitlements') or {},
            'quotas': payload.get('quotas') or {},
            'policy': payload.get('policy') or {},
            'last_verified_at': snap.last_verified_at,
            'readonly_mode': snap.readonly_mode,
            'reason': snap.reason,
        }

    def export_fingerprint(self) -> dict[str, Any]:
        return export_fingerprint_payload()

    def replace_license(self, content: bytes) -> dict[str, Any]:
        path = self._license_file_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        self.refresh()
        return self.snapshot()

    @property
    def current_status(self) -> str:
        return self._snapshot.status

    @property
    def current_payload(self) -> dict[str, Any]:
        return self._snapshot.payload


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).replace('Z', '+00:00')
    try:
        return datetime.fromisoformat(text).astimezone(UTC)
    except Exception:
        return None


_LICENSE_MANAGER: LicenseManager | None = None


def get_license_manager() -> LicenseManager:
    global _LICENSE_MANAGER
    if _LICENSE_MANAGER is None:
        _LICENSE_MANAGER = LicenseManager()
    return _LICENSE_MANAGER
