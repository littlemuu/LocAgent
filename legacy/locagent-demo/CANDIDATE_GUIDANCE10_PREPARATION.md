# Candidate-guidance10 experiment preparation

> Command examples run from the repository root. Shell examples require a configured environment; Examples using `$PYTHON` accept an existing compatible interpreter; direct `.venv/bin/python` commands require the project environment. Historical `outputs/` evidence and helper scripts are local artifacts, not included in a fresh clone.

This records preparation for a public ten-task DeepSeek Flash comparison.
Live execution requires a successful independent review and the admission checks below.
No live approval, consumed receipt, credential or real provider call is created here.

## Scope and preservation

Preparation baseline: `0d5af3eeff0afb73a488c523d407b56e8fde7bda`.
Preserved source tree identity: `79148ecc013310e58d6780972feb94182b6b3a2d`.
Preparation did not mutate databases, credentials or existing experiment evidence.

Experiment files are under outputs/candidate-guidance10-preparation-20261010/.
The new ignored locagent_service/candidate_guidance_cohort.json is a local frozen
cohort specification, not an approval. Do not replace phased_cohorts.json.

## Fixed comparison and sample selection

The comparison axis is candidate_guidance=False/True; suppress_repeats=False in
both arms. Two connectivity tasks are scored separately from eight primary tasks.
Five pairs are off-first and five on-first; primary order is balanced 4/4.

Dataset: princeton-nlp/SWE-bench_Lite, test split, revision
6ec7bb89b9342f664a54a6e0a6ea6501d3437cc2.
Local Arrow SHA-256: b77fa3036c06219715a35e8088fee13b0b87bc957052546c3270caf38a325627.

| Role | Instance | Exact base commit | Order |
| --- | --- | --- | --- |
| connectivity | matplotlib__matplotlib-22711 | f670fe78795b18eb1118707721852209cd77ad51 | off → on |
| connectivity | django__django-11179 | 19fc6376ce67d01ca37a91ef2f55ef769f50513a | on → off |
| primary | pydata__xarray-4094 | a64cf2d5476e7bbda099b34c40b7be1880dbd39a | off → on |
| primary | sphinx-doc__sphinx-8435 | 5d8d6275a54f2c5fb72b82383b5712c22d337634 | off → on |
| primary | pytest-dev__pytest-5495 | 1aefb24b37c30fba8fd79a744829ca16e252f340 | off → on |
| primary | django__django-16408 | ef85b6bf0bc5a8b194f0724cf5bbedbcee402b96 | off → on |
| primary | matplotlib__matplotlib-23563 | 149a0398b391cfc4eddb5e659f50b3c66f32ea65 | on → off |
| primary | sphinx-doc__sphinx-8273 | 88b81a06eb635a1596617f8971fa97a84c069e93 | on → off |
| primary | pytest-dev__pytest-8906 | 69356d20cfee9a81972dcbf93d8caf9eabe113e8 | on → off |
| primary | django__django-16910 | 4142739af1cda53581af4169dbe16d6cd5e26948 | on → off |

These are locally new tasks, not a claimed unseen/blind benchmark. The repository
ships Claude predictions covering all 300 test IDs; predictions are not consulted
or sent to the model. Gold patch/test_patch remain only in scoring-only/. Runtime
sample files contain the four task fields plus dataset provenance, never answers
or hints. Preparation uses git archive, AST and BM25; no target repository code is
executed.

The two Django ORM tasks remain as agreed after semantic review: 16408 concerns
nested FilteredRelation hydration/cache assignment in compiler.py; 16910 concerns
reverse OneToOne projection masks for only()+select_related() in query.py. Their
triggers/functions/fixes differ, but the shared ORM domain is a correlation
limitation. Selection filters and ranking are frozen in selection-audit.json.

## Scoring and source binding

scoring-only/metric-specification.json is frozen before any live result. File and
function recall@1/@3 use fixed macro denominators; failures/missing/invalid results
score zero. Function NA is declared only when no base-function label exists.
Deleted lines map through base AST; inserted lines map through patched AST and
exact base qualified name. New callables are disclosed separately. Existing base
functions missing from the graph remain gold; no constructor/class substitution.
The final label-audit.json records line attribution and graph gaps.

Source manifests bind exact commit, all snapshot/index artifact hashes, pip-freeze
environment and the full project behavior closure. Runtime models use only those
prepared bundles. Source identities are immutable. Rebinding after implementation
changes creates new manifests and preserves old ones. A fresh rebuild can produce
new bundle identities; the frozen specification produces deterministic plan bytes.

The plan, child executor, localize_prepared, call ledger, durable result and summary
all carry the independent candidate-guidance axis. Approval bindings also include
the axis, fixed options and phase roles. Existing suppression plans retain their
prior behavior and shape. HTTP TaskOptions remain unchanged.

## Budget and model

A new shared CNY 5 cap covers both phases: at most 60 calls, 3 per arm, 512 output
tokens per call, temperature 0, thinking disabled, no retries/redirects, 60-second
HTTP timeout and a 65,536-byte request estimate gate. Each call reserves CNY
2.101248 for the full provider context. Sixty maximum reserves total CNY
126.074880, so the cap may stop the run before completion; it is not a guarantee
that all 60 calls can be made. Unknown outcomes retain full reserve and halt.
Old approvals, ledgers and budgets must never be reused or reset.

