from __future__ import annotations

import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.requests import Request

from app.core.request_context import get_request_id
from app.core.schemas import BaseSchema

logger = logging.getLogger(__name__)


class ApiProblem(BaseSchema):
    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: str | None = None
    request_id: str
    errors: list[Any] | None = None


class ApiProblemException(Exception):
    def __init__(
        self,
        status_code: int,
        detail: str,
        title: str | None = None,
        problem_type: str = "about:blank",
    ) -> None:
        self.status_code = status_code
        self.detail = detail
        self.title = title or HTTPStatus(status_code).phrase
        self.problem_type = problem_type
        super().__init__(detail)


def _build_problem(
    request: Request,
    *,
    status_code: int,
    detail: str,
    title: str,
    problem_type: str = "about:blank",
) -> ApiProblem:
    request_id = getattr(request.state, "request_id", "") or get_request_id() or "unknown"
    return ApiProblem(
        type=problem_type,
        title=title,
        status=status_code,
        detail=detail,
        instance=str(request.url),
        request_id=request_id,
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiProblemException)
    async def handle_api_problem(request: Request, exc: ApiProblemException) -> JSONResponse:
        problem = _build_problem(
            request,
            status_code=exc.status_code,
            detail=exc.detail,
            title=exc.title,
            problem_type=exc.problem_type,
        )
        return JSONResponse(status_code=exc.status_code, content=problem.model_dump(by_alias=True))

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        problem = _build_problem(
            request,
            status_code=422,
            detail="Request validation failed.",
            title="Validation Error",
            problem_type="https://quotes4.dev/problems/validation-error",
        )
        payload = problem.model_dump(by_alias=True)
        payload["errors"] = exc.errors()
        return JSONResponse(status_code=422, content=payload)

    @app.exception_handler(IntegrityError)
    async def handle_integrity_error(request: Request, exc: IntegrityError) -> JSONResponse:
        logger.warning(
            "database_integrity_error",
            extra={"request_path": str(request.url)},
            exc_info=exc,
        )
        problem = _build_problem(
            request,
            status_code=409,
            detail="The request conflicted with an existing record or database constraint.",
            title="Conflict",
            problem_type="https://quotes4.dev/problems/conflict",
        )
        return JSONResponse(status_code=409, content=problem.model_dump(by_alias=True))

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "unhandled_api_exception",
            extra={"request_path": str(request.url)},
        )
        problem = _build_problem(
            request,
            status_code=500,
            detail="The server could not complete the request.",
            title="Internal Server Error",
            problem_type="https://quotes4.dev/problems/internal-error",
        )
        return JSONResponse(status_code=500, content=problem.model_dump(by_alias=True))
