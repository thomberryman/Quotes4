# ruff: noqa: E501

from fastapi.testclient import TestClient


def test_health_endpoint_returns_request_id(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.headers["x-request-id"]
    body = response.json()
    assert body["status"] == "ok"
    assert body["apiBasePath"] == "/api/v1"


def test_openapi_includes_ingestion_and_dashboard_routes(
    client: TestClient,
) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    payload = response.json()
    paths = payload["paths"]

    assert "/api/v1/quote-ingestion/runs" in paths
    assert "/api/v1/quote-ingestion/uploads/presign" in paths
    assert "/api/v1/actuals-imports/batches/{batch_id}/process" in paths
    assert "/api/v1/projects/{project_id}/comparables" in paths
    assert "/api/v1/dashboards/operational" in paths
