# Offline regression tests

Run from the LocAgent repository root with the existing CPU virtual environment:

```sh
LITELLM_LOCAL_MODEL_COST_MAP=True HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 .venv/bin/python -B -m unittest discover -s tests -p 'test_*.py' -v
```

The combined suite currently has 48 unittest methods: 10 return-trace tests,
4 request-contract tests and 34 Stage 1 safety/integration tests. No pytest,
credentials or additional dependency installation is required.

The original return-trace tests use a small in-memory graph and the real entity
search, formatting and ledger functions. They do not run the main loop or load
saved fixtures. Tool observations include the newline added by `print()` in
`execute_ipython`.

The socket guard is active before production-tool imports and throughout the
suite. DNS, TCP connection and UDP send attempts fail, including attempts that
an imported library catches internally. Offline Hugging Face flags prevent
dataset downloads, and LiteLLM uses its bundled price metadata.

The 10 return-trace tests cover source-independent repeat detection, changed
content and entity isolation, legacy histories, JSON round trips, current
observation messages, the suppression switch, unseen repeats, removed context,
short responses and folded entity hints. Original code stays in the ledger even
when the tool output is shortened.

The Stage 1 tests exercise the shared main loop, real graph tools, result
parsing, provider failures, state cleanup, path safety and the legacy queue
wrapper with fake providers. They prepare a small BM25 index and pickle fixture
in temporary directories and remove them on exit. They do not depend on saved
`outputs/day1` fixtures or call a real model.

Additional regression cases cover root-level files, unsafe root paths, legacy
nested-path parsing, and strict finish arguments with a matching isolated schema.

See [Stage 1 acceptance](../STAGE1_ACCEPTANCE.md) for the contract, resource and
concurrency boundaries. When the historical fixtures exist, run:

```sh
.venv/bin/python -B tests/run_historical_smokes.py
```

This runner checks `day4_return_trace_smoke.py`, `day5_main_trace_smoke.py` and
`day6_repeat_output_smoke.py`, including the legacy IPython path and trajectory
persistence. It requires saved files under `outputs/day1`, blocks TCP/UDP/DNS
and live completions, and allows local AF_UNIX IPC for multiprocessing.Manager.
Day5 creates a new output run directory without overwriting older artifacts.

Verified on 2026-10-06 in Ubuntu WSL: all 48 unittest methods and all three
historical smoke scripts passed, with no network or live model attempts.
