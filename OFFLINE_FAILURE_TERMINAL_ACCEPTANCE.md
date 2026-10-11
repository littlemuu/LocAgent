# Failure terminal and interruption boundary

Malformed/non-object tool arguments have a stable invalid_response classification. Other execution, storage, transport and ownership faults halt the batch. Explicit audit does not infer safe exit from a dead parent or free lock. Completed-result time, recorded attempts and phase wall time are separate; unknown durations remain unknown. Synthetic response/process regressions do not establish live recovery efficacy.

## Portable verification

~~~sh
LOCAGENT_ALLOW_PAID=0 LITELLM_LOCAL_MODEL_COST_MAP=True HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 \
  .venv/bin/python -B -m unittest discover -s tests -p test_failure_terminal.py -v
~~~

These tests use synthetic/offline data. Private original evidence is retained locally,
not required by these tests and not included in Git. Final real-run results and
limitations are in [NEW20_REAL_EVALUATION.md](NEW20_REAL_EVALUATION.md).
