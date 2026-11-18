"""One controlled model request; no search execution or automatic retries."""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def main():
    # Preserve the process-local workaround validated on Day 1.
    for name in (
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
        "http_proxy", "https_proxy", "all_proxy",
    ):
        os.environ.pop(name, None)

    if not os.environ.get("DEEPSEEK_API_KEY"):
        raise SystemExit("DEEPSEEK_API_KEY is not set; no request sent.")
    task_path = Path("outputs/day1/task.json")
    if not task_path.is_file():
        raise SystemExit("Run this script from ~/projects/LocAgent.")
    task = json.loads(task_path.read_text(encoding="utf-8"))
    problem = task.get("problem_statement")
    if not isinstance(problem, str) or not problem.strip():
        raise SystemExit("task.json has no nonempty problem_statement; no request sent.")

    import litellm

    messages = [
        {"role": "system", "content": (
            "You locate code relevant to a GitHub issue. Use search_code to "
            "search the repository. Base any localization on returned code "
            "evidence, including file paths, functions and reasons. "
            "First choose search terms based on the issue."
        )},
        {"role": "user", "content": problem},
    ]
    tool_schema = [{"type": "function", "function": {
        "name": "search_code",
        "description": "Search repository code using a query string.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    }}]
    # Keep the settings that already worked; do not add parallel-call options.
    settings = {
        "model": "openai/deepseek-v4-flash",
        "api_base": "https://api.deepseek.com",
        "extra_body": {"thinking": {"type": "disabled"}},
        "max_tokens": 256,
        "timeout": 60,
        "num_retries": 0,
        "tool_choice": {"type": "function", "function": {"name": "search_code"}},
    }
    started_at = datetime.now(timezone.utc)
    out = Path("outputs/day2") / (
        "first_response_" + started_at.strftime("%Y%m%dT%H%M%SZ")
        + "_" + uuid4().hex[:8] + ".json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "started_at": started_at.isoformat(),
        "instance_id": task.get("instance_id"),
        "base_commit": task.get("base_commit"),
        "purpose": "Diagnostic reconstruction, not an exact replay of the lost Day 1 prompt",
        "settings": settings,
        "messages": messages,
        "tools": tool_schema,
        "status": "started",
    }

    def save():
        out.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    save()
    print("Sending one request; no automatic retries.", flush=True)
    started = time.perf_counter()
    try:
        response = litellm.completion(
            **settings, messages=messages, tools=tool_schema,
            api_key=os.environ["DEEPSEEK_API_KEY"],
        )
    except Exception as exc:
        record.update({
            "status": "request_error",
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "error_type": type(exc).__name__,
            "http_status": str(getattr(exc, "status_code", "unknown")),
        })
        save()
        # Do not dump exception text or request configuration containing credentials.
        print("Request error:", record["error_type"], record["http_status"])
        print("Saved:", out)
        print("Stop here; do not rerun automatically.")
        return 1

    # Save the response before inspecting choices or checking tool calls.
    record.update({
        "status": "response_received",
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "response": response.model_dump(mode="json"),
    })
    save()
    print("Saved:", out)
    print("Returned model:", response.model)
    print("Elapsed seconds:", record["elapsed_seconds"])
    print("Usage:", response.usage)
    if not response.choices:
        print("No choices; inspect saved response before any further request.")
        return 0
    choice = response.choices[0]
    calls = choice.message.tool_calls or []
    print("finish_reason:", choice.finish_reason)
    print("tool_calls count:", len(calls))
    for i, call in enumerate(calls, 1):
        print(f"Call {i}: id={call.id}, name={call.function.name}")
        print("arguments:", call.function.arguments)
        try:
            args = json.loads(call.function.arguments)
            valid = (
                call.function.name == "search_code"
                and isinstance(args, dict)
                and isinstance(args.get("query"), str)
                and bool(args["query"].strip())
            )
            print("Valid search_code arguments:", valid)
        except (TypeError, ValueError):
            print("Valid search_code arguments: False (invalid JSON)")
    print("Assistant content:", repr(choice.message.content))
    print("Done. No BM25 search or second model request was executed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
