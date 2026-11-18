"""Read-only CLI. No --execute option and no credential/transport imports."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from locagent_service.bailian_expanded_runner import preview


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=ROOT / 'outputs/bailian-expanded50-20261016/frozen/manifest.json')
    parser.add_argument('--proposed-cap', default='2', help='Proposal only; grants no execution authorization')
    args = parser.parse_args()
    print(json.dumps(preview(args.manifest, ROOT, args.proposed_cap), indent=2))
