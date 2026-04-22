from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class LicenseStatus(StrEnum):
    VALID = 'VALID'
    VALID_GRACE = 'VALID_GRACE'
    INVALID_SIGNATURE = 'INVALID_SIGNATURE'
    INVALID_SCHEMA = 'INVALID_SCHEMA'
    INVALID_PRODUCT = 'INVALID_PRODUCT'
    INVALID_VERSION_RANGE = 'INVALID_VERSION_RANGE'
    INVALID_SUBJECT = 'INVALID_SUBJECT'
    NOT_YET_VALID = 'NOT_YET_VALID'
    EXPIRED = 'EXPIRED'
    TIME_ROLLBACK_SUSPECTED = 'TIME_ROLLBACK_SUSPECTED'
    LICENSE_NOT_FOUND = 'LICENSE_NOT_FOUND'
    INTERNAL_ERROR = 'INTERNAL_ERROR'


class LicenseEnvelope(BaseModel):
    schema_version: int = 1
    license_id: str
    alg: str
    kid: str
    payload: dict[str, Any]
    signature: str


class PublicKeyItem(BaseModel):
    kid: str
    alg: str
    public_key: str
    status: str = 'active'


class PublicKeySet(BaseModel):
    schema_version: int = 1
    keys: list[PublicKeyItem] = Field(default_factory=list)


class TimeRollbackEvent(BaseModel):
    detected_at: str
    wallclock_now: str
    max_seen_wallclock: str
    delta_sec: int


class LicenseStateRecord(BaseModel):
    schema_version: int = 1
    license_id: str | None = None
    last_status: str = LicenseStatus.LICENSE_NOT_FOUND
    last_verified_at: str | None = None
    max_seen_wallclock: str | None = None
    last_deployment_fingerprint: str | None = None
    last_payload_hash: str | None = None
    time_rollback_events: list[TimeRollbackEvent] = Field(default_factory=list)
