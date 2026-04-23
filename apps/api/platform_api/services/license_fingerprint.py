from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime
from pathlib import Path

from platform_api.services.license_models import FingerprintRecord


def _read_text_if_exists(path: Path) -> str | None:
    try:
        if path.exists():
            text = path.read_text(encoding='utf-8').strip()
            return text or None
    except Exception:
        return None
    return None


def ensure_installation_id(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_text_if_exists(path)
    if existing:
        return existing
    installation_id = secrets.token_hex(16)
    path.write_text(installation_id + '\n', encoding='utf-8')
    return installation_id


def build_fingerprint(*, installation_id: str, machine_id: str | None, hostname: str | None) -> str:
    material = {
        'installation_id': installation_id,
        'machine_id': machine_id or '',
        'hostname': hostname or '',
    }
    raw = '|'.join(f'{key}={material[key]}' for key in sorted(material))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def collect_fingerprint(
    *,
    installation_id_path: Path,
    machine_id_paths: list[Path],
    hostname_paths: list[Path],
) -> FingerprintRecord:
    installation_id = ensure_installation_id(installation_id_path)
    machine_id = next((value for value in (_read_text_if_exists(path) for path in machine_id_paths) if value), None)
    hostname = next((value for value in (_read_text_if_exists(path) for path in hostname_paths) if value), None)
    fingerprint = build_fingerprint(
        installation_id=installation_id,
        machine_id=machine_id,
        hostname=hostname,
    )
    return FingerprintRecord(
        installation_id=installation_id,
        machine_id=machine_id,
        hostname=hostname,
        fingerprint=fingerprint,
        generated_at=datetime.now(UTC).isoformat(),
    )
