from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from platform_api.core.config import settings
from platform_api.services.license_models import LicenseStateRecord, TimeRollbackEvent


def _license_dir() -> Path:
    root = os.getenv('PLATFORM_LICENSE_DIR')
    if root:
        return Path(root).resolve()
    return (settings.project_root / 'var/license').resolve()


def state_file_path() -> Path:
    return Path(os.getenv('PLATFORM_LICENSE_STATE_FILE', str(_license_dir() / 'state.json')))


def load_state_record() -> LicenseStateRecord:
    path = state_file_path()
    if not path.exists():
        return LicenseStateRecord()
    return LicenseStateRecord.model_validate(json.loads(path.read_text(encoding='utf-8')))


def save_state_record(record: LicenseStateRecord) -> None:
    path = state_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(record.model_dump_json(indent=2), encoding='utf-8')


def detect_time_rollback(*, record: LicenseStateRecord, tolerance_sec: int = 600) -> tuple[bool, LicenseStateRecord]:
    now = datetime.now(UTC)
    max_seen = datetime.fromisoformat(record.max_seen_wallclock.replace('Z', '+00:00')) if record.max_seen_wallclock else None
    if max_seen is not None and (now.timestamp() + tolerance_sec) < max_seen.timestamp():
        delta_sec = int(max_seen.timestamp() - now.timestamp())
        event = TimeRollbackEvent(
            detected_at=now.isoformat(),
            wallclock_now=now.isoformat(),
            max_seen_wallclock=max_seen.isoformat(),
            delta_sec=delta_sec,
        )
        record.time_rollback_events.append(event)
        return True, record
    if max_seen is None or now > max_seen:
        record.max_seen_wallclock = now.isoformat()
    return False, record
