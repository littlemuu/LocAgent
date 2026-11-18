# Integrated v3 live development result

New requests: 38; cumulative requests: 53. Batch halted: False; reason: None.

A = native graph + positive body BM25 + path index. B = OpenHands basic tools + unchanged entity BM25.

|Case|Arm|Status|Requests|Input tokens|Output tokens|First gold rank|Upper CNY|
|---|---|---|---:|---:|---:|---:|---:|
|gaogaotiantian__viztracer-528|A|completed|4|23057|865|none|0.053034|
|gaogaotiantian__viztracer-528|B|completed|4|13055|955|none|0.033750|
|huggingface__accelerate-3261|A|completed|3|17286|794|1|0.040924|
|huggingface__accelerate-3261|B|completed|4|20302|941|1|0.048132|
|roboflow__supervision-1698|A|completed|4|23312|863|1|0.053528|
|roboflow__supervision-1698|B|completed|4|12092|1067|1|0.032720|
|spotify__luigi-3324|A|completed|3|20122|721|2|0.046012|
|spotify__luigi-3324|B|completed|4|19988|842|2|0.046712|
|tobymao__sqlglot-3436|A|completed|4|24282|1004|none|0.056596|
|tobymao__sqlglot-3436|B|completed|4|14403|909|1|0.036078|

New input/output tokens: 187899/8961. Cache hit/miss input: 86784/101115.
New response-based peak/no-cache cost upper bound: CNY 0.447486; pending reservation: CNY 0.000000.
Old upper CNY 0.172942 + new upper = cumulative CNY 0.620428.
New estimate using response cache usage and official weekday peak/offpeak timing: CNY 0.27738936. Not an independently obtained account debit.

Official pricing: https://api-docs.deepseek.com/zh-cn/quick_start/pricing/

Strict metric counts (quality kept separate from the preceding batch):
{
  "baseline": {
    "completed": 5,
    "failed": 0,
    "not_started": 0,
    "strict_hit_counts": {
      "1": 2,
      "3": 3,
      "5": 3
    },
    "complete_only_denominator": 5,
    "planned_denominator": 5
  },
  "retrieval": {
    "completed": 5,
    "failed": 0,
    "not_started": 0,
    "strict_hit_counts": {
      "1": 3,
      "3": 4,
      "5": 4
    },
    "complete_only_denominator": 5,
    "planned_denominator": 5
  }
}

Tool selection and budget closure:
- gaogaotiantian__viztracer-528 baseline: locagent_retrieve calls=0; finish-only requests=1; selected entities=["src/viztracer/viewer.py:viewer_main"]
- gaogaotiantian__viztracer-528 retrieval: locagent_retrieve calls=0; finish-only requests=1; selected entities=["src/viztracer/viewer.py:viewer_main", "src/viztracer/__init__.py:__all__"]
- huggingface__accelerate-3261 baseline: locagent_retrieve calls=0; finish-only requests=1; selected entities=["examples/by_feature/megatron_lm_gpt_pretraining.py:main", "examples/by_feature/megatron_lm_gpt_pretraining.py:parse_args", "src/accelerate/accelerator.py:Accelerator.__init__", "src/accelerate/accelerator.py:Accelerator.logging_dir"]
- huggingface__accelerate-3261 retrieval: locagent_retrieve calls=1; finish-only requests=1; selected entities=["examples/by_feature/megatron_lm_gpt_pretraining.py:main", "src/accelerate/accelerator.py:Accelerator", "src/accelerate/utils/dataclasses.py:ProjectConfiguration"]
- roboflow__supervision-1698 baseline: locagent_retrieve calls=0; finish-only requests=1; selected entities=["supervision/detection/core.py:Detections.__getitem__", "supervision/detection/core.py:Detections.empty", "supervision/validators/__init__.py:validate_xyxy"]
- roboflow__supervision-1698 retrieval: locagent_retrieve calls=0; finish-only requests=1; selected entities=["supervision/detection/core.py:Detections.__getitem__", "supervision/detection/core.py:Detections.empty", "supervision/validators/__init__.py:validate_xyxy", "supervision/detection/utils.py:get_data_item"]
- spotify__luigi-3324 baseline: locagent_retrieve calls=0; finish-only requests=1; selected entities=["luigi/contrib/postgres.py:CopyToTable", "luigi/contrib/postgres.py:CopyToTable.copy", "luigi/contrib/postgres.py:CopyToTable.run"]
- spotify__luigi-3324 retrieval: locagent_retrieve calls=1; finish-only requests=1; selected entities=["luigi/contrib/postgres.py:CopyToTable", "luigi/contrib/postgres.py:CopyToTable.copy", "luigi/contrib/postgres.py:CopyToTable.run"]
- tobymao__sqlglot-3436 baseline: locagent_retrieve calls=0; finish-only requests=1; selected entities=["sqlglot/parser.py:Parser._parse_create", "sqlglot/expressions.py:SequenceProperties"]
- tobymao__sqlglot-3436 retrieval: locagent_retrieve calls=0; finish-only requests=1; selected entities=["sqlglot/parser.py:Parser._parse_sequence_properties", "sqlglot/parser.py:Parser.CREATE_SEQUENCE", "sqlglot/parser.py:Parser._parse_var_from_options"]

Evidence and constraints:
- No automatic retry or model-driven extra budget. Old results remain separate; only accounting adds the prior15 calls.
- The SDK entity retrieval path-query weakness remains unfixed. Use of the tool does not prove it supplied useful evidence.
- Exposed development tasks, strong hints, small sample, single-pass labels: no independent test claim.
- Multiple native changes (positive score filtering, indexed pagination) and shared finish policy changed together. Whole-system comparison cannot identify a retrieval causal effect.
- See analysis.json for per-request usage/tool arguments and wire-audit.json for actual delivered evidence budgets; raw ledgers preserve responses.
