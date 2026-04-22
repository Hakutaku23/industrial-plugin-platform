from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from platform_api.services.license_models import PublicKeySet


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def load_public_keys(path: Path) -> dict[str, Ed25519PublicKey]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding='utf-8'))
    keyset = PublicKeySet.model_validate(raw)
    result: dict[str, Ed25519PublicKey] = {}
    for item in keyset.keys:
        if item.status != 'active':
            continue
        result[item.kid] = Ed25519PublicKey.from_public_bytes(base64.b64decode(item.public_key.encode('ascii')))
    return result


def verify_ed25519_signature(*, public_key: Ed25519PublicKey, payload: dict[str, Any], signature_b64: str) -> bool:
    try:
        public_key.verify(base64.b64decode(signature_b64.encode('ascii')), canonical_json_bytes(payload))
        return True
    except Exception:
        return False
