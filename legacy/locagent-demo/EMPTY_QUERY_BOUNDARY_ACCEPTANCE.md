# Empty-query retrieval boundary

BM25 fallback checks the installed tokenizer before ranking. Empty-token whitespace, punctuation, regex fragments and stopwords return no locations; exact graph/entity matches retain priority. Nonempty backend errors still propagate. Ordinary-query ranking, scores and formatting remain unchanged. Safe exception projection retains type/stack coordinates but no message, locals or raw context; cycles/depth are bounded and exception truthiness is never evaluated. The public error and continuation whitelist are unchanged.

## Portable verification

~~~sh
LOCAGENT_ALLOW_PAID=0 LITELLM_LOCAL_MODEL_COST_MAP=True HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 \
  .venv/bin/python -B -m unittest discover -s tests -p test_empty_query_boundary.py -v
~~~

These tests use synthetic/offline data. Private original evidence is retained locally,
not required by these tests and not included in Git. Final real-run results and
limitations are in [NEW20_REAL_EVALUATION.md](NEW20_REAL_EVALUATION.md).
