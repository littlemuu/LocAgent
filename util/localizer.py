"""Single-run adapter over LocAgent's real graph tools and shared search loop.

This adapter owns the legacy graph globals exclusively while running. It rejects
overlapping adapter calls. Do not run the old CLI/tools concurrently in the same
process; this is deliberately not a thread-safe or sandboxed service boundary.
"""
import ast
from contextlib import contextmanager
from copy import deepcopy
import inspect
import json
import os
from pathlib import Path
import pickle
from threading import Lock
from typing import Any, Callable, Iterator, Protocol

from util.localization_contract import (
    ErrorCode, InvalidRequestError, LocalizationError, LocalizationOptions,
    LocalizationRequest, LocalizationResult, ResultStatus, TokenUsage,
    safe_instance_id, safe_repo_path,
)


class CompletionProvider(Protocol):
    def __call__(self, **kwargs: Any) -> Any: ...


class LiteLLMProvider:
    """Explicit live provider. No model is contacted by constructing it."""

    def __init__(self, timeout: float = 60):
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
            raise InvalidRequestError('provider timeout must be positive')
        self.timeout = timeout

    def __call__(self, **kwargs: Any) -> Any:
        import litellm
        kwargs.setdefault('timeout', self.timeout)
        kwargs.setdefault('num_retries', 0)
        return litellm.completion(**kwargs)


_ENGINE_LOCK = Lock()
_TOOLS = ('search_code_snippets', 'get_entity_contents', 'explore_tree_structure')
_GLOBALS = (
    'CURRENT_ISSUE_ID', 'CURRENT_INSTANCE', 'ALL_FILE', 'ALL_CLASS', 'ALL_FUNC',
    'DP_GRAPH_ENTITY_SEARCHER', 'DP_GRAPH_DEPENDENCY_SEARCHER', 'DP_GRAPH',
    'REPO_SAVE_DIR', 'GRAPH_INDEX_DIR', 'BM25_INDEX_DIR',
    'bm25_content_retrieve', 'setup_repo', 'build_code_retriever',
    'build_module_retriever',
)


@contextmanager
def _local_metadata() -> Iterator[None]:
    # LiteLLM otherwise fetches its price table during import, even with a fake
    # provider. Pin that metadata to its bundled copy and restore the setting.
    key = 'LITELLM_LOCAL_MODEL_COST_MAP'
    previous = os.environ.get(key)
    os.environ[key] = 'True'
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = previous


def _inside(root: Path, name: str) -> Path:
    root = root.resolve()
    path = root / name
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError('path escapes the configured root or is a symlink')
    return path


