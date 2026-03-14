"""Request tracing, structured logging, and global error envelope setup."""

from __future__ import annotations

import json
import logging
import time
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas.contracts import ProblemResponse

LOGGER_NAME = "eco_health.api"


def configure_logging() -> None:
    """Initialize application logging once."""

    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=logging.INFO, format="%(message)s")


def _trace_id(request: Request) -> str:
    existing = getattr(request.state, "trace_id", None)
    return existing or str(uuid4())


def _problem_response(
    *,
    status_code: int,
    code: str,
    message: str,
    trace_id: str,
    retryable: bool,
) -> JSONResponse:
    body = ProblemResponse(code=code, message=message, trace_id=trace_id, retryable=retryable).model_dump()
    return JSONResponse(status_code=status_code, content=body, headers={"X-Trace-Id": trace_id})


def setup_observability(app: FastAPI) -> None:
    """Attach tracing middleware and global exception handlers."""

    configure_logging()
    logger = logging.getLogger(LOGGER_NAME)

    @app.middleware("http")
    async def trace_middleware(request: Request, call_next):
        trace_id = request.headers.get("X-Trace-Id") or str(uuid4())
        request.state.trace_id = trace_id
        start = time.perf_counter()

        response = await call_next(request)

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        logger.info(
            json.dumps(
                {
                    "event": "http_request",
                    "trace_id": trace_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": elapsed_ms,
                }
            )
        )
        response.headers["X-Trace-Id"] = trace_id
        return response

    @app.exception_handler(StarletteHTTPException)
    async def starlette_http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        trace_id = _trace_id(request)
        code = "HTTP_ERROR"
        if exc.status_code in (401, 403):
            code = "AUTH_ERROR"
        elif exc.status_code == 404:
            code = "NOT_FOUND"
        retryable = exc.status_code in (429, 503, 504)
        return _problem_response(
            status_code=exc.status_code,
            code=code,
            message=str(exc.detail),
            trace_id=trace_id,
            retryable=retryable,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        trace_id = _trace_id(request)
        return _problem_response(
            status_code=422,
            code="VALIDATION_ERROR",
            message="Invalid request payload",
            trace_id=trace_id,
            retryable=False,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        trace_id = _trace_id(request)
        logger.exception(
            json.dumps(
                {
                    "event": "unhandled_exception",
                    "trace_id": trace_id,
                    "path": request.url.path,
                    "error": str(exc),
                }
            )
        )
        return _problem_response(
            status_code=500,
            code="INTERNAL_ERROR",
            message="Internal server error",
            trace_id=trace_id,
            retryable=False,
        )
