from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LicenseStatus(StrEnum):
    VALID = 'VALID'
    VALID_GRACE = 'VALID_GRACE'
    MISSING = 'MISSING'
    INVALID_FORMAT = 'INVALID_FORMAT'
    INVALID_SIGNATURE = 'INVALID_SIGNATURE'
    UNKNOWN_ISSUER = 'UNKNOWN_ISSUER'
    FINGERPRINT_MISMATCH = 'FINGERPRINT_MISMATCH'
    NOT_YET_VALID = 'NOT_YET_VALID'
    EXPIRED = 'EXPIRED'
    REVOKED = 'REVOKED'
    ROLLBACK_SUSPECTED = 'ROLLBACK_SUSPECTED'
    IO_ERROR = 'IO_ERROR'
    CONFIG_ERROR = 'CONFIG_ERROR'


class LicenseGrantModel(BaseModel):
    mode: str = 'perpetual'
    not_before: str | None = None
    not_after: str | None = None
    grace_days: int | None = None
    allow_manual_run: bool = True
    allow_schedule: bool = True
    allow_real_writeback: bool = True
    allow_package_upload: bool = True
    allowed_connector_types: list[str] = Field(default_factory=list)
    max_instances: int | None = None
    max_packages: int | None = None
    max_data_sources: int | None = None
    max_concurrent_runs: int | None = None


class LicensePayloadModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    license_schema: str = Field(default='ipp-license/v1', alias='schema')
    license_id: str
    issuer: str
    customer_name: str
    issued_at: str
    deployment_fingerprint: str
    grant: LicenseGrantModel
    metadata: dict[str, Any] = Field(default_factory=dict)


class LicenseEnvelopeModel(BaseModel):
    payload: LicensePayloadModel
    key_id: str
    algorithm: str = 'Ed25519'
    signature: str


class FingerprintRecord(BaseModel):
    installation_id: str
    machine_id: str | None = None
    hostname: str | None = None
    fingerprint: str
    generated_at: str


class LicenseStateRecord(BaseModel):
    last_validated_at: str | None = None
    last_seen_time_utc: str | None = None
    last_status: str | None = None
    last_license_id: str | None = None
    last_fingerprint: str | None = None


class LicenseSnapshot(BaseModel):
    status: LicenseStatus
    valid: bool
    readonly_mode: bool
    message: str
    license_file_path: str | None = None
    public_keys_file_path: str | None = None
    revocations_file_path: str | None = None
    fingerprint: str | None = None
    installation_id: str | None = None
    issuer: str | None = None
    key_id: str | None = None
    license_id: str | None = None
    customer_name: str | None = None
    grant_mode: str | None = None
    issued_at: str | None = None
    not_before: str | None = None
    not_after: str | None = None
    grace_days: int | None = None
    grace_expires_at: str | None = None
    revoked: bool = False
    entitlements: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_perpetual(self) -> bool:
        return (self.grant_mode or '').lower() == 'perpetual'

    @property
    def is_term(self) -> bool:
        return (self.grant_mode or '').lower() == 'term'


def utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()