@contextmanager
def _graph_session(graph: Any, task: dict[str, str], bm25_root: Path | None,
                   module_retriever: Any) -> Iterator[Any]:
    from dependency_graph import RepoDependencySearcher, RepoEntitySearcher
    from dependency_graph.build_graph import (
        NODE_TYPE_CLASS, NODE_TYPE_FILE, NODE_TYPE_FUNCTION, VALID_NODE_TYPES,
    )
    from plugins.location_tools.repo_ops import repo_ops as ops

    # Validate every graph path before running any tools or parsing output.
    try:
        for node, data in graph.nodes(data=True):
            if data.get('type') not in VALID_NODE_TYPES:
                raise ValueError('invalid graph node type')
            if node == '.' and data['type'] == 'directory':
                continue
            safe_repo_path(node.partition(':')[0])
        searcher = RepoEntitySearcher(graph)
        files = searcher.get_all_nodes_by_type(NODE_TYPE_FILE)
        if not files:
            raise ValueError('graph must contain a file node')
    except Exception:
        raise LocalizationError(ErrorCode.INDEX_UNAVAILABLE, 'Invalid prepared graph') from None

    previous = {name: getattr(ops, name) for name in _GLOBALS}

    def no_setup(*args: Any, **kwargs: Any) -> Any:
        raise LocalizationError(
            ErrorCode.INDEX_UNAVAILABLE, 'Prepare indexes before localization',
        )

    def prepared_module(*args: Any, **kwargs: Any) -> Any:
        if module_retriever is None:
            raise LocalizationError(
                ErrorCode.INDEX_UNAVAILABLE, 'Prepared module retriever is unavailable',
            )
        return module_retriever

    def prepared_bm25(*args: Any, **kwargs: Any) -> Any:
        try:
            if bm25_root is None:
                raise ValueError('BM25 root is not configured')
            directory = _inside(bm25_root, task['instance_id'])
            corpus = _inside(directory, 'corpus.jsonl')
            if not corpus.is_file():
                raise ValueError('BM25 corpus is missing')
        except (OSError, ValueError):
            raise LocalizationError(
                ErrorCode.INDEX_UNAVAILABLE, 'Prepared BM25 index is unavailable',
            ) from None
        return previous['bm25_content_retrieve'](*args, **kwargs)

    try:
        ops.CURRENT_ISSUE_ID = task['instance_id']
        ops.CURRENT_INSTANCE = task.copy()
        ops.DP_GRAPH = graph
        ops.DP_GRAPH_ENTITY_SEARCHER = searcher
        ops.DP_GRAPH_DEPENDENCY_SEARCHER = RepoDependencySearcher(graph)
        ops.ALL_FILE = files
        ops.ALL_CLASS = searcher.get_all_nodes_by_type(NODE_TYPE_CLASS)
        ops.ALL_FUNC = searcher.get_all_nodes_by_type(NODE_TYPE_FUNCTION)
        ops.REPO_SAVE_DIR = None
        ops.GRAPH_INDEX_DIR = None
        ops.BM25_INDEX_DIR = str(bm25_root.resolve()) if bm25_root else None
        ops.bm25_content_retrieve = prepared_bm25
        ops.setup_repo = no_setup
        ops.build_code_retriever = no_setup
        ops.build_module_retriever = prepared_module
        yield ops
    finally:
        for name, value in previous.items():
            setattr(ops, name, value)


def _execute_tool(ops: Any, code: str, *, return_records: dict[str, Any],
                  suppress_repeats: bool) -> str:
    # Accept the print(tool(**literal_arguments)) form emitted by ResponseParser.
    # AST inspection and literal_eval never execute model-provided Python code.
    try:
        tree = ast.parse(code)
        if len(tree.body) != 1 or not isinstance(tree.body[0], ast.Expr):
            raise ValueError('one expression required')
        outer = tree.body[0].value
        if (not isinstance(outer, ast.Call) or not isinstance(outer.func, ast.Name)
                or outer.func.id != 'print' or len(outer.args) != 1 or outer.keywords):
            raise ValueError('print(tool(...)) required')
        call = outer.args[0]
        if (not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name)
                or call.func.id not in _TOOLS):
            raise ValueError('tool is not allowed')
        args = [ast.literal_eval(arg) for arg in call.args]
        kwargs: dict[str, Any] = {}
        for keyword in call.keywords:
            if keyword.arg is None:
                values = ast.literal_eval(keyword.value)
                if not isinstance(values, dict) or not all(isinstance(k, str) for k in values):
                    raise ValueError('literal keyword dictionary required')
            else:
                values = {keyword.arg: ast.literal_eval(keyword.value)}
            if kwargs.keys() & values.keys():
                raise ValueError('duplicate keyword')
            kwargs.update(values)
        if any(key.startswith('_') for key in kwargs):
            raise ValueError('internal arguments are not allowed')
        function = getattr(ops, call.func.id)
        inspect.signature(function).bind(*args, **kwargs)
    except (SyntaxError, ValueError, TypeError):
        raise LocalizationError(
            ErrorCode.INVALID_RESPONSE, 'Model returned an unsupported tool call',
        ) from None
    if call.func.id in ('search_code_snippets', 'get_entity_contents'):
        kwargs.update(_return_records=return_records, _suppress_repeats=suppress_repeats)
    try:
        return str(function(*args, **kwargs)) + '\n'
    except LocalizationError:
        raise
    except Exception:
        raise LocalizationError(ErrorCode.EXECUTION_ERROR, 'Graph tool execution failed') from None


