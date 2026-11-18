# Finish-evidence compatibility

Validated legacy success/empty can establish finish; bounded diagnostics take precedence. Iteration-limit and invalid/missing/truncated finishes are not valid. Ambiguous completed records expose an unknown count and NA aggregate finish rate. Failed/missing tasks retain fixed-denominator zero. Tests run the actual local loop with scripted providers; executor completion, valid finish and correct localization remain distinct.

## Portable verification

~~~sh
LOCAGENT_ALLOW_PAID=0 LITELLM_LOCAL_MODEL_COST_MAP=True HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 \
  .venv/bin/python -B -m unittest discover -s tests -p test_finish_compatibility.py -v
~~~

These tests use synthetic/offline data. Private original evidence is retained locally,
not required by these tests and not included in Git. Final real-run results and
limitations are in [NEW20_REAL_EVALUATION.md](NEW20_REAL_EVALUATION.md).
