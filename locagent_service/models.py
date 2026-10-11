from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer, model_validator, ValidationInfo


class DemoScenario(str, Enum):
    SUCCESS = 'success'
    EMPTY = 'empty'
    ITERATION_LIMIT = 'iteration_limit'
    PROVIDER_ERROR = 'provider_error'


class TaskStatus(str, Enum):
    QUEUED = 'queued'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'
    CANCELLED = 'cancelled'
    NEEDS_REVIEW = 'needs_review'


class TaskOptions(BaseModel):
    model_config = ConfigDict(extra='forbid')
    max_iterations: int = Field(default=6, strict=True, ge=1, le=12)
    suppress_repeats: bool = Field(default=True, strict=True)


class TaskRequest(BaseModel):
    """Bounded wire/storage shape; new HTTP sources are admitted inside store.create."""
    model_config = ConfigDict(extra='forbid')
    source_id: str = Field(default='demo-v1', pattern=r'^(demo-v1|prepared-[a-f0-9]{64})$')
    problem_statement: str = Field(strict=True, min_length=1, max_length=32768)
    demo_scenario: DemoScenario = DemoScenario.SUCCESS
    options: TaskOptions = Field(default_factory=TaskOptions)
    timeout_seconds: int = Field(default=90, strict=True, ge=1, le=900)
    max_attempts: int = Field(default=3, strict=True, ge=1, le=5)

    @field_validator('problem_statement')
    @classmethod
    def nonblank(cls, value: str, info: ValidationInfo) -> str:
        if not value.strip():
            raise ValueError('problem_statement must contain text')
        if len(value) > 8000 and info.data.get('source_id') == 'demo-v1':
            raise ValueError('Ordinary requests are limited to 8000 characters')
        return value


class CreateTask(TaskRequest):
    @model_validator(mode='after')
    def verified_long_source(self, info: ValidationInfo):
        # Only database deserialization supplies this internal context; HTTP JSON cannot.
        if len(self.problem_statement) > 8000 and not (info.context or {}).get('persisted_task'):
            from locagent_service.sources import validate_source
            try:
                validate_source(self)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise ValueError('Long input requires a verified exact prepared source') from exc
        return self


class PublicError(BaseModel):
    code: str
    message: str


class TokenUsageView(BaseModel):
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)


class LocalizationResultView(BaseModel):
    instance_id: str
    status: Literal['success', 'empty', 'iteration_limit']
    found_files: list[str]
    found_modules: list[str]
    found_entities: list[str]
    iterations: int = Field(ge=0)
    usage: TokenUsageView
    raw_output: str
    return_records: dict[str, Any]
    messages: list[dict[str, Any]]
    diagnostics: dict[str, Any] | None = None

    @model_serializer(mode='wrap')
    def serialize_result(self, handler):
        value = handler(self)
        if self.diagnostics is None:
            value.pop('diagnostics', None)
        return value


class TaskView(BaseModel):
    id: UUID
    status: TaskStatus
    request: CreateTask
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    worker_id: str | None
    result: LocalizationResultView | None
    error: PublicError | None
    attempt: int = 0
    lease_until: datetime | None = None
    deadline: datetime | None = None


class ErrorResponse(BaseModel):
    error: PublicError