def _checked_provider(provider: CompletionProvider) -> CompletionProvider:
    from litellm import Timeout as ProviderTimeout
    from openai import APITimeoutError

    def checked(**kwargs: Any) -> Any:
        try:
            response = provider(**kwargs)
        except (TimeoutError, ProviderTimeout, APITimeoutError):
            raise LocalizationError(ErrorCode.TIMEOUT, 'Provider request timed out') from None
        except Exception:
            raise LocalizationError(ErrorCode.MODEL_ERROR, 'Provider request failed') from None
        try:
            if len(response.choices) != 1:
                raise ValueError('exactly one choice required')
            message = response.choices[0].message
            if message.role != 'assistant' or (
                message.content is not None and not isinstance(message.content, str)
            ):
                raise ValueError('invalid assistant message')
            TokenUsage(response.usage.prompt_tokens, response.usage.completion_tokens)
            if message.tool_calls:
                for call in message.tool_calls:
                    if call.function.name not in (*_TOOLS, 'finish'):
                        raise ValueError('unknown tool')
                    arguments = json.loads(call.function.arguments)
                    if not isinstance(arguments, dict):
                        raise ValueError('tool arguments must be an object')
                    if call.function.name == 'finish' and (
                        set(arguments) != {'thought'}
                        or not isinstance(arguments['thought'], str)
                    ):
                        raise ValueError('finish requires exactly one string thought')
            elif message.content is None:
                raise ValueError('empty response')
        except (AttributeError, TypeError, ValueError, IndexError):
            raise LocalizationError(
                ErrorCode.INVALID_RESPONSE, 'Provider returned an invalid response',
            ) from None
        return response
    return checked


