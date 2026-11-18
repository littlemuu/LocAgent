# Prepared-source compatibility acceptance

Exact Git-tree archives preserve ordinary Python blobs, including export-subst cases. Links are rejected by default; explicit omission accepts only audited direct in-repository non-executable image targets. Ordinary inputs retain an 8,000-character limit; prepared inputs permit 32,768 only after manifest/artifact and exact-text validation. Historical compatibility acceptance covered 25 sources / 50 scripted arms and 35 PostgreSQL/process cases (32 existing plus 3 long-input cases), not model quality. Portable tests use synthetic repositories/indexes. AST labels use deleted base lines and inserted patched lines; unrepresentable constructors remain truth without class substitution.

## Portable verification

~~~sh
LOCAGENT_ALLOW_PAID=0 LITELLM_LOCAL_MODEL_COST_MAP=True HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 \
  .venv/bin/python -B -m unittest discover -s tests -p test_expanded_compatibility.py -v
~~~

These tests use synthetic/offline data. Private original evidence is retained locally,
not required by these tests and not included in Git. Final real-run results and
limitations are in [NEW20_REAL_EVALUATION.md](NEW20_REAL_EVALUATION.md).
