from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.auth import CurrentSubject, require_permissions
from app.core.db import get_db_session
from app.modules.dashboards.schemas import DashboardDrilldownResponse, OperationalDashboardResponse
from app.modules.dashboards.service import dashboard_service

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db_session)]
DashboardsReadSubject = Annotated[
    CurrentSubject,
    Depends(require_permissions("projects.read")),
]


@router.get("/operational", response_model=OperationalDashboardResponse)
def get_operational_dashboard(
    session: DbSession,
    _subject: DashboardsReadSubject,
    from_month: str | None = Query(default=None, alias="fromMonth"),
    to_month: str | None = Query(default=None, alias="toMonth"),
    client_id: str | None = Query(default=None, alias="clientId"),
    project_id: str | None = Query(default=None, alias="projectId"),
    discipline_id: str | None = Query(default=None, alias="disciplineId"),
    status: str | None = Query(default=None),
    scenario_key: str | None = Query(default=None, alias="scenarioKey"),
) -> OperationalDashboardResponse:
    return dashboard_service.get_operational_dashboard(
        session,
        from_month=from_month,
        to_month=to_month,
        client_id=client_id,
        project_id=project_id,
        discipline_id=discipline_id,
        status=status,
        scenario_key=scenario_key,
    )


@router.get("/drilldowns/{view}", response_model=DashboardDrilldownResponse)
def get_dashboard_drilldown(
    view: str,
    session: DbSession,
    _subject: DashboardsReadSubject,
    from_month: str | None = Query(default=None, alias="fromMonth"),
    to_month: str | None = Query(default=None, alias="toMonth"),
    client_id: str | None = Query(default=None, alias="clientId"),
    project_id: str | None = Query(default=None, alias="projectId"),
    discipline_id: str | None = Query(default=None, alias="disciplineId"),
    status: str | None = Query(default=None),
    scenario_key: str | None = Query(default=None, alias="scenarioKey"),
) -> DashboardDrilldownResponse:
    return dashboard_service.get_drilldown(
        session,
        view,
        from_month=from_month,
        to_month=to_month,
        client_id=client_id,
        project_id=project_id,
        discipline_id=discipline_id,
        status=status,
        scenario_key=scenario_key,
    )


@router.get("/drilldowns/{view}/csv", response_class=PlainTextResponse)
def export_dashboard_drilldown_csv(
    view: str,
    session: DbSession,
    _subject: DashboardsReadSubject,
    from_month: str | None = Query(default=None, alias="fromMonth"),
    to_month: str | None = Query(default=None, alias="toMonth"),
    client_id: str | None = Query(default=None, alias="clientId"),
    project_id: str | None = Query(default=None, alias="projectId"),
    discipline_id: str | None = Query(default=None, alias="disciplineId"),
    status: str | None = Query(default=None),
    scenario_key: str | None = Query(default=None, alias="scenarioKey"),
) -> PlainTextResponse:
    drilldown = dashboard_service.get_drilldown(
        session,
        view,
        from_month=from_month,
        to_month=to_month,
        client_id=client_id,
        project_id=project_id,
        discipline_id=discipline_id,
        status=status,
        scenario_key=scenario_key,
    )
    filename = f"quotes4-{view}.csv"
    return PlainTextResponse(
        dashboard_service.render_csv(drilldown),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
