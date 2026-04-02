from __future__ import annotations

import os
import hashlib
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.main import app
from app.models import BackgroundJob, UploadedFile, User
from app.models.enums import BackgroundJobStatus

TEST_CHECKSUM = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


def _assert_status(response, expected_status: int) -> dict[str, object]:
    assert response.status_code == expected_status, response.text
    return response.json()


def _bearer_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def _csrf_headers(client: TestClient) -> dict[str, str]:
    csrf_token = client.cookies.get(get_settings().auth_csrf_cookie_name)
    assert csrf_token
    return {"X-CSRF-Token": csrf_token}


def _login(
    client: TestClient,
    *,
    email: str,
    password: str,
) -> dict[str, object]:
    response = client.post(
        "/api/v1/auth/session",
        json={"email": email, "password": password},
    )
    return _assert_status(response, 200)


def _invite_accept_and_login(
    client: TestClient,
    *,
    admin_headers: dict[str, str],
    email: str,
    first_name: str,
    last_name: str,
    role_keys: list[str],
    password: str,
) -> dict[str, dict[str, object]]:
    invitation = _assert_status(
        client.post(
            "/api/v1/auth/invitations",
            headers=admin_headers,
            json={
                "email": email,
                "firstName": first_name,
                "lastName": last_name,
                "roleKeys": role_keys,
            },
        ),
        201,
    )
    accepted = _assert_status(
        client.post(
            "/api/v1/auth/invitations/accept",
            json={
                "invitationToken": invitation["inviteToken"],
                "password": password,
            },
        ),
        200,
    )
    session = _login(client, email=email, password=password)
    return {
        "invitation": invitation,
        "accepted": accepted,
        "session": session,
    }


def test_auth_invite_refresh_and_logout(client: TestClient) -> None:
    settings = get_settings()
    admin_session = _login(
        client,
        email=os.environ["DEV_ADMIN_EMAIL"],
        password=os.environ["DEV_ADMIN_PASSWORD"],
    )
    admin_headers = _bearer_headers(str(admin_session["accessToken"]))

    invited = _invite_accept_and_login(
        client,
        admin_headers=admin_headers,
        email="finance@example.com",
        first_name="Fin",
        last_name="Analyst",
        role_keys=["finance_analyst"],
        password="FinanceAnalyst123!",
    )

    assert invited["accepted"]["user"]["roleKeys"] == ["finance_analyst"]

    cookie_login_response = client.post(
        "/api/v1/auth/session",
        json={
            "email": "finance@example.com",
            "password": "FinanceAnalyst123!",
        },
    )
    cookie_session = _assert_status(cookie_login_response, 200)
    set_cookie = ", ".join(cookie_login_response.headers.get_list("set-cookie"))
    assert f"{settings.auth_access_cookie_name}=" in set_cookie
    assert f"{settings.auth_refresh_cookie_name}=" in set_cookie
    assert f"{settings.auth_csrf_cookie_name}=" in set_cookie
    assert "HttpOnly" in set_cookie

    cookie_me = _assert_status(client.get("/api/v1/auth/me"), 200)
    assert cookie_me["email"] == "finance@example.com"

    me = _assert_status(
        client.get(
            "/api/v1/auth/me",
            headers=_bearer_headers(str(cookie_session["accessToken"])),
        ),
        200,
    )
    assert me["email"] == "finance@example.com"

    refreshed = _assert_status(
        client.post(
            "/api/v1/auth/session/refresh",
            json={"refreshToken": invited["session"]["refreshToken"]},
        ),
        200,
    )
    assert refreshed["refreshToken"] != invited["session"]["refreshToken"]

    stale_refresh = client.post(
        "/api/v1/auth/session/refresh",
        json={"refreshToken": invited["session"]["refreshToken"]},
    )
    assert stale_refresh.status_code == 401

    logout = _assert_status(
        client.delete("/api/v1/auth/session", headers=_csrf_headers(client)),
        200,
    )
    assert logout["message"] == "Session cleared."

    revoked_refresh = client.post(
        "/api/v1/auth/session/refresh",
        json={"refreshToken": refreshed["refreshToken"]},
    )
    assert revoked_refresh.status_code == 401


