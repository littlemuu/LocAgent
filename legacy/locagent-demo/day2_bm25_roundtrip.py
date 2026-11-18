"""Resume a saved Day 2 response: two searches, then one model request."""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first_response", type=Path)
    args = parser.parse_args()
    root = Path.cwd()
    sys.path.insert(0, str(root))
    for name in (
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
        "http_proxy", "https_proxy", "all_proxy",
    ):
        os.environ.pop(name, None)
    if not os.environ.get("DEEPSEEK_API_KEY"):
        raise SystemExit("Key is not set; no request sent.")

    first = json.loads(args.first_response.read_text(encoding="utf-8"))
    task = json.loads((root / "outputs/day1/task.json").read_text(encoding="utf-8"))
    for key in ("instance_id", "base_commit"):
        if not task.get(key) or first.get(key) != task[key]:
            raise SystemExit(f"Task metadata mismatch: {key}; no request sent.")
    repo = root / "outputs/day1/requests"
    actual_commit = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    if actual_commit != task["base_commit"]:
        raise SystemExit("Requests HEAD differs from task base_commit; no request sent.")

    response = first["response"]
    choice = response["choices"][0]
    if choice.get("finish_reason") != "tool_calls":
        raise SystemExit("Saved response did not finish with tool_calls; inspect it first.")
    message = choice["message"]
    calls = message.get("tool_calls") or []
    if not 1 <= len(calls) <= 2:
        raise SystemExit("Expected 1 or 2 calls within this exercise's budget.")
    ids = set()
    queries = []
    clean_calls = []
    for call in calls:
        fn = call["function"]
        if call.get("type") != "function" or fn["name"] != "search_code":
            raise SystemExit("Unexpected tool; no request sent.")
        call_id = call.get("id")
        if not isinstance(call_id, str) or not call_id or call_id in ids:
            raise SystemExit("Missing or duplicate tool_call_id; no request sent.")
        ids.add(call_id)
        parsed = json.loads(fn["arguments"])
        query = parsed.get("query") if isinstance(parsed, dict) else None
        if not isinstance(query, str) or not query.strip():
            raise SystemExit("Invalid query; no request sent.")
        queries.append(query)
        clean_calls.append({"id": call_id, "type": "function", "function": {
            "name": fn["name"], "arguments": fn["arguments"],
        }})

    index_dir = root / "outputs/day1/bm25" / task["instance_id"]
    if not index_dir.is_dir():
        raise SystemExit("Persisted index is missing; no request sent.")
    out = args.first_response.with_name(args.first_response.stem + "_bm25_roundtrip.json")
    if out.exists():
        raise SystemExit(f"Record already exists: {out}. Inspect it before any rerun.")

    from plugins.location_tools.retriever.bm25_retriever import build_retriever_from_persist_dir
    import litellm

    messages = list(first["messages"])
    messages.append({
        "role": "assistant", "content": message.get("content"),
        "tool_calls": clean_calls,
    })
    # Explicit settings keep credentials out of the record.
    settings = {key: first["settings"][key] for key in (
        "model", "api_base", "extra_body", "timeout",
    )}
    settings.update(max_tokens=1200, num_retries=0, tool_choice="none")
    record = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "source_response": str(args.first_response),
        "instance_id": task["instance_id"], "base_commit": task["base_commit"],
        "actual_repo_commit": actual_commit,
        "index_dir": str(index_dir),
        "index_provenance": "Day 1 index; index contents not independently rehashed here",
        "top_k_per_query": 3, "max_code_characters_per_hit": 1800,
        "first_usage": response.get("usage"),
        "first_elapsed_seconds": first.get("elapsed_seconds"),
        "settings": settings, "tools": first["tools"],
        "messages": messages, "searches": [], "status": "started",
    }
    # Reserve a deterministic output so accidentally running twice cannot resend.
    with out.open("x", encoding="utf-8") as handle:
        json.dump(record, handle, ensure_ascii=False, indent=2)

    def save():
        temporary = out.with_suffix(".tmp")
        temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(out)

    started = time.perf_counter()
    phase = "load_index"
    try:
        print("Loading the existing BM25 index...", flush=True)
        retriever = build_retriever_from_persist_dir(str(index_dir))
        retriever.similarity_top_k = 3
        phase = "search"
        for call, query in zip(clean_calls, queries):
            search_started = time.perf_counter()
            hits = []
            for rank, item in enumerate(retriever.retrieve(query)[:3], 1):
                code = item.node.get_content()
                hits.append({
                    "rank": rank,
                    "file": item.node.metadata.get("file_path"),
                    "score": float(item.score) if item.score is not None else None,
                    "code": code[:1800], "code_truncated": len(code) > 1800,
                })
            payload = {"query": query, "hits": hits}
            messages.append({
                "role": "tool", "tool_call_id": call["id"],
                "content": json.dumps(payload, ensure_ascii=False),
            })
            record["searches"].append({
                "tool_call_id": call["id"], **payload,
                "elapsed_seconds": round(time.perf_counter() - search_started, 3),
            })
            save()
            print("Query:", query)
            for hit in hits:
                print(" ", hit["rank"], hit["file"], "score=", hit["score"])

        messages.append({"role": "user", "content": (
            "请仅根据以上检索返回的代码，用中文给出最多三个候选文件或函数，"
            "按优先级排列；每项附一小段原样代码证据，并说明它与问题的关系。"
            "这些检索片段可能被截断；没有看到的实现不得当作已验证事实。"
            "若证据不足，请指出下一步需要查看什么。不要编造行号，不再调用工具。"
        )})
        record["status"] = "model_request_started"
        save()
        phase = "model_request"
        print("Sending tool results: one model request, no automatic retries...", flush=True)
        model_started = time.perf_counter()
        final = litellm.completion(
            **settings, messages=messages, tools=first["tools"],
            api_key=os.environ["DEEPSEEK_API_KEY"],
        )
        record["second_elapsed_seconds"] = round(time.perf_counter() - model_started, 3)
        record["response"] = final.model_dump(mode="json")
        record["status"] = "response_received"
        record["resume_elapsed_seconds"] = round(time.perf_counter() - started, 3)
        save()
    except Exception as exc:
        record.update(status="error", error_phase=phase, error_type=type(exc).__name__,
                      http_status=str(getattr(exc, "status_code", "unknown")),
                      resume_elapsed_seconds=round(time.perf_counter() - started, 3))
        save()
        print("Error:", phase, type(exc).__name__, record["http_status"])
        print("Saved:", out)
        print("Stop here; do not delete the record or resend automatically.")
        return 1

    print("Saved:", out)
    print("Returned model:", final.model)
    print("Second usage:", final.usage)
    first_usage = response.get("usage") or {}
    second_usage = record["response"].get("usage") or {}
    total = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        values = [first_usage.get(key), second_usage.get(key)]
        total[key] = sum(values) if all(isinstance(v, int) for v in values) else None
    print("Two-request usage:", json.dumps(total))
    if not final.choices:
        print("No choices; inspect the saved response.")
        return 0
    answer = final.choices[0]
    print("finish_reason:", answer.finish_reason)
    print("Final tool_calls count:", len(answer.message.tool_calls or []))
    print("Localization suggestion (not yet verified):")
    print(answer.message.content or "[empty]")
    if answer.finish_reason != "stop" or answer.message.tool_calls:
        print("Final response needs inspection; do not treat it as a completed answer yet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
