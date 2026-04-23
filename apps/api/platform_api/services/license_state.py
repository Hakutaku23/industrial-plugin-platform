from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from platform_api.services.license_models import LicenseStateRecord


def load_state(path: Path) -> LicenseStateRecord:
    if not path.exists():
        return LicenseStateRecord()
    try:
        parsed = json.loads(path.read_text(encoding='utf-8'))
        return LicenseStateRecord.model_validate(parsed)
    except Exception:
        return LicenseStateRecord()


def save_state(path: Path, state: LicenseStateRecord) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state.model_dump(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding='utf-8',
    )


def detect_rollback(*, previous_utc_iso: str | None, current_utc: datetime, tolerance_sec: int = 300) -> bool:
    if not previous_utc_iso:
        return False
    try:
        previous = datetime.fromisoformat(previous_utc_iso)
    except ValueError:
        return False
    if previous.tzinfo is None:
        previous = previous.replace(tzinfo=UTC)
    else:
        previous = previous.astimezone(UTC)
    return current_utc + timedelta(seconds=tolerance_sec) < previous