def test_cookie_authenticated_unsafe_requests_require_csrf(client: TestClient) -> None:
    settings = get_settings()
    _login(
        client,
        email=os.environ["DEV_ADMIN_EMAIL"],
        password=os.environ["DEV_ADMIN_PASSWORD"],
    )

    denied_project_create = client.post(
        "/api/v1/projects",
        json={"name": "CSRF Project", "status": "bid", "quoteCurrencyCode": "GBP"},
    )
    assert denied_project_create.status_code == 403

    created_project = _assert_status(
        client.post(
            "/api/v1/projects",
            headers=_csrf_headers(client),
            json={"name": "CSRF Project", "status": "bid", "quoteCurrencyCode": "GBP"},
        ),
        201,
    )
    assert created_project["name"] == "CSRF Project"

    stale_csrf_headers = _csrf_headers(client)
    refreshed = _assert_status(
        client.post(
            "/api/v1/auth/session/refresh",
            headers=stale_csrf_headers,
            json={},
        ),
        200,
    )
    assert refreshed["tokenType"] == "bearer"
    assert client.cookies.get(settings.auth_csrf_cookie_name) != stale_csrf_headers["X-CSRF-Token"]

    denied_logout = client.delete("/api/v1/auth/session")
    assert denied_logout.status_code == 403

    logout = _assert_status(
        client.delete("/api/v1/auth/session", headers=_csrf_headers(client)),
        200,
    )
    assert logout["message"] == "Session cleared."


def test_auth_cookie_names_can_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_ACCESS_COOKIE_NAME", "quotes4_demo_access")
    monkeypatch.setenv("AUTH_REFRESH_COOKIE_NAME", "quotes4_demo_refresh")
    monkeypatch.setenv("AUTH_CSRF_COOKIE_NAME", "quotes4_demo_csrf")
    get_settings.cache_clear()

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/session",
            json={
                "email": os.environ["DEV_ADMIN_EMAIL"],
                "password": os.environ["DEV_ADMIN_PASSWORD"],
            },
        )

        payload = _assert_status(response, 200)
        assert payload["tokenType"] == "bearer"

        set_cookie = ", ".join(response.headers.get_list("set-cookie"))
        assert "quotes4_demo_access=" in set_cookie
        assert "quotes4_demo_refresh=" in set_cookie
        assert "quotes4_demo_csrf=" in set_cookie
        assert client.cookies.get("quotes4_demo_csrf")


def test_failed_auth_attempts_are_written_to_audit_log(client: TestClient) -> None:
    failed_login = client.post(
        "/api/v1/auth/session",
        json={
            "email": os.environ["DEV_ADMIN_EMAIL"],
            "password": "not-the-right-password",
        },
    )
    assert failed_login.status_code == 401

    admin_session = _login(
        client,
        email=os.environ["DEV_ADMIN_EMAIL"],
        password=os.environ["DEV_ADMIN_PASSWORD"],
    )
    admin_headers = _bearer_headers(str(admin_session["accessToken"]))

    audit_events = _assert_status(
        client.get(
            "/api/v1/audit/events?entityType=auth_attempt&limit=20",
            headers=admin_headers,
        ),
        200,
    )
    auth_failure_event = next(
        item for item in audit_events["items"] if item["action"] == "auth.session.failed"
    )
    assert auth_failure_event["metadata"]["email"] == os.environ["DEV_ADMIN_EMAIL"]
    assert auth_failure_event["metadata"]["reason"] == "invalid_credentials"


def test_login_accepts_legacy_fallback_sha256_password_hashes(client: TestClient, db_session) -> None:
    admin_user = db_session.scalar(select(User).where(User.email == os.environ["DEV_ADMIN_EMAIL"]))
    assert admin_user is not None
    password = os.environ["DEV_ADMIN_PASSWORD"]
    admin_user.password_hash = f"fallback-sha256${hashlib.sha256(password.encode('utf-8')).hexdigest()}"
    db_session.commit()

    response = client.post(
        "/api/v1/auth/session",
        json={
            "email": os.environ["DEV_ADMIN_EMAIL"],
            "password": password,
        },
    )

    assert response.status_code == 200, response.text


