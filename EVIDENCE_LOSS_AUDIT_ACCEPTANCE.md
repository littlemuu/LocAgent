# Evidence-loss audit boundary

Normal execution and scoring require intact original bodies. Explicit forensic audit may record a nonrecoverable evidence-loss halt while preserving charges, reserves, references and proofs. Clearing an active token fences stale work but does not prove executor exit. Restoring a body grants no continuation; persistence failures propagate. Tests inject missing/corrupt bodies and write faults in temporary stores.

## Portable verification

~~~sh
LOCAGENT_ALLOW_PAID=0 LITELLM_LOCAL_MODEL_COST_MAP=True HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 \
  .venv/bin/python -B -m unittest discover -s tests -p test_evidence_loss_audit.py -v
~~~

These tests use synthetic/offline data. Private original evidence is retained locally,
not required by these tests and not included in Git. Final real-run results and
limitations are in [NEW20_REAL_EVALUATION.md](NEW20_REAL_EVALUATION.md).
