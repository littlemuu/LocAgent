# Fixed 20-task real evaluation — independently reviewed

The complete real experiment and descriptive results passed independent review on
2026-10-10. Both suppression settings used the same 20 fixed repository commits,
source/index/model configuration and scoring labels. The configuration used
openai/deepseek-v4-flash (documented V4.1-Flash service alias), temperature zero,
thinking disabled, at most three requests per arm and 512 output tokens per call.

Forty executor arms completed, with 120 settled requests and two checkpoints:
first five tasks / 30 requests, then remaining fifteen / 90 requests. No executor
arm failed and no call remained unknown. Execution completion is not valid finish:
three results had invalid_finish and retained iteration_limit status.

| Metric | Suppression off | Suppression on |
|---|---:|---:|
| Valid finish / 20 | 19 | 18 |
| File Recall@1 / 20 | 85.00% | 75.00% |
| File Recall@3 / 20 | 90.00% | 80.00% |
| Function Recall@1 / 18 applicable | 50.93% | 45.37% |
| Function Recall@3 / 18 applicable | 68.52% | 62.04% |
| Function Recall@1, coverage-adjusted / 20 | 45.83% | 40.83% |
| Function Recall@3, coverage-adjusted / 20 | 61.67% | 55.83% |
| Prompt tokens | 374,226 | 364,756 |
| Completion tokens | 8,740 | 8,448 |
| Conservative cost upper bound (CNY) | 0.818372 | 0.797096 |
| Recorded attempt seconds | 251.261308 | 252.513828 |
| Completed-result engine seconds | 217.068933 | 218.164172 |

File/finish denominators remain 20. Function recall uses 18 predeclared applicable
tasks and 27 targets; pytest-5227 and django-11099 are NA. Unrepresentable
constructor truth remains included; classes do not substitute for functions.
Invalid finishes receive no location credit.

Input tokens were 2.53% lower and the conservative cost bound 2.60% lower with
suppression, but recall and valid-finish rate were lower, and attempt/engine time
slightly higher. This is a measured tradeoff, not overall quality/performance
improvement. A single small paired run provides no repeated-trial confidence
intervals or causal identification. Model trajectories, order, cache and machine
timing can affect outcomes even at temperature zero. No extra trial was run to
obtain a more favorable result.

Total conservative cost was CNY 1.615468, computed from saved usage at 2 CNY per
million input tokens (all assumed uncached) and 8 CNY per million output tokens.
This is the historical evaluation's conservative accounting formula, not an invoice
or a statement of current tariffs. Recorded phase wall time was 508.887805 seconds;
it differs from the attempt and engine measurements above.

Independent review rebuilt all 120 request hashes, checked raw response hashes
and usage, recomputed cost/metrics without the runtime summarizer, and verified
40 result/call sets, both checkpoints and source/label semantics. The enabled arm
produced 15 shortened tool messages across 10 arms, seen in 11 later requests.
This proves suppression occurred, not that localization improved.

Earlier interrupted experiments remain preserved locally and are not pooled into
this comparison. No failed executor arm occurred in this final live run. Recovery
and safe-failure continuation evidence comes from separate offline/process tests,
not a claimed successful live recovery.

## Public reproduction boundary

Public source includes the evaluator, parsers, binding, ownership/storage checks
and portable synthetic tests. Operational cohort bindings, raw provider responses,
approvals, budget/control records, credentials, databases and private paths are
excluded from Git. A new real evaluation requires newly reviewed bindings and
separate explicit authorization; this report authorizes no requests.

The existing defaults are unchanged: core LocalizationOptions defaults suppression
off; HTTP TaskOptions defaults it on. Paired evaluation supplies both flags
explicitly. Portable regression instructions are in [tests/README.md](tests/README.md).

Supported engineering description: implemented reproducible fixed-source paired
evaluation, per-request budget settlement and evidence verification; completed a
20-task/40-arm/120-request real experiment and quantified the context-suppression
cost/quality tradeoff.
