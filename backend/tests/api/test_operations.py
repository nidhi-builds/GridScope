from sqlalchemy import select

from app.db.models.assets import Pole, Transformer
from app.db.models.incidents import Incident


def test_secondary_views_are_paginated_and_incident_geometry_is_geojson(client, seeded_incident):
    health = client.get("/api/v1/device-health?page=1&page_size=25")
    planned = client.get("/api/v1/planned-operations?page=1&page_size=25")
    geometry = client.get(f"/api/v1/network/incidents/{seeded_incident.id}")

    assert set(health.json()) == {"items", "page", "page_size", "total"}
    assert set(planned.json()) == {"items", "page", "page_size", "total"}
    assert geometry.json()["type"] == "FeatureCollection"
    assert geometry.json()["features"]


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
