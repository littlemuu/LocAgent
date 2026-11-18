import json

# 先导入主程序，沿用其中已处理好的代理环境。
import auto_search_main as main
from litellm import ModelResponse

import pickle
from pathlib import Path
from queue import Queue
from unittest.mock import patch

from dependency_graph import RepoEntitySearcher
from dependency_graph.build_graph import (
    NODE_TYPE_FILE, NODE_TYPE_CLASS, NODE_TYPE_FUNCTION,
)
from plugins.location_tools.repo_ops import repo_ops

from copy import deepcopy
from tempfile import mkdtemp

from types import SimpleNamespace
from threading import Lock

import util.process_output as process_output


def make_tool_response(name, arguments, call_id):
    return ModelResponse(
        model="offline-test",
        choices=[{
            "index": 0,
            "finish_reason": "tool_calls",
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": json.dumps(arguments),
                    },
                }],
            },
        }],
        usage={
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    )


if __name__ == "__main__":
    response = make_tool_response(
        "get_entity_contents",
        {"entity_names": ["requests/models.py:Response.iter_content"]},
        "offline_read_1",
    )

    actions = main.ResponseParser().parse(response)
    assert len(actions) == 1
    action = actions[0]
    assert action.action_type == main.ActionType.RUN_IPYTHON
    assert action.tool_call_id == "offline_read_1"

    print("解析出的代码：", action.code)
    print("通过：预设响应被识别为工具执行动作")

        # 1. 加载昨天用过的真实图，准备工具环境。
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

    # 2. 准备三轮响应；第三轮用解析器支持的结束标签。
    responses = [
        make_tool_response(
            "search_code_snippets",
            {"search_terms": [entity]},
            "offline_search_1",
        ),
        make_tool_response(
            "get_entity_contents",
            {"entity_names": [entity]},
            "offline_read_2",
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
    ]

    tools = main.function_calling.get_tools(
        codeact_enable_search_keyword=True,
        codeact_enable_search_entity=True,
    )
    result_queue = Queue()

    # 3. 临时替换模型请求函数，依次返回预设响应。
    with patch.object(
        main, "request_model", side_effect=responses
    ) as fake_request, patch.object(
        main.litellm,
        "completion",
        side_effect=AssertionError("离线测试不应请求真实模型"),
    ):
        main.auto_search_process(
            result_queue=result_queue,
            model_name="openai/deepseek-v4-flash",
            messages=[{"role": "user", "content": "离线工具记录测试"}],
            fake_user_msg="请继续。",
            tools=tools,
            max_iteration_num=4,
        )
        assert fake_request.call_count == 3

    # 4. 检查主循环返回的账本，以及实际回传的工具结果。
    final_output, messages, traj = result_queue.get(timeout=1)
    history = traj["return_records"][entity]
    flags = [item["repeated"] for item in history]

    assert flags == [False, True], flags
    assert history[0]["content"] == history[1]["content"]
    assert "def iter_content(" in history[0]["content"]
    assert traj["termination_reason"] == "finished"
    assert traj["iterations"] == 3

    tool_messages = [msg for msg in messages if msg["role"] == "tool"]
    assert [msg["tool_call_id"] for msg in tool_messages] == [
        "offline_search_1", "offline_read_2",
    ]
    for entry, message in zip(history, tool_messages):
        assert entry["content"] in message["content"]

    print("主循环重复标记：", flags)
    print("结束原因：", traj["termination_reason"])
    print("通过：三轮主循环、真实工具执行、账本累积、工具结果回传")

        # 5. 使用主程序同款 JSONL 写入、读取函数。
    # 每次运行创建独立目录，保留之前的测试产物。
    output_root = Path("outputs/day5")
    output_root.mkdir(parents=True, exist_ok=True)
    run_dir = Path(mkdtemp(prefix="trace-", dir=str(output_root)))
    saved_path = run_dir / "saved_traj.jsonl"

    main.append_to_jsonl(traj, str(saved_path))
    saved_rows = main.load_jsonl(str(saved_path))
    assert len(saved_rows) == 1

    loaded_traj = saved_rows[0]
    assert loaded_traj == traj, "写入、读取后的轨迹不一致"

    # 保留对照，稍后检查恢复运行有没有改动旧轨迹。
    old_snapshot = deepcopy(loaded_traj)

    # messages 也要独立复制，因为主循环会向它追加消息。
    resume_messages = deepcopy(loaded_traj["messages"])
    resume_responses = [
        make_tool_response(
            "get_entity_contents",
            {"entity_names": [entity]},
            "offline_resume_read_1",
        ),
        deepcopy(responses[-1]),  # 复用前面的结束响应格式
    ]
    resume_queue = Queue()

    # 6. 把加载的旧轨迹明确传回真实主循环。
    with patch.object(
        main, "request_model", side_effect=resume_responses
    ) as fake_request, patch.object(
        main.litellm,
        "completion",
        side_effect=AssertionError("离线测试不应请求真实模型"),
    ):
        main.auto_search_process(
            result_queue=resume_queue,
            model_name="openai/deepseek-v4-flash",
            messages=resume_messages,
            fake_user_msg="请继续。",
            tools=loaded_traj["tools"],
            traj_data=loaded_traj,
            max_iteration_num=3,
        )
        assert fake_request.call_count == 2

    _, resumed_messages, resumed_traj = resume_queue.get(timeout=1)

    # 7. 历史必须延续，新读取必须识别为重复。
    resumed_history = resumed_traj["return_records"][entity]
    resumed_flags = [item["repeated"] for item in resumed_history]

    assert resumed_flags == [False, True, True], resumed_flags
    assert resumed_history[:2] == old_snapshot["return_records"][entity]
    assert resumed_history[2]["content"] == resumed_history[1]["content"]
    assert resumed_traj["termination_reason"] == "finished"
    assert resumed_traj["iterations"] == 2

    # 旧消息保留，新增读取请求、工具结果、结束回复共三条。
    old_messages = old_snapshot["messages"]
    assert resumed_traj["messages"][:len(old_messages)] == old_messages
    assert len(resumed_traj["messages"]) == len(old_messages) + 3
    assert resumed_messages == resumed_traj["messages"]

    # 检查整个旧轨迹，包括消息列表与账本。
    assert loaded_traj == old_snapshot, "恢复执行修改了传入的旧轨迹"
    assert main.load_jsonl(str(saved_path))[0] == old_snapshot

    print("保存位置：", saved_path)
    print("恢复后的重复标记：", resumed_flags)
    print("通过：文件保存与加载、历史延续、旧轨迹保持不变")

        # 8. 不传旧轨迹，开启全新的尝试。
    resumed_snapshot = deepcopy(resumed_traj)
    fresh_queue = Queue()
    fresh_responses = [
        make_tool_response(
            "get_entity_contents",
            {"entity_names": [entity]},
            "offline_fresh_read_1",
        ),
        deepcopy(responses[-1]),
    ]

    with patch.object(
        main, "request_model", side_effect=fresh_responses
    ) as fake_request, patch.object(
        main.litellm,
        "completion",
        side_effect=AssertionError("离线测试不应请求真实模型"),
    ):
        main.auto_search_process(
            result_queue=fresh_queue,
            model_name="openai/deepseek-v4-flash",
            messages=[{"role": "user", "content": "一次全新的尝试"}],
            fake_user_msg="请继续。",
            tools=tools,
            traj_data=None,
            max_iteration_num=3,
        )
        assert fake_request.call_count == 2

    _, _, fresh_traj = fresh_queue.get(timeout=1)
    fresh_history = fresh_traj["return_records"][entity]
    fresh_flags = [item["repeated"] for item in fresh_history]

    assert fresh_flags == [False], fresh_flags
    assert fresh_history[0]["content"] == resumed_history[-1]["content"]
    assert fresh_traj["termination_reason"] == "finished"
    assert resumed_traj == resumed_snapshot, "新尝试修改了上一次的轨迹"
    assert loaded_traj == old_snapshot, "新尝试修改了最初加载的轨迹"

    print("新尝试的重复标记：", fresh_flags)
    print("通过：新尝试独立记账，已有轨迹未被修改")

        # 9. 准备独立输出目录和真实任务元数据。
    outer_dir = run_dir / "outer"
    outer_dir.mkdir()

    with Path("outputs/day1/task.json").open(encoding="utf-8") as file:
        task = json.load(file)

    assert task["instance_id"] == graph_path.stem

    bug_queue = Queue()
    bug_queue.put({
        key: task[key]
        for key in ("instance_id", "repo", "base_commit", "problem_statement")
    })

    args = SimpleNamespace(
        log_level="WARNING",
        num_samples=1,
        max_attempt_num=1,
        use_function_calling=True,
        use_example=False,
        simple_desc=True,
        model="openai/deepseek-v4-flash",
        timeout=30,
        output_folder=str(outer_dir),
        output_file=str(outer_dir / "loc_outputs.jsonl"),
    )

    # 外层还要解析最终定位结果，因此提供符合格式的预设答案。
    outer_responses = deepcopy(responses)
    outer_responses[-1].choices[0].message.content = (
        "```\n"
        "requests/models.py\n"
        "function: Response.iter_content\n"
        "```\n"
        "<finish></finish>"
    )

    graph_dir = str(graph_path.parent.resolve())
    logger = main.logging.getLogger()
    previous_handlers = logger.handlers[:]
    previous_level = logger.level

    try:
        with (
            patch.object(repo_ops, "GRAPH_INDEX_DIR", graph_dir),
            patch.object(process_output, "GRAPH_INDEX_DIR", graph_dir),
            patch.object(
                main, "request_model", side_effect=outer_responses
            ),
            patch.object(
                main.litellm,
                "completion",
                side_effect=AssertionError("离线测试不应请求真实模型"),
            ),
        ):
            main.run_localize(
                rank=0,
                args=args,
                bug_queue=bug_queue,
                log_queue=Queue(),
                output_file_lock=Lock(),
                traj_file_lock=Lock(),
            )
    finally:
        logger.handlers = previous_handlers
        logger.setLevel(previous_level)

    # 10. 检查由真实外层保存的文件。
    assert not (outer_dir / "failed_attempts.jsonl").exists(), outer_dir
    assert not (outer_dir / "incomplete_trajs.jsonl").exists(), outer_dir

    outer_path = outer_dir / "loc_trajs.jsonl"
    assert outer_path.exists(), f"外层没有保存轨迹：{outer_dir}"

    outer_rows = main.load_jsonl(str(outer_path))
    assert len(outer_rows) == 1
    outer_row = outer_rows[0]
    assert outer_row["instance_id"] == task["instance_id"]
    assert outer_row["found_entities"] == [[entity]]

    saved_attempts = outer_row["loc_trajs"]["trajs"]
    assert len(saved_attempts) == 1
    saved_attempt = saved_attempts[0]

    assert saved_attempt["termination_reason"] == "finished"
    assert saved_attempt["iterations"] == 3
    assert saved_attempt["return_records"] == traj["return_records"]

    outer_flags = [
        item["repeated"]
        for item in saved_attempt["return_records"][entity]
    ]
    print("外层保存位置：", outer_path)
    print("外层保存的重复标记：", outer_flags)
    print("通过：真实子进程、队列回传、定位解析、外层轨迹写盘")