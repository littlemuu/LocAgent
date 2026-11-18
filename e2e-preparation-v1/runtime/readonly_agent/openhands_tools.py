"""Native OpenHands SDK 1.62.0 tools over the existing independent Python API.

No BashTool/FileEditorTool/MCP server or implicit tools are registered here.
One ToolSession is shared within a single case/arm, never between conversations.
"""
from threading import Lock
from typing import ClassVar
from uuid import uuid4

from pydantic import ConfigDict, Field
from openhands.sdk import Action, Observation, Tool, ToolDefinition, register_tool
from openhands.sdk.tool import ToolAnnotations, ToolExecutor

from .core import BASE, RETRIEVE, FileTools, Limits, encoded, page


class CursorAction(Action):
    model_config = ConfigDict(extra='forbid', strict=True)
    offset: int = Field(default=0, ge=0)


class ReadAction(Action):
    model_config = ConfigDict(extra='forbid', strict=True)
    path: str
    start_line: int | None = Field(default=None, ge=1, description="One-based source start line, inclusive. Not a character offset.")
    end_line: int | None = Field(default=None, ge=1, description="One-based source end line, inclusive; defaults to EOF.")
    cursor: str | None = Field(default=None, description="Copy next_cursor from this session and path; omit line bounds or preserve the original range.")


class QueryAction(CursorAction):
    query: str = Field(min_length=1, max_length=256)


class ReadObservation(Observation):
    # Avoid the SDK's extra error prefix silently increasing output bytes.
    @property
    def to_llm_content(self):
        return self.content


class ToolSession:
    def __init__(self, snapshot, *, retriever=None, limits=Limits()):
        self.tools = FileTools(snapshot, retriever)
        self.limits = limits
        self.calls = self.used = 0
        self.closed = False
        self.lock = Lock()
        self.audit = []

    def close_investigation(self):
        """Irreversible session-local fence, independent of model tool_choice."""
        with self.lock:
            self.closed = True

    def execute(self, name, args):
        with self.lock:
            if self.closed or self.calls >= self.limits.max_tool_calls:
                self.closed = True
                result = {'error': 'investigation_closed', 'next': 'finish'}
            else:
                self.calls += 1
                try:
                    result = self.tools.respond(name, args, min(self.limits.page_bytes, self.limits.source_bytes-self.used))
                except Exception as error:
                    result = {'error': 'tool_error', 'error_type': type(error).__name__}
                size = len(encoded(result)) if result is not None else self.limits.source_bytes + 1
                if size > self.limits.source_bytes-self.used:
                    self.closed = True
                    result = {'error': 'investigation_closed', 'next': 'finish'}
                else:
                    self.used += size
                if self.limits.source_bytes-self.used < 64 or self.calls >= self.limits.max_tool_calls:
                    self.closed = True
            self.audit.append({'tool': name, 'arguments': args.copy(), 'result': result,
                               'source_bytes': self.used, 'calls': self.calls})
            return ReadObservation.from_text(encoded(result).decode(), is_error='error' in result)


class ReadExecutor(ToolExecutor):
    def __init__(self, session, name):
        self.session, self.name = session, name

    def __call__(self, action, conversation=None):
        fields = {'list_files': ('offset',), 'read_file': ('path', 'start_line', 'end_line', 'cursor'),
                  'search_text': ('query', 'offset'), 'locagent_retrieve': ('query', 'offset')}
        return self.session.execute(self.name, {f: getattr(action, f) for f in fields[self.name]})


class ReadTool(ToolDefinition):
    action_model: ClassVar[type[Action]] = CursorAction

    @classmethod
    def create(cls, conv_state=None, *, session):
        spec = next(t for t in BASE + [RETRIEVE] if t['name'] == cls.name)
        return [cls(description=spec['description'], action_type=cls.action_model,
                    observation_type=ReadObservation, executor=ReadExecutor(session, cls.name),
                    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                                                idempotentHint=False, openWorldHint=False))]


class ListFilesTool(ReadTool):
    name = 'list_files'


class ReadFileTool(ReadTool):
    name = 'read_file'
    action_model = ReadAction


class SearchTextTool(ReadTool):
    name = 'search_text'
    action_model = QueryAction


class LocAgentRetrieveTool(ReadTool):
    name = 'locagent_retrieve'
    action_model = QueryAction


def register_readonly_tools(session):
    """Register bound instances under unique registry keys; return SDK Tool specs.

    Actual model-visible names remain identical across arms. SDK global registry
    cannot accidentally resolve a different conversation's bound session.
    """
    classes = [ListFilesTool, SearchTextTool, ReadFileTool]
    if session.tools.retriever is not None:
        classes.append(LocAgentRetrieveTool)
    specs = []
    for cls in classes:
        instance = cls.create(session=session)[0]
        key = 'readonly_' + uuid4().hex
        register_tool(key, instance)
        specs.append(Tool(name=key))
    return specs