def test_project_create_rejects_end_date_before_start_date(client: TestClient) -> None:
    admin_session = _login(
        client,
        email=os.environ["DEV_ADMIN_EMAIL"],
        password=os.environ["DEV_ADMIN_PASSWORD"],
    )
    admin_headers = _bearer_headers(str(admin_session["accessToken"]))

    response = client.post(
        "/api/v1/projects",
        headers=admin_headers,
        json={
            "name": "Invalid Date Intake",
            "status": "bid",
            "startDate": "2026-05-10",
            "endDate": "2026-05-01",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Project end date cannot be earlier than start date."


def test_backend_mvp_workflow(client: TestClient) -> None:
    admin_session = _login(
        client,
        email=os.environ["DEV_ADMIN_EMAIL"],
        password=os.environ["DEV_ADMIN_PASSWORD"],
    )
    admin_headers = _bearer_headers(str(admin_session["accessToken"]))

    leadership = _invite_accept_and_login(
        client,
        admin_headers=admin_headers,
        email="leadership@example.com",
        first_name="Lead",
        last_name="Viewer",
        role_keys=["leadership"],
        password="LeadershipPass123!",
    )
    denied_users = client.get(
        "/api/v1/users",
        headers=_bearer_headers(str(leadership["session"]["accessToken"])),
    )
    assert denied_users.status_code == 403

    created_user = _assert_status(
        client.post(
            "/api/v1/users",
            headers=admin_headers,
            json={
                "email": "planner@example.com",
                "firstName": "Plan",
                "lastName": "Ner",
                "displayName": "Plan Ner",
                "jobTitle": "Planner",
                "roleKeys": ["leadership"],
            },
        ),
        201,
    )
    updated_user = _assert_status(
        client.patch(
            f"/api/v1/users/{created_user['id']}",
            headers=admin_headers,
            json={
                "expectedUpdatedAt": created_user["updatedAt"],
                "jobTitle": "Senior Planner",
            },
        ),
        200,
    )
    rerolled_user = _assert_status(
        client.put(
            f"/api/v1/users/{created_user['id']}/roles",
            headers=admin_headers,
            json={"roleKeys": ["finance_analyst"]},
        ),
        200,
    )
    fetched_user = _assert_status(
        client.get(f"/api/v1/users/{created_user['id']}", headers=admin_headers),
        200,
    )
    assert updated_user["jobTitle"] == "Senior Planner"
    assert rerolled_user["roleKeys"] == ["finance_analyst"]
    assert fetched_user["id"] == created_user["id"]

    counterparty = _assert_status(
        client.post(
            "/api/v1/counterparties",
            headers=admin_headers,
            json={
                "name": "Example Client",
                "legalName": "Example Client Ltd",
                "defaultCurrencyCode": "GBP",
                "classifications": ["client", "production_company"],
                "notes": "Primary bid counterparty",
            },
        ),
        201,
    )
    updated_counterparty = _assert_status(
        client.patch(
            f"/api/v1/counterparties/{counterparty['id']}",
            headers=admin_headers,
            json={
                "expectedUpdatedAt": counterparty["updatedAt"],
                "websiteUrl": "https://example.test",
            },
        ),
        200,
    )
    clients = _assert_status(client.get("/api/v1/clients", headers=admin_headers), 200)
    counterparties = _assert_status(
        client.get("/api/v1/counterparties", headers=admin_headers),
        200,
    )
    assert updated_counterparty["websiteUrl"] == "https://example.test"
    assert any(item["id"] == counterparty["id"] for item in clients["items"])
    assert any(item["id"] == counterparty["id"] for item in counterparties["items"])

    contact = _assert_status(
        client.post(
            "/api/v1/contacts",
            headers=admin_headers,
            json={
                "firstName": "Casey",
                "lastName": "Client",
                "email": "casey.client@example.com",
                "phone": "+44 20 0000 0000",
            },
        ),
        201,
    )
    updated_contact = _assert_status(
        client.patch(
            f"/api/v1/contacts/{contact['id']}",
            headers=admin_headers,
            json={
                "expectedUpdatedAt": contact["updatedAt"],
                "mobile": "+44 7700 900000",
            },
        ),
        200,
    )
    discipline = _assert_status(
        client.post(
            "/api/v1/disciplines",
            headers=admin_headers,
            json={
                "code": "edit",
                "name": "Editorial",
                "sortOrder": 15,
            },
        ),
        201,
    )
    updated_discipline = _assert_status(
        client.patch(
            f"/api/v1/disciplines/{discipline['id']}",
            headers=admin_headers,
            json={
                "expectedUpdatedAt": discipline["updatedAt"],
                "name": "Picture Editorial",
            },
        ),
        200,
    )
    listed_contacts = _assert_status(client.get("/api/v1/contacts", headers=admin_headers), 200)
    listed_disciplines = _assert_status(
        client.get("/api/v1/disciplines", headers=admin_headers),
        200,
    )
    assert updated_contact["mobile"] == "+44 7700 900000"
    assert updated_discipline["name"] == "Picture Editorial"
    assert any(item["id"] == contact["id"] for item in listed_contacts["items"])
    assert any(item["id"] == discipline["id"] for item in listed_disciplines["items"])

    project = _assert_status(
        client.post(
            "/api/v1/projects",
            headers=admin_headers,
            json={
                "code": "PRJ-001",
                "name": "Planet Edit",
                "description": "MVP project flow",
                "quoteCurrencyCode": "GBP",
                "bidDueDate": "2026-01-15",
            },
        ),
        201,
    )
    project = _assert_status(
        client.patch(
            f"/api/v1/projects/{project['id']}",
            headers=admin_headers,
            json={
                "expectedUpdatedAt": project["updatedAt"],
                "description": "Updated MVP project flow",
            },
        ),
        200,
    )
    project = _assert_status(
        client.put(
            f"/api/v1/projects/{project['id']}/metadata",
            headers=admin_headers,
            json={
                "expectedUpdatedAt": project["updatedAt"],
                "contentType": "Series",
                "runtimeMinutes": 60,
                "metadata": {"commissioner": "Ops"},
            },
        ),
        200,
    )
    project = _assert_status(
        client.put(
            f"/api/v1/projects/{project['id']}/parties",
            headers=admin_headers,
            json={
                "expectedUpdatedAt": project["updatedAt"],
                "items": [
                    {
                        "companyId": counterparty["id"],
                        "role": "client",
                        "isPrimary": True,
                    }
                ],
            },
        ),
        200,
    )
    project = _assert_status(
        client.put(
            f"/api/v1/projects/{project['id']}/contacts",
            headers=admin_headers,
            json={
                "expectedUpdatedAt": project["updatedAt"],
                "items": [
                    {
                        "contactId": contact["id"],
                        "companyId": counterparty["id"],
                        "jobTitle": "Executive Producer",
                        "isPrimary": True,
                    }
                ],
            },
        ),
        200,
    )
    project = _assert_status(
        client.put(
            f"/api/v1/projects/{project['id']}/disciplines",
            headers=admin_headers,
            json={
                "expectedUpdatedAt": project["updatedAt"],
                "items": [{"disciplineId": discipline["id"], "isPrimary": True}],
            },
        ),
        200,
    )
    project = _assert_status(
        client.put(
            f"/api/v1/projects/{project['id']}/schedule-ranges",
            headers=admin_headers,
            json={
                "expectedUpdatedAt": project["updatedAt"],
                "items": [
                    {
                        "disciplineId": discipline["id"],
                        "label": "Edit Block",
                        "startDate": "2026-01-01",
                        "endDate": "2026-02-28",
                        "allocationPercent": 100,
                    }
                ],
            },
        ),
        200,
    )
    project = _assert_status(
        client.post(
            f"/api/v1/projects/{project['id']}/outcomes",
            headers=admin_headers,
            json={
                "outcomeType": "bid",
                "effectiveAt": datetime.now(UTC).isoformat(),
                "notes": "Bid logged",
            },
        ),
        201,
    )
    listed_projects = _assert_status(client.get("/api/v1/projects", headers=admin_headers), 200)
    fetched_project = _assert_status(
        client.get(f"/api/v1/projects/{project['id']}", headers=admin_headers),
        200,
    )
    assert any(item["id"] == project["id"] for item in listed_projects["items"])
    assert fetched_project["metadata"]["contentType"] == "Series"

    quote = _assert_status(
        client.post(
            "/api/v1/quotes",
            headers=admin_headers,
            json={
                "projectId": project["id"],
                "quoteNumber": "Q-001",
                "title": "Initial Quote",
            },
        ),
        201,
    )
    quote = _assert_status(
        client.patch(
            f"/api/v1/quotes/{quote['id']}",
            headers=admin_headers,
            json={
                "expectedUpdatedAt": quote["updatedAt"],
                "title": "Updated Quote",
            },
        ),
        200,
    )
    quote_version = _assert_status(
        client.post(
            f"/api/v1/quotes/{quote['id']}/versions",
            headers=admin_headers,
            json={
                "title": "Client Draft",
                "currencyCode": "GBP",
                "validUntil": "2026-01-31",
                "subtotalAmount": 10000,
                "taxAmount": 0,
                "totalAmount": 10000,
                "sections": [
                    {
                        "name": "Editorial",
                        "sortOrder": 1,
                        "subtotalAmount": 10000,
                        "lineItems": [
                            {
                                "sortOrder": 1,
                                "lineType": "service",
                                "disciplineId": discipline["id"],
                                "description": "Offline edit",
                                "quantity": 1,
                                "unit": "project",
                                "rate": 10000,
                                "amount": 10000,
                            }
                        ],
                    }
                ],
            },
        ),
        201,
    )
    listed_quote_versions = _assert_status(
        client.get(f"/api/v1/quotes/{quote['id']}/versions", headers=admin_headers),
        200,
    )
    fetched_quote_version = _assert_status(
        client.get(f"/api/v1/quotes/versions/{quote_version['id']}", headers=admin_headers),
        200,
    )
    issued_quote_version = _assert_status(
        client.post(
            f"/api/v1/quotes/versions/{quote_version['id']}/issue",
            headers=admin_headers,
        ),
        200,
    )
    rejected_quote_patch = client.patch(
        f"/api/v1/quotes/versions/{quote_version['id']}",
        headers=admin_headers,
        json={
            "expectedUpdatedAt": quote_version["updatedAt"],
            "title": "Should Fail",
        },
    )
    assert rejected_quote_patch.status_code == 409
    assert len(listed_quote_versions) == 1
    assert fetched_quote_version["id"] == quote_version["id"]
    assert issued_quote_version["status"] == "issued"

    forecast_version = _assert_status(
        client.post(
            f"/api/v1/forecasts/projects/{project['id']}/versions",
            headers=admin_headers,
            json={"title": "Forecast Draft"},
        ),
        201,
    )
    assert len(forecast_version["lines"]) == 1
    forecast_line = forecast_version["lines"][0]

    forecast_version = _assert_status(
        client.put(
            f"/api/v1/forecasts/lines/{forecast_line['id']}/allocations",
            headers=admin_headers,
            json={
                "expectedUpdatedAt": forecast_version["updatedAt"],
                "allocationMethod": "manual",
                "allocations": [
                    {"month": "2026-01", "amount": 6000},
                    {"month": "2026-02", "amount": 4000},
                ],
                "reason": "Manual rebalance",
            },
        ),
        200,
    )
    fetched_forecast_version = _assert_status(
        client.get(
            f"/api/v1/forecasts/versions/{forecast_version['id']}",
            headers=admin_headers,
        ),
        200,
    )
    assert fetched_forecast_version["isSourceQuoteCurrent"] is True
    assert "Manual override: Manual rebalance" in str(fetched_forecast_version["lines"][0]["notes"])
    submitted_forecast = _assert_status(
        client.post(
            f"/api/v1/forecasts/versions/{forecast_version['id']}/submit",
            headers=admin_headers,
        ),
        200,
    )
    locked_forecast = _assert_status(
        client.post(
            f"/api/v1/forecasts/versions/{forecast_version['id']}/lock",
            headers=admin_headers,
        ),
        200,
    )
    forecast_detail = _assert_status(
        client.get(f"/api/v1/forecasts/projects/{project['id']}", headers=admin_headers),
        200,
    )
    assert fetched_forecast_version["id"] == forecast_version["id"]
    assert submitted_forecast["status"] == "submitted"
    assert locked_forecast["status"] == "locked"
    assert forecast_detail["currentVersionId"] == forecast_version["id"]

    revised_quote_version = _assert_status(
        client.post(
            f"/api/v1/quotes/{quote['id']}/versions",
            headers=admin_headers,
            json={
                "baseVersionId": quote_version["id"],
                "title": "Client Revision",
                "currencyCode": "GBP",
                "validUntil": "2026-02-15",
                "subtotalAmount": 12000,
                "taxAmount": 0,
                "totalAmount": 12000,
                "sections": [
                    {
                        "name": "Editorial",
                        "sortOrder": 1,
                        "subtotalAmount": 12000,
                        "lineItems": [
                            {
                                "sortOrder": 1,
                                "lineType": "service",
                                "disciplineId": discipline["id"],
                                "description": "Offline edit revised",
                                "quantity": 1,
                                "unit": "project",
                                "rate": 12000,
                                "amount": 12000,
                            }
                        ],
                    }
                ],
            },
        ),
        201,
    )
    revised_quote_version = _assert_status(
        client.post(
            f"/api/v1/quotes/versions/{revised_quote_version['id']}/issue",
            headers=admin_headers,
        ),
        200,
    )

    stale_forecast_version = _assert_status(
        client.get(
            f"/api/v1/forecasts/versions/{forecast_version['id']}",
            headers=admin_headers,
        ),
        200,
    )
    assert stale_forecast_version["isSourceQuoteCurrent"] is False
    assert any(
        "source quote version is no longer current" in issue
        for issue in stale_forecast_version["issues"]
    )

    recalc = _assert_status(
        client.post(
            f"/api/v1/forecasts/projects/{project['id']}/recalculate",
            headers=admin_headers,
        ),
        202,
    )
    recalculated_forecast_version = _assert_status(
        client.get(
            f"/api/v1/forecasts/versions/{recalc['forecastVersionId']}",
            headers=admin_headers,
        ),
        200,
    )
    forecast_detail = _assert_status(
        client.get(f"/api/v1/forecasts/projects/{project['id']}", headers=admin_headers),
        200,
    )
    listed_jobs = _assert_status(client.get("/api/v1/jobs", headers=admin_headers), 200)
    fetched_job = _assert_status(
        client.get(f"/api/v1/jobs/{recalc['jobId']}", headers=admin_headers),
        200,
    )
    assert recalc["status"] == "queued"
    assert recalc["forecastVersionId"] == recalculated_forecast_version["id"]
    assert "current quote" in recalc["message"].lower()
    assert recalculated_forecast_version["status"] == "draft"
    assert recalculated_forecast_version["isSourceQuoteCurrent"] is True
    assert recalculated_forecast_version["totalAmount"] == 12000
    assert recalculated_forecast_version["lines"][0]["label"] == "Offline edit revised"
    assert forecast_detail["currentVersionId"] == recalculated_forecast_version["id"]
    assert any(item["id"] == recalc["jobId"] for item in listed_jobs["items"])
    assert fetched_job["queueName"] == "forecast_recalc"

    presigned = _assert_status(
        client.post(
            "/api/v1/files/uploads/presign",
            headers=admin_headers,
            json={
                "fileName": "project-brief.txt",
                "contentType": "text/plain",
                "sizeBytes": 128,
                "checksumSha256": TEST_CHECKSUM,
                "entityType": "project",
                "entityId": project["id"],
            },
        ),
        201,
    )
    finalized = _assert_status(
        client.post(
            "/api/v1/files/uploads/finalize",
            headers=admin_headers,
            json={
                "fileId": presigned["fileId"],
                "objectKey": presigned["objectKey"],
                "checksumSha256": TEST_CHECKSUM,
            },
        ),
        200,
    )
    fetched_file = _assert_status(
        client.get(f"/api/v1/files/{presigned['fileId']}", headers=admin_headers),
        200,
    )
    assert finalized["file"]["status"] == "uploaded"
    assert fetched_file["entityId"] == project["id"]

    audit_events = _assert_status(
        client.get(
            f"/api/v1/audit/events?projectId={project['id']}&limit=20",
            headers=admin_headers,
        ),
        200,
    )
    actions = {item["action"] for item in audit_events["items"]}
    assert {
        "quote.version.issued",
        "forecast.version.locked",
        "forecast.version.recalculated",
        "file.upload.finalized",
    }.issubset(actions)


def test_uploaded_files_use_authenticated_download_urls(
    client: TestClient,
    db_session,
    tmp_path,
) -> None:
    admin_session = _login(
        client,
        email=os.environ["DEV_ADMIN_EMAIL"],
        password=os.environ["DEV_ADMIN_PASSWORD"],
    )
    admin_headers = _bearer_headers(str(admin_session["accessToken"]))

    project = _assert_status(
        client.post(
            "/api/v1/projects",
            headers=admin_headers,
            json={"name": "Download Project", "status": "bid", "quoteCurrencyCode": "GBP"},
        ),
        201,
    )
    presigned = _assert_status(
        client.post(
            "/api/v1/files/uploads/presign",
            headers=admin_headers,
            json={
                "fileName": "download-brief.txt",
                "contentType": "text/plain",
                "sizeBytes": 21,
                "checksumSha256": TEST_CHECKSUM,
                "entityType": "project",
                "entityId": project["id"],
            },
        ),
        201,
    )
    _assert_status(
        client.post(
            "/api/v1/files/uploads/finalize",
            headers=admin_headers,
            json={
                "fileId": presigned["fileId"],
                "objectKey": presigned["objectKey"],
                "checksumSha256": TEST_CHECKSUM,
            },
        ),
        200,
    )

    fixture_path = tmp_path / "download-brief.txt"
    fixture_bytes = b"downloaded file bytes"
    fixture_path.write_bytes(fixture_bytes)

    uploaded_file = db_session.get(UploadedFile, presigned["fileId"])
    assert uploaded_file is not None
    uploaded_file.storage_key = str(fixture_path)
    db_session.commit()

    file_metadata = _assert_status(
        client.get(f"/api/v1/files/{presigned['fileId']}", headers=admin_headers),
        200,
    )
    assert file_metadata["downloadUrl"].endswith(f"/api/v1/files/{presigned['fileId']}/download")
    assert file_metadata["publicUrl"] == file_metadata["downloadUrl"]

    download_response = client.get(
        f"/api/v1/files/{presigned['fileId']}/download",
        headers=admin_headers,
    )
    assert download_response.status_code == 200, download_response.text
    assert download_response.content == fixture_bytes
    assert download_response.headers["cache-control"] == "private, no-store"
    assert "attachment;" in download_response.headers["content-disposition"]


def test_background_job_active_deduplication_key_is_db_enforced(db_session) -> None:
    now = datetime.now(UTC)
    deduplication_key = "forecast_recalc:project:ops_project_unique"
    db_session.add(
        BackgroundJob(
            queue_name="forecast_recalc",
            status=BackgroundJobStatus.queued,
            deduplication_key=deduplication_key,
            payload_json={"projectId": "ops_project_unique"},
            related_entity_type="project",
            related_entity_id="ops_project_unique",
            attempts=0,
            max_attempts=5,
            available_at=now,
        )
    )
    db_session.commit()

    db_session.add(
        BackgroundJob(
            queue_name="forecast_recalc",
            status=BackgroundJobStatus.running,
            deduplication_key=deduplication_key,
            payload_json={"projectId": "ops_project_unique"},
            related_entity_type="project",
            related_entity_id="ops_project_unique",
            attempts=1,
            max_attempts=5,
            available_at=now,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    db_session.add(
        BackgroundJob(
            queue_name="forecast_recalc",
            status=BackgroundJobStatus.succeeded,
            deduplication_key=deduplication_key,
            payload_json={"projectId": "ops_project_unique"},
            related_entity_type="project",
            related_entity_id="ops_project_unique",
            attempts=1,
            max_attempts=5,
            available_at=now,
        )
    )
    db_session.commit()


def test_jobs_endpoint_exposes_failure_summary(client: TestClient, db_session) -> None:
    now = datetime.now(UTC)
    db_session.add_all(
        [
            BackgroundJob(
                queue_name="ceta_import",
                status=BackgroundJobStatus.failed,
                deduplication_key="ceta_import:ceta_import:ops_batch_failed",
                payload_json={"batchId": "ops_batch_failed"},
                related_entity_type="ceta_import",
                related_entity_id="ops_batch_failed",
                attempts=5,
                max_attempts=5,
                available_at=now,
                failed_at=now,
                last_error="parser failed",
            ),
            BackgroundJob(
                queue_name="forecast_recalc",
                status=BackgroundJobStatus.failed,
                deduplication_key="forecast_recalc:project:ops_project_failed",
                payload_json={"projectId": "ops_project_failed"},
                related_entity_type="project",
                related_entity_id="ops_project_failed",
                attempts=5,
                max_attempts=5,
                available_at=now,
                failed_at=now,
                last_error="upstream mismatch",
            ),
            BackgroundJob(
                queue_name="forecast_recalc",
                status=BackgroundJobStatus.queued,
                deduplication_key="forecast_recalc:project:ops_project_queued",
                payload_json={"projectId": "ops_project_queued"},
                related_entity_type="project",
                related_entity_id="ops_project_queued",
                attempts=0,
                max_attempts=5,
                available_at=now,
            ),
        ]
    )
    db_session.commit()

    admin_session = _login(
        client,
        email=os.environ["DEV_ADMIN_EMAIL"],
        password=os.environ["DEV_ADMIN_PASSWORD"],
    )
    admin_headers = _bearer_headers(str(admin_session["accessToken"]))

    failed_jobs = _assert_status(
        client.get("/api/v1/jobs?status=failed&limit=1", headers=admin_headers),
        200,
    )
    assert len(failed_jobs["items"]) == 1
    assert failed_jobs["summary"]["totalCount"] == 2
    assert failed_jobs["summary"]["counts"]["failed"] == 2
    assert failed_jobs["summary"]["recentFailedCount"] == 2
    assert {item["queueName"] for item in failed_jobs["summary"]["failingQueues"]} == {
        "ceta_import",
        "forecast_recalc",
    }


def test_quotes_can_be_filtered_by_project(client: TestClient) -> None:
    admin_session = _login(
        client,
        email=os.environ["DEV_ADMIN_EMAIL"],
        password=os.environ["DEV_ADMIN_PASSWORD"],
    )
    admin_headers = _bearer_headers(str(admin_session["accessToken"]))

    first_project = _assert_status(
        client.post(
            "/api/v1/projects",
            headers=admin_headers,
            json={"name": "Filtered Quotes A", "status": "bid", "quoteCurrencyCode": "GBP"},
        ),
        201,
    )
    second_project = _assert_status(
        client.post(
            "/api/v1/projects",
            headers=admin_headers,
            json={"name": "Filtered Quotes B", "status": "bid", "quoteCurrencyCode": "GBP"},
        ),
        201,
    )

    first_quote = _assert_status(
        client.post(
            "/api/v1/quotes",
            headers=admin_headers,
            json={"projectId": first_project["id"], "quoteNumber": "FQA-1", "title": "Quote A"},
        ),
        201,
    )
    second_quote = _assert_status(
        client.post(
            "/api/v1/quotes",
            headers=admin_headers,
            json={"projectId": second_project["id"], "quoteNumber": "FQB-1", "title": "Quote B"},
        ),
        201,
    )

    filtered_quotes = _assert_status(
        client.get(
            f"/api/v1/quotes?projectId={first_project['id']}",
            headers=admin_headers,
        ),
        200,
    )
    all_quotes = _assert_status(client.get("/api/v1/quotes", headers=admin_headers), 200)

    assert [item["id"] for item in filtered_quotes["items"]] == [first_quote["id"]]
    assert {item["id"] for item in all_quotes["items"]} >= {first_quote["id"], second_quote["id"]}


def test_quote_version_rejects_inconsistent_financial_totals(client: TestClient) -> None:
    admin_session = _login(
        client,
        email=os.environ["DEV_ADMIN_EMAIL"],
        password=os.environ["DEV_ADMIN_PASSWORD"],
    )
    admin_headers = _bearer_headers(str(admin_session["accessToken"]))

    project = _assert_status(
        client.post(
            "/api/v1/projects",
            headers=admin_headers,
            json={"name": "Quote Validation", "status": "bid", "quoteCurrencyCode": "GBP"},
        ),
        201,
    )
    quote = _assert_status(
        client.post(
            "/api/v1/quotes",
            headers=admin_headers,
            json={"projectId": project["id"], "quoteNumber": "QV-1", "title": "Validation Quote"},
        ),
        201,
    )

    rejected_create = client.post(
        f"/api/v1/quotes/{quote['id']}/versions",
        headers=admin_headers,
        json={
            "title": "Invalid Draft",
            "currencyCode": "GBP",
            "subtotalAmount": 10000,
            "taxAmount": 0,
            "totalAmount": 10000,
            "sections": [
                {
                    "name": "Editorial",
                    "sortOrder": 1,
                    "subtotalAmount": 9000,
                    "lineItems": [
                        {
                            "sortOrder": 1,
                            "lineType": "service",
                            "description": "Offline edit",
                            "quantity": 1,
                            "unit": "project",
                            "rate": 10000,
                            "amount": 10000,
                        }
                    ],
                }
            ],
        },
    )
    assert rejected_create.status_code == 422
    assert "Section subtotal" in rejected_create.json()["detail"]

    valid_version = _assert_status(
        client.post(
            f"/api/v1/quotes/{quote['id']}/versions",
            headers=admin_headers,
            json={
                "title": "Valid Draft",
                "currencyCode": "GBP",
                "subtotalAmount": 10000,
                "taxAmount": 0,
                "totalAmount": 10000,
                "sections": [
                    {
                        "name": "Editorial",
                        "sortOrder": 1,
                        "subtotalAmount": 10000,
                        "lineItems": [
                            {
                                "sortOrder": 1,
                                "lineType": "service",
                                "description": "Offline edit",
                                "quantity": 1,
                                "unit": "project",
                                "rate": 10000,
                                "amount": 10000,
                            }
                        ],
                    }
                ],
            },
        ),
        201,
    )

    rejected_update = client.patch(
        f"/api/v1/quotes/versions/{valid_version['id']}",
        headers=admin_headers,
        json={
            "expectedUpdatedAt": valid_version["updatedAt"],
            "subtotalAmount": 10000,
            "taxAmount": 500,
            "totalAmount": 10000,
        },
    )
    assert rejected_update.status_code == 422
    assert "subtotal plus tax" in rejected_update.json()["detail"]


def test_project_actuals_vs_quote_returns_benchmark_summary_when_available(
    client: TestClient,
) -> None:
    admin_session = _login(
        client,
        email=os.environ["DEV_ADMIN_EMAIL"],
        password=os.environ["DEV_ADMIN_PASSWORD"],
    )
    admin_headers = _bearer_headers(str(admin_session["accessToken"]))

    response = _assert_status(
        client.get(
            "/api/v1/projects/project_black_glass/actuals-vs-quote",
            headers=admin_headers,
        ),
        200,
    )

    assert response["projectId"] == "project_black_glass"
    assert response["benchmarkSummary"] is not None
    assert response["benchmarkSummary"]["quotedAmount"] > 0
    assert response["benchmarkSummary"]["disciplineSummaries"]


def test_project_actuals_vs_quote_returns_null_benchmark_summary_when_unavailable(
    client: TestClient,
) -> None:
    admin_session = _login(
        client,
        email=os.environ["DEV_ADMIN_EMAIL"],
        password=os.environ["DEV_ADMIN_PASSWORD"],
    )
    admin_headers = _bearer_headers(str(admin_session["accessToken"]))

    project = _assert_status(
        client.post(
            "/api/v1/projects",
            headers=admin_headers,
            json={"name": "No Benchmark Project", "status": "bid", "quoteCurrencyCode": "GBP"},
        ),
        201,
    )

    response = _assert_status(
        client.get(f"/api/v1/projects/{project['id']}/actuals-vs-quote", headers=admin_headers),
        200,
    )

    assert response["projectId"] == project["id"]
    assert response["projectName"] == "No Benchmark Project"
    assert response["benchmarkSummary"] is None
