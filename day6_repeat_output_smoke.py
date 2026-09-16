import io
import pickle
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path
from queue import Queue
from unittest.mock import patch

import auto_search_main as main
from litellm import ModelResponse
from day5_main_trace_smoke import make_tool_response
from dependency_graph import RepoEntitySearcher
from dependency_graph.build_graph import (
    NODE_TYPE_FILE, NODE_TYPE_CLASS, NODE_TYPE_FUNCTION,
)
from plugins.location_tools.repo_ops import repo_ops


# 使用已经保存的真实图，不重新建图。
graph_path = Path("outputs/day1/graphs/psf__requests-3362.pkl")
with graph_path.open("rb") as file:
    graph = pickle.load(file)

searcher = RepoEntitySearcher(graph)
repo_ops.DP_GRAPH = graph
repo_ops.DP_GRAPH_ENTITY_SEARCHER = searcher
repo_ops.ALL_FILE = searcher.get_all_nodes_by_type(NODE_TYPE_FILE)
repo_ops.ALL_CLASS = searcher.get_all_nodes_by_type(NODE_TYPE_CLASS)
repo_ops.ALL_FUNC = searcher.get_all_nodes_by_type(NODE_TYPE_FUNCTION)

entity = "requests/models.py:Response.iter_content"
assert entity in graph

tools = main.function_calling.get_tools(
    codeact_enable_search_keyword=True,
    codeact_enable_search_entity=True,
)


def run_case(enabled):
    responses = iter([
        make_tool_response(
            "search_code_snippets",
            {"search_terms": [entity]},
            "day6_search",
        ),
        make_tool_response(
            "get_entity_contents",
            {"entity_names": [entity]},
            "day6_read",
        ),
        ModelResponse(
            model="offline-test",
            choices=[{
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": "离线验证结束。<finish></finish>",
                },
            }],
            usage={
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        ),
    ])
    sent_messages = []

    def fake_request(**kwargs):
        # 保存每次请求实际携带的消息，避免后续追加影响检查。
        sent_messages.append(deepcopy(kwargs["messages"]))
        return next(responses)

    result_queue = Queue()
    with (
        patch.object(main, "request_model", side_effect=fake_request),
        patch.object(
            main.litellm,
            "completion",
            side_effect=AssertionError("离线检查禁止请求真实模型"),
        ),
        redirect_stdout(io.StringIO()),
    ):
        main.auto_search_process(
            result_queue=result_queue,
            model_name="openai/deepseek-v4-flash",
            messages=[{"role": "user", "content": "离线重复输出对照"}],
            fake_user_msg="请继续。",
            tools=tools,
            max_iteration_num=4,
            suppress_repeats=enabled,
        )

    _, _, traj = result_queue.get(timeout=1)
    assert traj["termination_reason"] == "finished"
    assert len(sent_messages) == 3

    # 第三次请求应该已经携带前两次工具的结果。
    observations = [
        message["content"]
        for message in sent_messages[-1]
        if message["role"] == "tool"
    ]
    assert len(observations) == 2

    history = traj["return_records"][entity]
    assert len(history) == 2
    assert [entry["repeated"] for entry in history] == [False, True]
    assert [
        entry["previously_in_context"] for entry in history
    ] == [False, True]
    assert history[0]["in_context"] is True

    for entry, observation in zip(history, observations):
        assert entry["output_content"] in observation

    return history, observations


off_history, off_messages = run_case(False)
on_history, on_messages = run_case(True)

# 关闭开关：两次都保留正文。
assert all("def iter_content(" in text for text in off_messages)
assert all(
    entry["output_content"] == entry["content"]
    for entry in off_history
)

# 打开开关：首次原样返回，第二次省略。
assert on_messages[0] == off_messages[0]
assert "Repeated content for" in on_messages[1]
assert "def iter_content(" not in on_messages[1]
assert len(on_messages[1]) < len(off_messages[1])

# 账本仍保留完整原文。
assert [
    entry["content"] for entry in on_history
] == [
    entry["content"] for entry in off_history
]

print("通过：开关关闭时，两次返回完整正文")
print("通过：开关打开时，首次正文不变，第二次替换为提示")
print("通过：替代结果确实进入了下一次模型请求的消息")
print("通过：账本仍保留完整原文")
print("第二次工具消息字符数：", len(off_messages[1]), "→", len(on_messages[1]))
print("实际替代消息：")
print(on_messages[1])