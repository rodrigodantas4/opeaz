#!/usr/bin/env python3
"""Print seed response IDs as shell exports (bash) or PowerShell $env: assignments."""

import argparse
import json
import sys
from pathlib import Path


def load_seed(path: Path) -> dict:
    with path.open(encoding='utf-8') as fh:
        return json.load(fh)


def build_vars(data: dict) -> dict[str, int]:
    norte = next(p['id'] for p in data['pharmacies'] if 'Norte' in p['name'])
    nodes = data['nodes']
    return {
        'PRIMARY_PHARMACY_ID': data['primary_pharmacy_id'],
        'CPC_GROUPEMENT_ID': data['groupements'][0]['id'],
        'NORTE_PHARMACY_ID': norte,
        'CPC_ROOT_ID': nodes['cpc_root_id'],
        'CONDITIONS_2025_ID': nodes['conditions_2025_id'],
        'CONDITIONS_LEAF_ID': nodes['conditions_leaf_id'],
        'VAT_LEAF_ID': nodes['vat_leaf_id'],
        'MY_DOCUMENTS_ID': nodes['my_documents_id'],
        'FLYER_LEAF_ID': nodes['flyer_leaf_id'],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        'seed_file',
        nargs='?',
        default='seed.json',
        help='Path to POST /test/seed/ JSON response (default: seed.json)',
    )
    parser.add_argument(
        '--shell',
        choices=('bash', 'powershell'),
        default='bash',
        help='Output format (default: bash export statements)',
    )
    args = parser.parse_args()

    path = Path(args.seed_file)
    if not path.is_file():
        print(f'seed file not found: {path}', file=sys.stderr)
        return 1

    pairs = build_vars(load_seed(path))
    if args.shell == 'powershell':
        for key, value in pairs.items():
            print(f'$env:{key} = {value}')
    else:
        for key, value in pairs.items():
            print(f'export {key}={value}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
