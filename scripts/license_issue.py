#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def canonical_json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def main() -> int:
    parser = argparse.ArgumentParser(description='Issue offline license file')
    parser.add_argument('--private-key-json', required=True)
    parser.add_argument('--payload-json', required=True)
    parser.add_argument('--license-id', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()

    key_doc = json.loads(Path(args.private_key_json).read_text(encoding='utf-8'))
    payload = json.loads(Path(args.payload_json).read_text(encoding='utf-8'))
    private_key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(key_doc['private_key'].encode('ascii')))
    signature = base64.b64encode(private_key.sign(canonical_json_bytes(payload))).decode('ascii')
    envelope = {
        'schema_version': 1,
        'license_id': args.license_id,
        'alg': 'Ed25519',
        'kid': key_doc['kid'],
        'payload': payload,
        'signature': signature,
    }
    Path(args.out).write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
