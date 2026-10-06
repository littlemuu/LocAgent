from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import PurePosixPath
import re
from typing import Any


class ErrorCode(str, Enum):
    INVALID_REQUEST = 'invalid_request'
    INDEX_UNAVAILABLE = 'index_unavailable'
    MODEL_ERROR = 'model_error'
    TIMEOUT = 'timeout'
    INVALID_RESPONSE = 'invalid_response'
    EXECUTION_ERROR = 'execution_error'
    BUSY = 'busy'
    OUTPUT_ERROR = 'output_error'


class LocalizationError(Exception):
    """Stable public error; provider exception text is never exposed here."""

    def __init__(self, code: ErrorCode, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def to_dict(self) -> dict[str, str]:
        return {'code': self.code.value, 'message': self.message}


class InvalidRequestError(LocalizationError, ValueError):
    def __init__(self, message: str):
        super().__init__(ErrorCode.INVALID_REQUEST, message)


def safe_instance_id(value: str) -> str:
    """Return a filename component without changing the original request."""
    if not isinstance(value, str):
        raise InvalidRequestError('instance_id must be a string')
    canonical = value.strip()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', canonical):
        raise InvalidRequestError('instance_id must be a safe filename component')
    if canonical.endswith('.'):
        raise InvalidRequestError('instance_id must not end with a dot')
    if canonical.split('.')[0].upper() in {
        'CON', 'PRN', 'AUX', 'NUL',
        *{f'COM{i}' for i in range(1, 10)},
        *{f'LPT{i}' for i in range(1, 10)},
    }:
        raise InvalidRequestError('instance_id must not be a reserved filename')
    return canonical


def safe_repo_path(value: str) -> str:
    """Validate paths in graph/results; these are repository-relative names."""
    if not isinstance(value, str) or not value:
        raise ValueError('repository path must be a nonempty string')
    if '\\' in value or ':' in value or any(ord(c) < 32 for c in value):
        raise ValueError('repository path contains forbidden characters')
    path = PurePosixPath(value)
    if path.is_absolute() or any(p in ('', '.', '..') for p in value.split('/')):
        raise ValueError('repository path must stay inside the repository')
    return value


@dataclass
class LocalizationRequest:
    instance_id: str
    repo: str
    base_commit: str
    problem_statement: str

    def __post_init__(self):
        for name in ('instance_id', 'repo', 'base_commit', 'problem_statement'):
            if not isinstance(getattr(self, name), str):
                raise InvalidRequestError(f'{name} must be a string')
        # Keep the user's four nonempty checks and original string values.
        if not self.instance_id.strip():
            raise InvalidRequestError('instance_id cannot be empty')
        if not self.repo.strip():
            raise InvalidRequestError('repo cannot be empty')
        if not self.base_commit.strip():
            raise InvalidRequestError('base_commit cannot be empty')
        if not self.problem_statement.strip():
            raise InvalidRequestError('problem_statement cannot be empty')
        safe_instance_id(self.instance_id)
        component = r'[A-Za-z0-9][A-Za-z0-9_.-]*'
        if not re.fullmatch(component + '/' + component, self.repo.strip()):
            raise InvalidRequestError('repo must be owner/name')
        if not re.fullmatch(r'[0-9a-fA-F]{40}', self.base_commit.strip()):
            raise InvalidRequestError('base_commit must be a full 40-digit SHA')

    def as_task(self) -> dict[str, str]:
        self.__post_init__()  # Revalidate a dataclass mutated after construction.
        return {
            'instance_id': safe_instance_id(self.instance_id),
            'repo': self.repo.strip(),
            'base_commit': self.base_commit.strip(),
            'problem_statement': self.problem_statement,
        }


@dataclass(frozen=True)
class LocalizationOptions:
    max_iterations: int = 6
    suppress_repeats: bool = False

    def __post_init__(self):
        if type(self.max_iterations) is not int or not 1 <= self.max_iterations <= 100:
            raise InvalidRequestError('max_iterations must be an integer from 1 to 100')
        if type(self.suppress_repeats) is not bool:
            raise InvalidRequestError('suppress_repeats must be a boolean')


class ResultStatus(str, Enum):
    SUCCESS = 'success'
    EMPTY = 'empty'
    ITERATION_LIMIT = 'iteration_limit'


@dataclass(frozen=True)
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def __post_init__(self):
        for value in (self.prompt_tokens, self.completion_tokens):
            if type(value) is not int or value < 0:
                raise ValueError('token counts must be nonnegative integers')


@dataclass
class LocalizationResult:
    instance_id: str
    status: ResultStatus
    found_files: list[str] = field(default_factory=list)
    found_modules: list[str] = field(default_factory=list)
    found_entities: list[str] = field(default_factory=list)
    iterations: int = 0
    usage: TokenUsage = field(default_factory=TokenUsage)
    raw_output: str = ''
    return_records: dict[str, Any] = field(default_factory=dict)
    messages: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        if safe_instance_id(self.instance_id) != self.instance_id:
            raise ValueError('result instance_id must be canonical')
        if not isinstance(self.status, ResultStatus):
            raise ValueError('status must be a ResultStatus')
        for values in (self.found_files, self.found_modules, self.found_entities):
            if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
                raise ValueError('locations must be lists of strings')
        for path in self.found_files:
            safe_repo_path(path)
        for entity in self.found_modules + self.found_entities:
            safe_repo_path(entity.partition(':')[0])
        if type(self.iterations) is not int or self.iterations < 0:
            raise ValueError('iterations must be nonnegative')
        if not isinstance(self.usage, TokenUsage) or not isinstance(self.raw_output, str):
            raise ValueError('usage and raw_output have invalid types')
        if self.status == ResultStatus.SUCCESS and not self.found_files:
            raise ValueError('success requires at least one found file')
        if self.status != ResultStatus.SUCCESS and (
            self.found_files or self.found_modules or self.found_entities
        ):
            raise ValueError('empty and iteration_limit cannot contain final locations')

    def to_dict(self) -> dict[str, Any]:
        self.__post_init__()
        result = asdict(self)
        result['status'] = self.status.value
        return result
