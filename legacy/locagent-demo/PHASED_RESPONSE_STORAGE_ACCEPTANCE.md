# Bounded response storage

Raw bytes are exclusively published and fsynced before the metadata reference and settlement. Metadata stores filename, size and hash. Limits are 8 MiB per body, 32 MiB cumulative raw storage per ledger and 8 MiB per JSON metadata file. Orphan/partial files count toward quota. Synthetic tests cover large error/success bodies, overflow, parseable incomplete prefixes, full-store refusal, missing/corrupt bodies, publication crashes, links and overwrite rejection. Unknown results retain full reserves; unreferenced bytes are not automatically adopted.

## Portable verification

~~~sh
LOCAGENT_ALLOW_PAID=0 LITELLM_LOCAL_MODEL_COST_MAP=True HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 \
  .venv/bin/python -B -m unittest discover -s tests -p test_response_storage.py -v
~~~

These tests use synthetic/offline data. Private original evidence is retained locally,
not required by these tests and not included in Git. Final real-run results and
limitations are in [NEW20_REAL_EVALUATION.md](NEW20_REAL_EVALUATION.md).