class GraphLocalizer:
    """One attempt against a trusted prepared graph; no downloads or disk writes."""

    def __init__(self, graph_loader: Callable[[LocalizationRequest], Any], *,
                 provider: CompletionProvider, model_name: str,
                 options: LocalizationOptions | None = None,
                 bm25_index_dir: str | Path | None = None,
                 module_retriever: Any = None):
        if not callable(graph_loader) or not callable(provider):
            raise InvalidRequestError('graph_loader and provider must be callable')
        if not isinstance(model_name, str) or not model_name.strip():
            raise InvalidRequestError('model_name must be a nonempty string')
        if options is not None and not isinstance(options, LocalizationOptions):
            raise InvalidRequestError('options must be LocalizationOptions')
        self.graph_loader = graph_loader
        self.provider = provider
        self.model_name = model_name
        self.options = options or LocalizationOptions()
        self.bm25_root = Path(bm25_index_dir) if bm25_index_dir is not None else None
        self.module_retriever = module_retriever

    @classmethod
    def from_graph(cls, graph: Any, **kwargs: Any) -> 'GraphLocalizer':
        return cls(lambda request: graph, **kwargs)

    @classmethod
    def from_index_dir(cls, index_dir: str | Path, **kwargs: Any) -> 'GraphLocalizer':
        # Pickle loading is ONLY for operator-created, trusted local indexes.
        root = Path(index_dir)

        def load(request: LocalizationRequest) -> Any:
            path = _inside(root, safe_instance_id(request.instance_id) + '.pkl')
            with path.open('rb') as stream:
                return pickle.load(stream)

        return cls(load, **kwargs)

    def localize(self, request: LocalizationRequest) -> LocalizationResult:
        if not isinstance(request, LocalizationRequest):
            raise InvalidRequestError('request must be LocalizationRequest')
        task = request.as_task()
        if not _ENGINE_LOCK.acquire(blocking=False):
            raise LocalizationError(ErrorCode.BUSY, 'Graph engine is already in use')
        try:
            with _local_metadata():
                return self._localize(request, task)
        except LocalizationError:
            raise
        except Exception:
            raise LocalizationError(ErrorCode.EXECUTION_ERROR, 'Localization execution failed') from None
        finally:
            _ENGINE_LOCK.release()

    def _localize(self, request: LocalizationRequest, task: dict[str, str]) -> LocalizationResult:
        try:
            graph = deepcopy(self.graph_loader(request))
        except Exception:
            raise LocalizationError(
                ErrorCode.INDEX_UNAVAILABLE, 'Prepared graph is unavailable',
            ) from None
        from util.localization_engine import run_search
        from util.process_output import get_loc_results_from_graph
        from util.prompts.pipelines import auto_search_prompt as prompt
        from util.runtime import function_calling

        with _graph_session(graph, task, self.bm25_root, self.module_retriever) as ops:
            instruction = prompt.TASK_INSTRUECTION.format(
                package_name=task['instance_id'].split('_')[0],
            ) + '\nProblem statement:\n' + task['problem_statement']
            messages = [
                {'role': 'system', 'content': function_calling.SYSTEM_PROMPT},
                {'role': 'user', 'content': instruction},
            ]
            tools = deepcopy(function_calling.get_tools(
                codeact_enable_search_keyword=True, codeact_enable_search_entity=True,
                codeact_enable_tree_structure_traverser=True,
            ))
            # The legacy parser uses the first finish argument as final text.
            # Advertise and enforce one named string without changing CLI tools.
            tools[0]['function']['parameters'] = {
                'type': 'object',
                'properties': {'thought': {'type': 'string'}},
                'required': ['thought'],
                'additionalProperties': False,
            }
            run = run_search(
                model_name=self.model_name, messages=messages,
                fake_user_msg=prompt.FAKE_USER_MSG_FOR_LOC, tools=tools,
                max_iteration_num=self.options.max_iterations,
                suppress_repeats=self.options.suppress_repeats,
                provider=_checked_provider(self.provider),
                execute_tool=lambda code, **kw: _execute_tool(ops, code, **kw),
            )
            trajectory = run.trajectory
            if trajectory['termination_reason'] == 'iteration_limit':
                status = ResultStatus.ITERATION_LIMIT
                files, modules, entities = [], [], []
            else:
                try:
                    all_files, all_modules, all_entities = get_loc_results_from_graph(
                        graph, [run.raw_output],
                    )
                    files, modules, entities = all_files[0], all_modules[0], all_entities[0]
                    if run.raw_output.strip('` \n') and not files:
                        raise ValueError('unrecognized final locations')
                except Exception:
                    raise LocalizationError(
                        ErrorCode.INVALID_RESPONSE, 'Model returned invalid final locations',
                    ) from None
                status = ResultStatus.SUCCESS if files else ResultStatus.EMPTY
            return LocalizationResult(
                instance_id=task['instance_id'], status=status,
                found_files=files, found_modules=modules, found_entities=entities,
                iterations=trajectory['iterations'], usage=TokenUsage(**trajectory['usage']),
                raw_output=run.raw_output, return_records=deepcopy(trajectory['return_records']),
                messages=deepcopy(run.messages),
            )


def write_result(result: LocalizationResult, output_root: str | Path) -> Path:
    """Explicit, exclusive JSON export under a caller-configured trusted root.

    Linux/WSL dir_fd and O_NOFOLLOW pin the output directory and reject symlinks.
    Existing files are never replaced. Localization itself never calls this.
    """
    directory_fd = None
    created = False
    try:
        if not isinstance(result, LocalizationResult):
            raise ValueError('result must be LocalizationResult')
        payload = json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + '\n'
        name = safe_instance_id(result.instance_id) + '.json'
        root = Path(output_root)
        root.mkdir(parents=True, exist_ok=True)
        directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=directory_fd)
        created = True
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(payload)
        return root / name
    except (OSError, TypeError, ValueError, LocalizationError):
        if created and directory_fd is not None:
            os.unlink(name, dir_fd=directory_fd)
        raise LocalizationError(ErrorCode.OUTPUT_ERROR, 'Result export failed') from None
    finally:
        if directory_fd is not None:
            os.close(directory_fd)
