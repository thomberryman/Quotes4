from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from starlette.responses import Response

from app.core.config import get_settings
from app.core.errors import ApiProblem, register_exception_handlers
from app.core.logging import configure_logging
from app.core.request_context import RequestContextMiddleware
from app.core.schemas import BaseSchema
from app.modules import api_router

configure_logging()
settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Request-ID"],
)
register_exception_handlers(app)
app.include_router(api_router, prefix=settings.api_base_path)


@app.middleware("http")
async def apply_security_headers(request: Request, call_next) -> Response:
    response = await call_next(request)
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    return response


def custom_openapi() -> dict[str, object]:
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
        description=app.description,
    )
    components = openapi_schema.setdefault("components", {})
    schemas = components.setdefault("schemas", {})
    schemas["ApiProblem"] = ApiProblem.model_json_schema(
        by_alias=True, ref_template="#/components/schemas/{model}"
    )
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


class HealthResponse(BaseSchema):
    name: str
    status: str
    environment: str
    timestamp: datetime
    api_base_path: str


@app.get("/", tags=["system"])
def read_root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "docsUrl": "/docs",
        "openApiUrl": "/openapi.json",
        "apiBasePath": settings.api_base_path,
    }


@app.get(f"{settings.api_base_path}/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    return HealthResponse(
        name=settings.app_name,
        status="ok",
        environment=settings.app_env,
        timestamp=datetime.now(UTC),
        api_base_path=settings.api_base_path,
    )
