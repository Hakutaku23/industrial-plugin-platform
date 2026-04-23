from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any

from platform_api.core.config import settings
from platform_api.services.license_crypto import (
    LicenseDecodeError,
    decode_license_text,
    load_public_key_registry,
    verify_payload_signature,
)
from platform_api.services.license_fingerprint import collect_fingerprint
from platform_api.services.license_models import LicenseSnapshot, LicenseStateRecord, LicenseStatus
from platform_api.services.license_state import detect_rollback, load_state, save_state


class LicenseManager:
    def __init__(self) -> None:
        self._lock = Lock()
        self._cached_snapshot: LicenseSnapshot | None = None
        self._cached_at: datetime | None = None

    @property
    def storage_dir(self) -> Path:
        return settings.license.storage_dir

    @property
    def license_file_path(self) -> Path:
        return self.storage_dir / settings.license.license_file_name

    @property
    def state_file_path(self) -> Path:
        return self.storage_dir / settings.license.state_file_name

    @property
    def installation_id_path(self) -> Path:
        return self.storage_dir / settings.license.installation_id_file_name

    @property
    def public_keys_file_path(self) -> Path:
        return settings.license.public_keys_file

    def initialize(self) -> None:
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def fingerprint_record(self):
        self.initialize()
        return collect_fingerprint(
            installation_id_path=self.installation_id_path,
            machine_id_paths=[Path(path) for path in settings.license.machine_id_paths],
            hostname_paths=[Path(path) for path in settings.license.hostname_paths],
        )

    def fingerprint_payload(self) -> dict[str, Any]:
        fp = self.fingerprint_record()
        return {
            'installation_id': fp.installation_id,
            'machine_id': fp.machine_id,
            'hostname': fp.hostname,
            'deployment_fingerprint': fp.fingerprint,
            'generated_at': fp.generated_at,
        }

    def get_snapshot(self, *, force_refresh: bool = False) -> LicenseSnapshot:
        with self._lock:
            if not force_refresh and self._cached_snapshot is not None and self._cached_at is not None:
                age = (datetime.now(UTC) - self._cached_at).total_seconds()
                if age < max(1, settings.license.cache_ttl_sec):
                    return self._cached_snapshot
            snapshot = self._build_snapshot()
            self._cached_snapshot = snapshot
            self._cached_at = datetime.now(UTC)
            return snapshot

    def save_license_text(self, content: str) -> LicenseSnapshot:
        self.initialize()
        self.license_file_path.write_text(content, encoding='utf-8')
        return self.get_snapshot(force_refresh=True)

    def _build_snapshot(self) -> LicenseSnapshot:
        self.initialize()
        fingerprint = self.fingerprint_record()
        state = load_state(self.state_file_path)
        now = datetime.now(UTC)

        if detect_rollback(previous_utc_iso=state.last_seen_time_utc, current_utc=now):
            snapshot = LicenseSnapshot(
                status=LicenseStatus.ROLLBACK_SUSPECTED,
                valid=False,
                readonly_mode=True,
                message='System clock rollback suspected',
                license_file_path=str(self.license_file_path),
                public_keys_file_path=str(self.public_keys_file_path),
                fingerprint=fingerprint.fingerprint,
                installation_id=fingerprint.installation_id,
            )
            self._persist_state(snapshot=snapshot, now=now)
            return snapshot

        if not settings.license.enabled:
            snapshot = LicenseSnapshot(
                status=LicenseStatus.VALID,
                valid=True,
                readonly_mode=False,
                message='License system disabled by configuration',
                license_file_path=str(self.license_file_path),
                public_keys_file_path=str(self.public_keys_file_path),
                fingerprint=fingerprint.fingerprint,
                installation_id=fingerprint.installation_id,
                grant_mode='perpetual',
            )
            self._persist_state(snapshot=snapshot, now=now)
            return snapshot

        if not self.license_file_path.exists():
            snapshot = LicenseSnapshot(
                status=LicenseStatus.MISSING,
                valid=False,
                readonly_mode=True,
                message='license.lic not found',
                license_file_path=str(self.license_file_path),
                public_keys_file_path=str(self.public_keys_file_path),
                fingerprint=fingerprint.fingerprint,
                installation_id=fingerprint.installation_id,
            )
            self._persist_state(snapshot=snapshot, now=now)
            return snapshot

        try:
            registry = load_public_key_registry(self.public_keys_file_path)
        except Exception as exc:  # noqa: BLE001
            snapshot = LicenseSnapshot(
                status=LicenseStatus.CONFIG_ERROR,
                valid=False,
                readonly_mode=True,
                message=f'Public key registry load failed: {exc}',
                license_file_path=str(self.license_file_path),
                public_keys_file_path=str(self.public_keys_file_path),
                fingerprint=fingerprint.fingerprint,
                installation_id=fingerprint.installation_id,
            )
            self._persist_state(snapshot=snapshot, now=now)
            return snapshot

        try:
            envelope = decode_license_text(self.license_file_path.read_text(encoding='utf-8'))
        except LicenseDecodeError as exc:
            snapshot = LicenseSnapshot(
                status=LicenseStatus.INVALID_FORMAT,
                valid=False,
                readonly_mode=True,
                message=str(exc),
                license_file_path=str(self.license_file_path),
                public_keys_file_path=str(self.public_keys_file_path),
                fingerprint=fingerprint.fingerprint,
                installation_id=fingerprint.installation_id,
            )
            self._persist_state(snapshot=snapshot, now=now)
            return snapshot

        public_key_pem = registry.get(envelope.key_id)
        if not public_key_pem:
            snapshot = LicenseSnapshot(
                status=LicenseStatus.UNKNOWN_ISSUER,
                valid=False,
                readonly_mode=True,
                message=f'Unknown issuer key: {envelope.key_id}',
                license_file_path=str(self.license_file_path),
                public_keys_file_path=str(self.public_keys_file_path),
                fingerprint=fingerprint.fingerprint,
                installation_id=fingerprint.installation_id,
                key_id=envelope.key_id,
            )
            self._persist_state(snapshot=snapshot, now=now)
            return snapshot

        try:
            verify_payload_signature(
                envelope.payload.model_dump(mode='json'),
                envelope.signature,
                public_key_pem,
            )
        except Exception as exc:  # noqa: BLE001
            snapshot = LicenseSnapshot(
                status=LicenseStatus.INVALID_SIGNATURE,
                valid=False,
                readonly_mode=True,
                message=str(exc),
                license_file_path=str(self.license_file_path),
                public_keys_file_path=str(self.public_keys_file_path),
                fingerprint=fingerprint.fingerprint,
                installation_id=fingerprint.installation_id,
                key_id=envelope.key_id,
            )
            self._persist_state(snapshot=snapshot, now=now)
            return snapshot

        payload = envelope.payload
        if payload.deployment_fingerprint != fingerprint.fingerprint:
            snapshot = LicenseSnapshot(
                status=LicenseStatus.FINGERPRINT_MISMATCH,
                valid=False,
                readonly_mode=True,
                message='Deployment fingerprint mismatch',
                license_file_path=str(self.license_file_path),
                public_keys_file_path=str(self.public_keys_file_path),
                fingerprint=fingerprint.fingerprint,
                installation_id=fingerprint.installation_id,
                issuer=payload.issuer,
                key_id=envelope.key_id,
                license_id=payload.license_id,
                customer_name=payload.customer_name,
                grant_mode=payload.grant.mode,
                issued_at=payload.issued_at,
                not_before=payload.grant.not_before,
                not_after=payload.grant.not_after,
                entitlements=payload.grant.model_dump(),
            )
            self._persist_state(snapshot=snapshot, now=now)
            return snapshot

        status = LicenseStatus.VALID
        valid = True
        readonly_mode = False
        message = 'License valid'
        not_before = _parse_utc(payload.grant.not_before)
        not_after = _parse_utc(payload.grant.not_after)

        if not_before and now < not_before:
            status = LicenseStatus.NOT_YET_VALID
            valid = False
            readonly_mode = True
            message = 'License not yet valid'
        elif payload.grant.mode.lower() == 'term' and not_after and now > not_after:
            status = LicenseStatus.EXPIRED
            valid = False
            readonly_mode = True
            message = 'License expired'

        snapshot = LicenseSnapshot(
            status=status,
            valid=valid,
            readonly_mode=readonly_mode,
            message=message,
            license_file_path=str(self.license_file_path),
            public_keys_file_path=str(self.public_keys_file_path),
            fingerprint=fingerprint.fingerprint,
            installation_id=fingerprint.installation_id,
            issuer=payload.issuer,
            key_id=envelope.key_id,
            license_id=payload.license_id,
            customer_name=payload.customer_name,
            grant_mode=payload.grant.mode,
            issued_at=payload.issued_at,
            not_before=payload.grant.not_before,
            not_after=payload.grant.not_after,
            entitlements=payload.grant.model_dump(),
        )
        self._persist_state(snapshot=snapshot, now=now)
        return snapshot

    def _persist_state(self, *, snapshot: LicenseSnapshot, now: datetime) -> None:
        save_state(
            self.state_file_path,
            LicenseStateRecord(
                last_validated_at=now.isoformat(),
                last_seen_time_utc=now.isoformat(),
                last_status=snapshot.status.value,
                last_license_id=snapshot.license_id,
                last_fingerprint=snapshot.fingerprint,
            ),
        )


def _parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


license_manager = LicenseManager()
