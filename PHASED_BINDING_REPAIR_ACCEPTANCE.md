# Complete behavior binding

Prepared sources bind execution/index/scoring Python packages, prompts, parser queries, migrations, metrics and dependency declarations. Plans additionally bind the local cohort file. Additions, deletions, content changes, symlinks and partial legacy maps fail closed. Interpreter and installed dependency inventory are pinned. This is local reproducibility, not protection against malicious filesystem administrators. Private source/plan/authorization bindings are not distributed.

## Portable verification

~~~sh
LOCAGENT_ALLOW_PAID=0 LITELLM_LOCAL_MODEL_COST_MAP=True HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 \
  .venv/bin/python -B -m unittest discover -s tests -p test_engine_binding.py -v
~~~

These tests use synthetic/offline data. Private original evidence is retained locally,
not required by these tests and not included in Git. Final real-run results and
limitations are in [NEW20_REAL_EVALUATION.md](NEW20_REAL_EVALUATION.md).
