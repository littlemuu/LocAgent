# Settled protocol-failure isolation

Only the exact allowlisted malformed/non-object non-finish argument error can terminate a failed arm and continue. All calls must be settled; raw evidence, durable error, owner/token, phase lock, exact child reaping and empty process group must agree. A persisted failure proof is read back before the next arm. Portable tests use handwritten synthetic bodies, temporary approvals, local subprocess exits and an independently enumerated 256-condition oracle. No JSON repair, retry, budget reset or unknown-outcome replay is allowed. The final real experiment had no failed executor arms, so live recovery efficacy is not claimed.

## Portable verification

~~~sh
LOCAGENT_ALLOW_PAID=0 LITELLM_LOCAL_MODEL_COST_MAP=True HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 \
  .venv/bin/python -B -m unittest discover -s tests -p test_settled_arm_isolation.py -v
~~~

These tests use synthetic/offline data. Private original evidence is retained locally,
not required by these tests and not included in Git. Final real-run results and
limitations are in [NEW20_REAL_EVALUATION.md](NEW20_REAL_EVALUATION.md).