Configured model: openai/deepseek-v4-flash; wire alias: deepseek-v4-flash;
endpoint: https://api.deepseek.com/chat/completions.
The [official pricing page](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)
currently says this alias is accepted and served by DeepSeek-V4.1-Flash. Accounting
uses conservative peak uncached CNY 2/million input and CNY 8/million output, with
no assumed discounts. pricing-alias-audit.json is a public documentation check,
not account/all-in pricing confirmation. Actual returned_model is saved per call
and checked against raw response evidence. A returned alias does not independently
prove immutable backend weights; the resolved family comes from official provider
documentation. Recheck alias mapping before live admission.

## Validation and reproduction

Complete portable offline suite: 391 tests passed in 346.000 seconds, including
10 new axis tests. The test export omits historical runtime artifacts and
credentials. Logs: full-offline.log, axis-tests.log. The initial compatibility
run exposed an old-plan exception-type regression; it was repaired and the full
suite passed. The original failed logs are retained.

From the repository root:

    LOCAGENT_ALLOW_PAID=0 LITELLM_LOCAL_MODEL_COST_MAP=True HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 .venv/bin/python -B -m unittest discover -s tests -p 'test_*.py' -v

The preparation scripts prepare_all.py, freeze_experiment.py and
freeze_and_simulate.py, input sample JSONs, fetch logs and archive audits are
preserved in the experiment directory. They use fresh output namespaces and
exclusive plan writes. Do not rerun the one-time freezer over existing plans.

For read-only frozen-plan verification, set LOCAGENT_SOURCE_ROOT to the experiment
directory's sources/, load live-plan.json with phased.read_json, then call
phased.validate_plan, phased.verify_sources and phased.check_labels with the
frozen scoring-only/labels.json. Recompute canonical expected_plan and compare its
SHA-256 to the frozen file. No live init/run is needed for these checks.

For an additional mock HTTP run, use a fresh source export and unique ledger,
then phased.initialize(..., simulate_http=True), run connectivity and primary,
and call phased.summary. Simulation stays mode=simulation, has admission=None,
uses HTTP MockTransport, never consumes real approval, and never grants a quality
claim. Do not reset or promote an existing simulation ledger.

## Independent review and subsequent live gate

Read independent-review-checklist.json, frozen-identities.json, both plan files,
label audit, test log, source-preservation report and HTTP simulation evidence.
No live quality/token/cost improvement can be claimed from fixtures.

Independent review does not itself authorize paid execution. The recorded CNY 5
budget applies only to its approved experiment; live execution requires valid
budget/data authorization, fresh account/all-in pricing confirmation and the
existing exact-plan single-use admission mechanism.
Use existing credentials only for normal authentication, without copying them
into artifacts or editing .env. Run connectivity first and inspect raw usage,
actual returned models and the checkpoint before continuing primary with the
same ledger. Unknown paid results stop for explicit audit; never blindly replay.

## Additional safe commands

Read-only frozen-input verification (no ledger writes or model calls):

    .venv/bin/python -B outputs/candidate-guidance10-preparation-20261010/verify_frozen.py

Optional fresh mock replay, using a unique experiment/ledger and no credentials:

    .venv/bin/python -B outputs/candidate-guidance10-preparation-20261010/replay_mock.py

The optional replay creates a new simulation plan identity solely to avoid
resetting the first simulation owner. It preserves the same frozen cohort and
configuration and cannot run in live mode.

## Final verified evidence (2026-10-10)

- Ten exact-commit static preparations completed successfully. Both plan files and
  all source/artifact/configuration bindings passed read-only verification.
- Offline plan SHA-256: 0a934a821d1f8bcd276f73bac655870fa05f70e676a738e5f7dc3fd494468b6b
- Frozen live-plan SHA-256: 4812e04f1cabbf5f1d337e828bb48b45e0a13b495aee0b807bf3582cd0927c5c
- Labels SHA-256: 8901f89f0711ac7b5d28289d614c976e05dfae82ca49246c6533801c145bbcc4
- HTTP simulation completed all 20 isolated arms and 60 calls, with two durable
  checkpoints, in 230.039 seconds. Mode remained simulation, admission remained
  null and paid calls remained zero. This is plumbing evidence, not model quality.
- Independent diagnostic-evidence audit checked 30 guidance requests and 26
  candidate references against graph identities and complete delivered spans.
  Largest note: 995 / 4096 JSON bytes; largest combined delivery: 3695 / 24576
  bytes; largest provider request estimate: 25168 / 65536 bytes.
- Both groups have function labels for every task: connectivity M=2, primary M=8,
  no NA. No base-function gold labels are absent from these graphs. The new
  SQLCompiler.get_related_selections.local_setter_noop in Django 16408 remains
  separately disclosed and is not mislabeled as a base function.
- Historical model audit read 120 saved, hash-verified real responses from the
  prior final new20 run: configured/wire alias was deepseek-v4-flash; every raw
  response reported deepseek-flash. Zero ledger/model mismatches and zero new
  requests. This evidence is in historical-returned-model-audit.json.
- 8,254 existing historical evidence entries and 197 source-snapshot files matched
  their hashes. The preserved source tree and prior candidate-guidance
  implementation matched their hashes; runtime and tests matched the tested export.
- At preparation time no network or resource blocker remained. Real evaluation required
  independent-review pass and the existing fresh paid-admission preflight.

Evidence: full-offline.log, frozen-verification.json,
http-simulation-acceptance.json, http-simulation-primary-summary.json,
simulation-independent-audit.json, preservation-and-tested-source.json.
The simulated summaries have quality_claim_allowed=false and no quality, token
or monetary improvement metrics.
