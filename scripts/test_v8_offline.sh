#!/bin/sh
# Offline only; stop immediately on the first failing command. Never retries.
set -eu
PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
SDK_PYTHON=${V8_SDK_PYTHON:-"$PROJECT_ROOT/workspace/.venv-openhands/bin/python"}
RETRIEVAL_PYTHON=${V8_RETRIEVAL_PYTHON:-"$PROJECT_ROOT/legacy/locagent-demo/.venv/bin/python"}
LEGACY_ROOT=${V8_LEGACY_ROOT:-"$PROJECT_ROOT/legacy/locagent-demo"}
if [ "$#" -ne 1 ]; then
    echo 'Usage: scripts/test_v8_offline.sh /absolute/path/to/new-output-directory' >&2
    exit 2
fi
case "$1" in /*) OUTPUT=$1 ;; *) echo 'Output must be absolute' >&2; exit 2 ;; esac
mkdir "$OUTPUT"
export DO_NOT_TRACK=1 LITELLM_LOCAL_MODEL_COST_MAP=True HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 OPENHANDS_SUPPRESS_BANNER=1
cd "$PROJECT_ROOT/workspace"
"$RETRIEVAL_PYTHON" -B -m experiments.sdk_hybrid_v8.offline_checks --suite core --output "$OUTPUT/core" --legacy-root "$LEGACY_ROOT" --retrieval-python "$RETRIEVAL_PYTHON"
"$SDK_PYTHON" -B -m experiments.sdk_hybrid_v8.offline_checks --suite sdk --output "$OUTPUT/sdk" --legacy-root "$LEGACY_ROOT" --retrieval-python "$RETRIEVAL_PYTHON"
"$SDK_PYTHON" -B -m experiments.sdk_hybrid_v8.demo --output "$OUTPUT/demo" --retrieval-python "$RETRIEVAL_PYTHON" > "$OUTPUT/demo.log" 2>&1
"$SDK_PYTHON" -B - "$OUTPUT" <<'PY'
import hashlib, json, sys
from pathlib import Path
out = Path(sys.argv[1])
core, sdk = [json.loads((out / name / 'summary.json').read_text()) for name in ('core', 'sdk')]
demo = json.loads((out / 'demo/acceptance.json').read_text())
run = json.loads((out / 'demo/sdk/result.json').read_text())
assert core['status'] == sdk['status'] == 'passed'
assert core['network_attempts'] == sdk['network_attempts'] == run['network_attempts'] == 0
assert demo['status'] == 'completed' and demo['hybrid_evidence_in_next_request']
files = sorted(Path('experiments/sdk_hybrid_v8').glob('*.py')) + sorted(Path('tests_v8').glob('*.py'))
manifest = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
summary = dict(status='passed', tests=core['tests'] + sdk['tests'], core_tests=core['tests'], sdk_tests=sdk['tests'],
               sdk_demo_completed=True, network_attempts=0, real_llm_requests=0, real_embedding_requests=0,
               cost=0, synthetic_embeddings_only=True, quality_measured=False, source_hashes=manifest)
(out / 'acceptance.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps({k: v for k, v in summary.items() if k != 'source_hashes'}))
PY
