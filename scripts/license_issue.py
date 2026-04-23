#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import sys
import os
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'apps', 'api'))
# print(sys.path)
from platform_api.services.license_crypto import encode_license_text, sign_payload


def _utc_text(value: str | None) -> str | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    else:
        parsed = parsed.astimezone(UTC)
    return parsed.isoformat()


def main() -> None:
    parser = argparse.ArgumentParser(description='Issue IPP license.lic from issuer private key')
    parser.add_argument('--key-id', required=True)
    parser.add_argument('--private-key', required=True)
    parser.add_argument('--customer-name', required=True)
    parser.add_argument('--fingerprint-json', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--grant-mode', choices=['perpetual', 'term'], required=True)
    parser.add_argument('--not-before', required=False)
    parser.add_argument('--not-after', required=False)
    parser.add_argument('--allow-manual-run', default='true')
    parser.add_argument('--allow-schedule', default='true')
    parser.add_argument('--allow-real-writeback', default='true')
    parser.add_argument('--max-instances', type=int)
    parser.add_argument('--max-packages', type=int)
    parser.add_argument('--max-data-sources', type=int)
    parser.add_argument('--max-concurrent-runs', type=int)
    parser.add_argument('--issuer', default='IPP Issuer')
    args = parser.parse_args()

    fingerprint_payload = json.loads(Path(args.fingerprint_json).read_text(encoding='utf-8'))
    deployment_fingerprint = str(fingerprint_payload['deployment_fingerprint'])

    payload = {
        'schema': 'ipp-license/v1',
        'license_id': f'lic-{uuid.uuid4().hex}',
        'issuer': args.issuer,
        'customer_name': args.customer_name,
        'issued_at': datetime.now(UTC).isoformat(),
        'deployment_fingerprint': deployment_fingerprint,
        'grant': {
            'mode': args.grant_mode,
            'not_before': _utc_text(args.not_before),
            'not_after': None if args.grant_mode == 'perpetual' else _utc_text(args.not_after),
            'allow_manual_run': str(args.allow_manual_run).lower() in {'1', 'true', 'yes', 'on'},
            'allow_schedule': str(args.allow_schedule).lower() in {'1', 'true', 'yes', 'on'},
            'allow_real_writeback': str(args.allow_real_writeback).lower() in {'1', 'true', 'yes', 'on'},
            'max_instances': args.max_instances,
            'max_packages': args.max_packages,
            'max_data_sources': args.max_data_sources,
            'max_concurrent_runs': args.max_concurrent_runs,
        },
        'metadata': {
            'installation_id': fingerprint_payload.get('installation_id'),
            'hostname': fingerprint_payload.get('hostname'),
            'machine_id': fingerprint_payload.get('machine_id'),
        },
    }

    private_key_pem = Path(args.private_key).read_text(encoding='utf-8')
    signature = sign_payload(payload, private_key_pem)
    envelope = {'payload': payload, 'key_id': args.key_id, 'algorithm': 'Ed25519', 'signature': signature}
    out_path = Path(args.output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(encode_license_text(envelope), encoding='utf-8')
    print(f'issued license: {out_path}')


if __name__ == '__main__':
    main()
