from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db.models.assets import Pole, Transformer
from app.db.models.incidents import Incident, PlannedOperation, ScheduledOutage


def test_secondary_views_are_paginated_and_incident_geometry_is_geojson(client, seeded_incident):
    health = client.get("/api/v1/device-health?page=1&page_size=25")
    planned = client.get("/api/v1/planned-operations?page=1&page_size=25")
    geometry = client.get(f"/api/v1/network/incidents/{seeded_incident.id}")

    assert set(health.json()) == {"items", "page", "page_size", "total"}
    assert set(planned.json()) == {"items", "page", "page_size", "total"}
    assert geometry.json()["type"] == "FeatureCollection"
    assert geometry.json()["features"]


def test_planned_operations_expose_only_their_existing_incident_link(client, session, seeded_incident):
    now = datetime.now(UTC)
    outage = ScheduledOutage(
        external_id=f"test-operation:{seeded_incident.id}", scope={}, scheduled_start=now,
        scheduled_end=now + timedelta(hours=1), source_updated_at=now,
    )
    session.add(outage)
    session.flush()
    session.add(PlannedOperation(scheduled_outage_id=outage.id, incident_id=seeded_incident.id, status="matched_evidence"))
    session.flush()

    operation = client.get("/api/v1/planned-operations?page=1&page_size=25").json()["items"][0]

    assert operation["incident_id"] == str(seeded_incident.id)


def test_network_geometry_expands_transformer_and_feeder_asset_scopes(client, session):
    transformer = session.scalar(select(Transformer).order_by(Transformer.code))
    dt = Incident(
        correlation_key=f"api-dt:{transformer.id}", fault_class="dt", status="detected", location_class="dt",
        feeder_id=transformer.feeder_id, transformer_id=transformer.id, pin_code="estimated", pin_source="registry",
        affected_count=1, confidence="high", confidence_reasons=[], navigation_latitude=transformer.latitude,
        navigation_longitude=transformer.longitude,
    )
    feeder = Incident(
        correlation_key=f"api-feeder:{transformer.feeder_id}", fault_class="feeder", status="detected", location_class="feeder",
        feeder_id=transformer.feeder_id, pin_code="estimated", pin_source="registry", affected_count=1,
        confidence="high", confidence_reasons=[], navigation_latitude=transformer.latitude, navigation_longitude=transformer.longitude,
    )
    session.add_all([dt, feeder])
    session.flush()

    dt_assets = {item["properties"]["asset"] for item in client.get(f"/api/v1/network/incidents/{dt.id}").json()["features"]}
    feeder_assets = {item["properties"]["asset"] for item in client.get(f"/api/v1/network/incidents/{feeder.id}").json()["features"]}

    assert {"transformer", "pole"} <= dt_assets
    assert {"transformer", "pole"} <= feeder_assets
