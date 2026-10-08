from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


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


class CreateTask(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_id: str = Field(default='demo-v1', pattern=r'^(demo-v1|prepared-[a-f0-9]{64})$')
    problem_statement: str = Field(strict=True, min_length=1, max_length=8000)
    demo_scenario: DemoScenario = DemoScenario.SUCCESS
    options: TaskOptions = Field(default_factory=TaskOptions)
    timeout_seconds: int = Field(default=90, strict=True, ge=1, le=900)
    max_attempts: int = Field(default=3, strict=True, ge=1, le=5)

    @field_validator('problem_statement')
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('problem_statement must contain text')
        return value


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
