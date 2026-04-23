#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


import sys
import os
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'apps', 'api'))

from platform_api.services.license_crypto import decode_license_text


def main() -> None:
    parser = argparse.ArgumentParser(description='Decode IPP license.lic into human-readable JSON')
    parser.add_argument('--license', required=True)
    parser.add_argument('--output', required=False)
    args = parser.parse_args()

    envelope = decode_license_text(Path(args.license).read_text(encoding='utf-8'))
    content = json.dumps(envelope.model_dump(mode='json'), ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(content, encoding='utf-8')
        print(f'wrote decoded json: {args.output}')
    else:
        print(content)


if __name__ == '__main__':
    main()
