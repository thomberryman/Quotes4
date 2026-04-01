from fastapi import APIRouter

from app.modules.actuals_imports.router import router as actuals_imports_router
from app.modules.audit.router import router as audit_router
from app.modules.auth.router import router as auth_router
from app.modules.clients.router import router as clients_router
from app.modules.comparables.router import router as comparables_router
from app.modules.dashboards.router import router as dashboards_router
from app.modules.files.router import router as files_router
from app.modules.forecasts.router import router as forecasts_router
from app.modules.jobs.router import router as jobs_router
from app.modules.projects.router import router as projects_router
from app.modules.quote_ingestion.router import router as quote_ingestion_router
from app.modules.quotes.router import router as quotes_router
from app.modules.rbac.router import router as rbac_router
from app.modules.users.router import router as users_router

api_router = APIRouter()
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(users_router, prefix="/users", tags=["users"])
api_router.include_router(rbac_router, prefix="/rbac", tags=["rbac"])
api_router.include_router(clients_router, tags=["clients"])
api_router.include_router(projects_router, prefix="/projects", tags=["projects"])
api_router.include_router(comparables_router, prefix="/projects", tags=["comparables"])
api_router.include_router(quotes_router, prefix="/quotes", tags=["quotes"])
api_router.include_router(
    quote_ingestion_router,
    prefix="/quote-ingestion",
    tags=["quote-ingestion"],
)
api_router.include_router(
    actuals_imports_router,
    prefix="/actuals-imports",
    tags=["actuals-imports"],
)
api_router.include_router(files_router, prefix="/files", tags=["files"])
api_router.include_router(forecasts_router, prefix="/forecasts", tags=["forecasts"])
api_router.include_router(dashboards_router, prefix="/dashboards", tags=["dashboards"])
api_router.include_router(audit_router, prefix="/audit", tags=["audit"])
api_router.include_router(jobs_router, prefix="/jobs", tags=["jobs"])
