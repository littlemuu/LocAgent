# Offline return trace regression tests

Run from the LocAgent repository root with the existing CPU virtual environment:

```sh
HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 .venv/bin/python -B -m unittest discover -s tests -p 'test_*.py' -v
```

No pytest or additional dependency installation is required. The tests use a
small graph constructed in memory and the real entity search, formatting and
return-trace functions. They do not load `outputs/day1`, pickle fixtures,
datasets or BM25 indexes. They do not call model clients or run the localization
main loop. Tool observations include the newline added by `print()` in
`execute_ipython`.

The socket guard is active before production-tool imports and throughout the
suite. DNS, TCP connection and UDP send attempts fail, including attempts that
an imported library catches internally. The offline Hugging Face flags add a
second guard against accidental dataset downloads. No credentials are needed.

The 10 tests cover source-independent repeat detection, changed content and
entity isolation, legacy histories, JSON round trips, current observation
messages, the suppression switch, unseen repeats, removed context, short
responses and folded entity hints. Original code stays in the ledger even when
the tool output is shortened.

Existing `day4_return_trace_smoke.py`, `day5_main_trace_smoke.py` and
`day6_repeat_output_smoke.py` provide broader historical smoke coverage, but
require saved files under `outputs/day1`. Day5 also writes output artifacts.
This suite does not verify model requests, IPython execution, the full main
loop, trajectory persistence or the outer localization runner.
