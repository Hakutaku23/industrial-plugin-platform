from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any

from platform_api.core.config import settings


def _license_dir() -> Path:
    root = os.getenv('PLATFORM_LICENSE_DIR')
    if root:
        return Path(root).resolve()
    return (settings.project_root / 'var/license').resolve()


def installation_id_path() -> Path:
    return _license_dir() / 'installation_id'


def ensure_installation_id() -> str:
    path = installation_id_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path.read_text(encoding='utf-8').strip()
    value = str(uuid.uuid4())
    path.write_text(value, encoding='utf-8')
    return value


def _read_text_if_exists(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding='utf-8').strip()
    return ''


def subject_input() -> dict[str, Any]:
    machine_id_path = Path(os.getenv('PLATFORM_LICENSE_HOST_MACHINE_ID_FILE', '/host/etc/machine-id'))
    hostname_path = Path(os.getenv('PLATFORM_LICENSE_HOST_HOSTNAME_FILE', '/host/etc/hostname'))
    return {
        'product_code': os.getenv('PLATFORM_LICENSE_PRODUCT_CODE', 'industrial-plugin-platform'),
        'host_machine_id': _read_text_if_exists(machine_id_path),
        'host_hostname': _read_text_if_exists(hostname_path),
        'installation_id': ensure_installation_id(),
        'customer_scope': os.getenv('PLATFORM_LICENSE_CUSTOMER_SCOPE', ''),
    }


def deployment_fingerprint() -> str:
    normalized = json.dumps(subject_input(), ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(normalized).hexdigest()


def export_fingerprint_payload() -> dict[str, Any]:
    subject = subject_input()
    host_machine_id = subject.get('host_machine_id', '')
    masked = host_machine_id[:6] + '***' + host_machine_id[-4:] if len(host_machine_id) >= 10 else host_machine_id
    return {
        'product_code': subject['product_code'],
        'deployment_fingerprint': deployment_fingerprint(),
        'application_time': __import__('datetime').datetime.utcnow().replace(microsecond=0).isoformat() + 'Z',
        'subject_input': {
            'host_machine_id': masked,
            'host_hostname': subject.get('host_hostname', ''),
            'installation_id': subject.get('installation_id', ''),
            'customer_scope': subject.get('customer_scope', ''),
        },
    }
