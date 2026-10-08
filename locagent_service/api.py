"""HTTP entry point: validate, persist, return immediately; never run LocAgent."""
import argparse
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI, Request, Response, Header
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
import psycopg
import uvicorn

from locagent_service.config import Settings
from locagent_service.models import CreateTask, ErrorResponse, TaskView
from locagent_service.store import TaskStore, StateConflict, IdempotencyConflict


def error_response(status: int, code: str, message: str):
    return JSONResponse(status_code=status, content={'error': {'code': code, 'message': message}})


def create_app(settings: Settings | None = None) -> FastAPI:
    store = TaskStore(settings or Settings.from_env())

    @asynccontextmanager
    async def lifespan(app):
        # Schema initialization is an explicit operator command, not a HTTP action.
        store.check_ready()
        yield

    app = FastAPI(title='LocAgent asynchronous demo', version='0.3', lifespan=lifespan)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        return error_response(422, 'invalid_request', 'Request fields or values are invalid')

    @app.exception_handler(psycopg.Error)
    async def database_error(request: Request, exc: psycopg.Error):
        return error_response(503, 'database_unavailable', 'Task storage is temporarily unavailable')

    @app.exception_handler(StateConflict)
    async def state_conflict(request: Request, exc: StateConflict):
        code = 'idempotency_conflict' if isinstance(exc, IdempotencyConflict) else 'state_conflict'
        return error_response(409, code, 'Task state or idempotency key conflicts')

    @app.get('/health')
    def health():
        store.check_ready()
        return {'status': 'ok', 'schema_version': 2}

    @app.post('/tasks', response_model=TaskView, status_code=202,
              responses={422: {'model': ErrorResponse}, 503: {'model': ErrorResponse}})
    def submit(request: CreateTask, response: Response,
               idempotency_key: str | None = Header(default=None, pattern=r'^[A-Za-z0-9_.:-]{1,128}$')):
        from locagent_service.sources import validate_source
        try:
            if request.source_id != 'demo-v1':
                task = store.create(request, idempotency_key, validate_new=validate_source)
            else:
                task = store.create(request, idempotency_key) if idempotency_key is not None else store.create(request)
        except (ValueError, OSError):
            return error_response(422, 'invalid_source', 'Prepared source is unavailable or mismatched')
        response.headers['Location'] = f'/tasks/{task.id}'
        return task

    @app.get('/tasks/{task_id}', response_model=TaskView,
             responses={404: {'model': ErrorResponse}, 503: {'model': ErrorResponse}})
    def get(task_id: UUID):
        task = store.get(task_id)
        if task is None:
            return error_response(404, 'not_found', 'Task does not exist')
        return task

    @app.post('/tasks/{task_id}/cancel', response_model=TaskView)
    def cancel(task_id: UUID):
        return store.cancel(task_id) or error_response(404, 'not_found', 'Task does not exist')

    @app.post('/tasks/{task_id}/retry', response_model=TaskView)
    def retry(task_id: UUID):
        return store.retry(task_id) or error_response(404, 'not_found', 'Task does not exist')

    @app.get('/tasks/{task_id}/attempts')
    def attempts(task_id: UUID):
        if store.get(task_id) is None:
            return error_response(404, 'not_found', 'Task does not exist')
        return store.history(task_id)

    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--host', default='127.0.0.1')
    args = parser.parse_args()
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level='info')


if __name__ == '__main__':
    main()
