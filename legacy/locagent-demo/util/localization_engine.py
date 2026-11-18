"""Shared single-attempt search loop; providers and tools are injected."""
import ast
import logging
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, List

from litellm import Message as LiteLLMMessage
from util.actions.action import ActionType
from util.actions.action_parser import ResponseParser
from util.return_trace import mark_returns_in_context, refresh_returns_in_context
from util.runtime.fn_call_converter import (
    convert_fncall_messages_to_non_fncall_messages,
    convert_non_fncall_messages_to_fncall_messages,
    STOP_WORDS as NON_FNCALL_STOP_WORDS,
)
from util.utils import convert_to_json


@dataclass
class SearchRun:
    raw_output: str
    messages: list[dict[str, Any]]
    trajectory: dict[str, Any]


def run_search(
    model_name: str, messages: list[dict[str, Any]], fake_user_msg: str, *,
    provider: Callable[..., Any], execute_tool: Callable[..., str],
    tools: Any = None, traj_data: dict[str, Any] | None = None,
    temp: float = 1.0, max_iteration_num: int = 6,
    use_function_calling: bool = True, suppress_repeats: bool = False,
) -> SearchRun:
    if tools and ('hosted_vllm' in model_name or 'qwen' in model_name.lower()
    #             #   or model_name=='azure/gpt-4o'
    #             #   or model_name == 'litellm_proxy/o3-mini-2025-01-31'
                ):
        use_function_calling = False

    # for LLM which do not support function calling
    if not use_function_calling:
        # 转换message
        messages = convert_fncall_messages_to_non_fncall_messages(messages, tools, add_in_context_learning_example=False)

    # code_history = []
    parser = ResponseParser()
    if not traj_data:
        traj_msgs = messages.copy()
        prompt_tokens = 0
        completion_tokens = 0
    else:
        # continue from last traj
        traj_msgs = deepcopy(traj_data['messages'])
        prompt_tokens = traj_data['usage']['prompt_tokens']
        completion_tokens = traj_data['usage']['completion_tokens']

    # traj_data 是传进来的旧运行记录
    if traj_data:
        return_records = deepcopy(traj_data.get("return_records", {}))
        refresh_returns_in_context(return_records, messages)
    else:
        return_records = {}

    cur_interation_num = 0
    last_message = None
    finish = False
    final_output = ""
    while not finish and cur_interation_num < max_iteration_num:
        cur_interation_num += 1
        if cur_interation_num == max_iteration_num:
            messages.append({
                'role': 'user',
                'content': 'The Maximum number of interation has been reached, please generate your final output with required format and use <finish></finish> to exit.'
            })
            traj_msgs.append({
                'role': 'user',
                'content': 'The Maximum number of interation has been reached, please generate your final output with required format and use <finish></finish> to exit.'
            })

        # new conversation
        if tools and ('hosted_vllm' in model_name or 'qwen' in model_name.lower()):
            messages = convert_fncall_messages_to_non_fncall_messages(messages, tools, add_in_context_learning_example=False)
            response = provider(
                model=model_name,
                temperature=temp, top_p=0.8, repetition_penalty=1.05,
                messages=messages,
                stop=NON_FNCALL_STOP_WORDS
            )
        elif tools:
            response = provider(
                model=model_name,
                tools=tools,
                messages=messages,
                temperature=temp,
                # stop=['</execute_ipython>'], #</finish>',
            )
        else:
            response = provider(
                model=model_name,
                messages=messages,
                temperature=temp,
                stop=['</execute_ipython>'], #</finish>',
            )
        prompt_tokens += response.usage.prompt_tokens
        completion_tokens += response.usage.completion_tokens
        if (
            last_message
            and not response.choices[0].message.tool_calls
            and response.choices[0].message.content == last_message
        ):
            messages.append({
                "role": "user",
                "content": "OBSERVATION:\n" + "Don't repeat your response.\n" + fake_user_msg,
            })
            traj_msgs.append({
                "role": "user",
                "content": "OBSERVATION:\n" + "Don't repeat your response.\n" + fake_user_msg,
            })
            continue

        raw_response = deepcopy(response)
        # logging.info('response.choices[0].message')
        if (
            tools
            and model_name != "openai/deepseek-v4-flash"
            and not response.choices[0].message.tool_calls
            and (
                'hosted_vllm' in model_name
                or 'qwen' in model_name.lower()
                or 'deepseek' in model_name
            )
        ):
            try:
                non_fncall_response_message = response.choices[0].message
                fn_call_messages_with_response = (
                    convert_non_fncall_messages_to_fncall_messages(
                        [non_fncall_response_message], tools # messages +
                    )
                )
                fn_call_response_message = fn_call_messages_with_response[-1]
                if not isinstance(fn_call_response_message, LiteLLMMessage):
                    fn_call_response_message = LiteLLMMessage(
                        **fn_call_response_message
                    )
                response.choices[0].message = fn_call_response_message
            except:
                logging.info('convert none fncall messages failed.')
                continue

        last_message = response.choices[0].message.content
        print(response.choices[0].message)
        messages.append(convert_to_json(raw_response.choices[0].message))
        traj_msgs.append(convert_to_json(raw_response.choices[0].message))

        actions = parser.parse(response)
        if not isinstance(actions, List):
            actions = [actions]
        for action in actions:
            logging.debug(action.action_type)
            if action.action_type == ActionType.FINISH:
                final_output = action.thought
                logging.info('='*15)
                logging.info("\nFinal Response:=\n" + final_output)
                finish = True # break
            elif action.action_type == ActionType.MESSAGE:
                logging.debug("thought:\n" + action.content)
                # check if enough
                messages.append({"role": "user", "content": fake_user_msg})
                traj_msgs.append({"role": "user", "content": fake_user_msg})
                # continue
            elif action.action_type == ActionType.RUN_IPYTHON:
                ipython_code = action.code.strip('`')
                logging.info(f"Executing code:\n```\n{ipython_code}\n```")
                function_response = execute_tool(
                    ipython_code, return_records=return_records, suppress_repeats=suppress_repeats
                )
                try:
                    function_response = ast.literal_eval(function_response)
                except (SyntaxError, ValueError):
                    function_response = function_response
                if not isinstance(function_response, str):
                    function_response = str(function_response)

                logging.info("OBSERVATION:\n" + function_response)
                if not tools:
                    messages.append({
                        "role": "user",
                        "content": "OBSERVATION:\n" + function_response,
                    })
                    traj_msgs.append({
                        "role": "user",
                        "content": "OBSERVATION:\n" + function_response,
                    })
                else:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": action.tool_call_id,
                        "name": action.function_name,
                        "content": "OBSERVATION:\n" + function_response,
                    })
                    traj_msgs.append({
                        "role": "tool",
                        "tool_call_id": action.tool_call_id,
                        "name": action.function_name,
                        "content": "OBSERVATION:\n" + function_response,
                    })

                mark_returns_in_context(
                    return_records, messages[-1]["content"]
                )
            else:
                logging.warning('Error Action!')
                # return

    # save traj
    traj_data = {
        'messages': traj_msgs,
        'tools': tools,
        'termination_reason': 'finished' if finish else 'iteration_limit',
        'iterations': cur_interation_num,
        'usage': {
            'prompt_tokens': prompt_tokens,
            'completion_tokens': completion_tokens
        },
        'return_records': return_records,
    }
    # return final_output, messages, traj_data
    return SearchRun(final_output, messages, traj_data)
