# Phased execution acceptance

The separate CLI supports regression-five and first-five/remaining-fifteen stages, sharing budgets and arm quotas. A phase lock, canonical ledger owner, run tokens and linked state hashes reject concurrent runners and copied/rolled-back records. Reservations precede transport, durable responses precede settlement and results precede checkpoints. Unknown outcomes never auto-resend. Explicit settled-response reconstruction checks identical request hashes. Each GraphLocalizer arm remains a separate process; local files are not a distributed exactly-once service.

## Portable verification

~~~sh
LOCAGENT_ALLOW_PAID=0 LITELLM_LOCAL_MODEL_COST_MAP=True HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 \
  .venv/bin/python -B -m unittest discover -s tests -p test_phased.py -v
~~~

These tests use synthetic/offline data. Private original evidence is retained locally,
not required by these tests and not included in Git. Final real-run results and
limitations are in [NEW20_REAL_EVALUATION.md](NEW20_REAL_EVALUATION.md).
