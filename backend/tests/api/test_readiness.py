def test_ready_reports_workflow_dependencies(client):
    response = client.get("/api/v1/ready")

    assert response.status_code == 200
    assert response.json()["database"] == "ready"
    assert response.json()["seed"] == "ready"
    assert response.json()["worker"] == "ready"
    assert {"unprocessed_count", "oldest_backlog_age_seconds", "last_processed_at"} <= response.json().keys()


def test_openapi_lists_every_operational_route(client):
    paths = client.get("/openapi.json").json()["paths"]

    assert {
        "/api/v1/telemetry", "/api/v1/telemetry/batch", "/api/v1/incidents",
        "/api/v1/incidents/{incident_id}", "/api/v1/incidents/{incident_id}/acknowledge",
        "/api/v1/incidents/{incident_id}/assign", "/api/v1/incidents/{incident_id}/report-resolved",
        "/api/v1/planned-operations", "/api/v1/device-health", "/api/v1/network/incidents/{incident_id}",
        "/api/v1/health", "/api/v1/ready",
    } <= paths.keys()
