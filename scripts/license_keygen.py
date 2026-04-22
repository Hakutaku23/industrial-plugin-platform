#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main() -> int:
    parser = argparse.ArgumentParser(description='Generate Ed25519 key pair for offline license issuing')
    parser.add_argument('--out-dir', required=True)
    parser.add_argument('--kid', default='ed25519-2026-main')
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    priv = base64.b64encode(private_key.private_bytes_raw()).decode('ascii')
    pub = base64.b64encode(public_key.public_bytes_raw()).decode('ascii')

    (out_dir / 'issuer_private_key.json').write_text(json.dumps({'kid': args.kid, 'alg': 'Ed25519', 'private_key': priv}, indent=2), encoding='utf-8')
    (out_dir / 'license_public_keys.json').write_text(json.dumps({'schema_version': 1, 'keys': [{'kid': args.kid, 'alg': 'Ed25519', 'public_key': pub, 'status': 'active'}]}, indent=2), encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
