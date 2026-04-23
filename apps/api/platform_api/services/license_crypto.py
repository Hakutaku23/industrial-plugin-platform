from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from platform_api.services.license_models import LicenseEnvelopeModel

BEGIN_MARKER = '-----BEGIN IPP LICENSE-----'
END_MARKER = '-----END IPP LICENSE-----'


class LicenseDecodeError(ValueError):
    pass


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def encode_license_text(envelope: dict[str, Any]) -> str:
    raw = json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    encoded = base64.b64encode(raw).decode('ascii')
    wrapped = '\n'.join(encoded[i:i + 64] for i in range(0, len(encoded), 64))
    return f'{BEGIN_MARKER}\n{wrapped}\n{END_MARKER}\n'


def decode_license_text(text: str) -> LicenseEnvelopeModel:
    stripped = text.strip()
    if not stripped.startswith(BEGIN_MARKER) or END_MARKER not in stripped:
        raise LicenseDecodeError('license.lic format invalid: missing armor markers')
    body = stripped[len(BEGIN_MARKER): stripped.index(END_MARKER)].strip()
    try:
        raw = base64.b64decode(''.join(body.splitlines()).encode('ascii'))
        parsed = json.loads(raw.decode('utf-8'))
    except Exception as exc:  # noqa: BLE001
        raise LicenseDecodeError(f'license.lic format invalid: {exc}') from exc
    return LicenseEnvelopeModel.model_validate(parsed)


def sign_payload(payload: dict[str, Any], private_key_pem: str) -> str:
    key = serialization.load_pem_private_key(private_key_pem.encode('utf-8'), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError('private key must be Ed25519')
    signature = key.sign(canonical_json_bytes(payload))
    return base64.b64encode(signature).decode('ascii')


def verify_payload_signature(payload: dict[str, Any], signature_b64: str, public_key_pem: str) -> None:
    key = serialization.load_pem_public_key(public_key_pem.encode('utf-8'))
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError('public key must be Ed25519')
    signature = base64.b64decode(signature_b64.encode('ascii'))
    try:
        key.verify(signature, canonical_json_bytes(payload))
    except InvalidSignature as exc:
        raise LicenseDecodeError('license signature verification failed') from exc


def load_public_key_registry(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    parsed = json.loads(path.read_text(encoding='utf-8'))
    if isinstance(parsed, dict) and isinstance(parsed.get('keys'), list):
        registry: dict[str, str] = {}
        for item in parsed['keys']:
            if not isinstance(item, dict):
                continue
            key_id = str(item.get('key_id', '')).strip()
            public_key_pem = str(item.get('public_key_pem', '')).strip()
            if key_id and public_key_pem:
                registry[key_id] = public_key_pem
        return registry
    raise ValueError(f'public key registry invalid: {path}')
