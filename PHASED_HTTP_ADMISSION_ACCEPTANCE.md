# HTTP transport and explicit admission

The fixed official HTTP transport disables redirects, proxy inheritance and retries. Admission requires exact reviewed plan bindings, explicit human authorization, fresh pricing, the paid switch and one-use claim. CLI proposals are unapproved drafts; the CLI does not activate them or automatically load credentials. Tests use MockTransport and synthetic credentials/approvals only in temporary directories. Partial claims remain consumed. Simulation is a separate namespace and cannot be promoted to live. The former inline-body size defect is superseded by bounded storage.

## Portable verification

~~~sh
LOCAGENT_ALLOW_PAID=0 LITELLM_LOCAL_MODEL_COST_MAP=True HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 \
  .venv/bin/python -B -m unittest discover -s tests -p test_phased_http.py -v
~~~

These tests use synthetic/offline data. Private original evidence is retained locally,
not required by these tests and not included in Git. Final real-run results and
limitations are in [NEW20_REAL_EVALUATION.md](NEW20_REAL_EVALUATION.md).
