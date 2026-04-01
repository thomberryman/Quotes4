from __future__ import annotations

from contextvars import ContextVar, Token
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_request_id_context: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    return _request_id_context.get()


def set_request_id(request_id: str) -> Token[str]:
    return _request_id_context.set(request_id)


def reset_request_id(token: Token[str]) -> None:
    _request_id_context.reset(token)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        request_id = request.headers.get("x-request-id", str(uuid4()))
        token = set_request_id(request_id)
        request.state.request_id = request_id

        try:
            response = await call_next(request)
        finally:
            reset_request_id(token)

        response.headers["X-Request-ID"] = request_id
        return response
