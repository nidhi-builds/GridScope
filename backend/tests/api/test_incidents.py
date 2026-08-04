from datetime import UTC, datetime

from sqlalchemy import event, select

from app.db.models.assets import Pole, Transformer
from app.db.models.incidents import Incident, IncidentEvidence
from app.db.models.telemetry import TelemetryEvent
from app.queries.incidents import list_incidents


def test_incident_detail_contains_operational_context(client, seeded_incident):
    response = client.get(f"/api/v1/incidents/{seeded_incident.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["boundary"]["kind"] in {"span", "corridor", "transformer", "feeder"}
    assert body["navigation"]["latitude"]
    assert body["pin"]["value"]
    assert body["confidence"]["reasons"]
    assert body["ticket_events"]
    assert body["ai_explanation"]["status"] == "fallback"
    assert body["ai_explanation"]["text"]["english"]
    assert body["ai_explanation"]["text"]["kannada"]
    assert body["ai_explanation"]["fallback_reason"] == "missing_api_key"


def test_incident_list_is_paginated(client, seeded_incident):
    response = client.get("/api/v1/incidents?page=1&page_size=25")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"items", "page", "page_size", "total"}
    assert body["total"] >= 1
    assert body["items"][0]["id"] == str(seeded_incident.id)
    assert "boundary" not in body["items"][0]


def test_incident_list_is_compact_and_uses_batched_reads(session, seeded_incident):
    session.add_all([
        Incident(
            correlation_key=f"api-list:{index}", fault_class="span", status="detected", location_class="span",
            transformer_id=seeded_incident.transformer_id, pole_id=seeded_incident.pole_id,
            pin_code="estimated", pin_source="registry", affected_count=index, confidence="high",
            confidence_reasons=[], navigation_latitude=1, navigation_longitude=1,
        ) for index in range(30)
    ])
    session.flush()
    statements = []
    listener = lambda *args: statements.append(args[2])
    event.listen(session.bind, "before_cursor_execute", listener)
    try:
        items, total = list_incidents(session, 1, 25)
    finally:
        event.remove(session.bind, "before_cursor_execute", listener)

    assert total >= 31
    assert len(statements) <= 3
    assert all("boundary" not in item for item in items)


def test_incident_detail_pages_long_evidence_without_per_row_event_reads(client, session, seeded_incident):
    now = datetime.now(UTC)
    events = [TelemetryEvent(
        pole_id=seeded_incident.pole_id, fingerprint=f"api-evidence-{index}-{now.timestamp()}", event_type="power_lost",
        payload={"energized": False}, device_time=now, received_at=now, processing_state="processed",
    ) for index in range(60)]
    session.add_all(events)
    session.flush()
    session.add_all(IncidentEvidence(
        incident_id=seeded_incident.id, telemetry_event_id=row.id, evidence_class="prior_dark"
    ) for row in events)
    session.flush()

    body = client.get(f"/api/v1/incidents/{seeded_incident.id}?evidence_page=2&evidence_page_size=10").json()

    assert body["evidence"]["total"] == 60
    assert body["evidence"]["page"] == 2
    assert len(body["evidence"]["items"]) == 10
    assert all(item["event_type"] == "power_lost" for item in body["evidence"]["items"])


def test_ticket_actions_return_resource_or_typed_conflict(client, seeded_incident):
    acknowledged = client.post(f"/api/v1/incidents/{seeded_incident.id}/acknowledge", json={"actor": "operator"})
    assigned = client.post(f"/api/v1/incidents/{seeded_incident.id}/assign", json={"actor": "operator", "crew_label": "crew-7"})
    rejected = client.post(f"/api/v1/incidents/{seeded_incident.id}/report-resolved", json={"actor": "operator"})

    assert acknowledged.json()["code"] == "ok"
    assert assigned.json()["incident"]["status"] == "crew_assigned"
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == "confirmed_dark_remains"


def test_openapi_declares_ticket_not_found_and_conflict_responses(client):
    paths = client.get("/openapi.json").json()["paths"]

    for action in ("acknowledge", "assign", "report-resolved"):
        responses = paths[f"/api/v1/incidents/{{incident_id}}/{action}"]["post"]["responses"]
        assert {"404", "409"} <= responses.keys()
