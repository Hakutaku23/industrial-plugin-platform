#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main() -> None:
    parser = argparse.ArgumentParser(description='Generate issuer Ed25519 key pair for IPP licenses')
    parser.add_argument('--key-id', required=True)
    parser.add_argument('--out-dir', required=True)
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode('utf-8')
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode('utf-8')

    private_path = out_dir / f'{args.key_id}.private.pem'
    public_path = out_dir / f'{args.key_id}.public.pem'
    registry_path = out_dir / f'{args.key_id}.public-registry.json'

    private_path.write_text(private_pem, encoding='utf-8')
    public_path.write_text(public_pem, encoding='utf-8')
    registry_path.write_text(json.dumps({'keys': [{'key_id': args.key_id, 'public_key_pem': public_pem}]}, ensure_ascii=False, indent=2), encoding='utf-8')

    print(f'private key  : {private_path}')
    print(f'public key   : {public_path}')
    print(f'registry json: {registry_path}')


if __name__ == '__main__':
    main()
