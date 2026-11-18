# Checkpoint quality-claim gate

Quality reporting requires explicit experiment completion, terminal arms, ordered durable checkpoints, no active run and no terminal infrastructure fault. A final result file alone is insufficient. Partial live metrics are progress; offline/simulation metrics never establish efficacy. Tests inject pre-checkpoint and ledger/owner write failures. quality_claim_allowed means a complete real experiment can be reported, not that quality improved.

## Portable verification

~~~sh
LOCAGENT_ALLOW_PAID=0 LITELLM_LOCAL_MODEL_COST_MAP=True HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 \
  .venv/bin/python -B -m unittest discover -s tests -p test_quality_checkpoint.py -v
~~~

These tests use synthetic/offline data. Private original evidence is retained locally,
not required by these tests and not included in Git. Final real-run results and
limitations are in [NEW20_REAL_EVALUATION.md](NEW20_REAL_EVALUATION.md).
