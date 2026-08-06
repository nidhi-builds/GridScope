from sqlalchemy import select

from app.db.models.assets import Pole
from app.db.models.telemetry import PoleEvidenceState


def test_live_network_reports_each_pole_state_and_keeps_silence_distinct_from_no_sensor(client, session, seeded_incident):
    """Silence and absence of a sensor are different facts and must stay separate.

    A pole with no evidence row has no device and reports nothing; a pole marked
    `unknown_silent` should be reporting and is not. Collapsing them on the map
    would be the same error as treating silence as darkness.
    """
    poles = list(session.scalars(select(Pole).limit(3)))
    assert len(poles) >= 3, "seed must provide poles to classify"
    session.add(PoleEvidenceState(pole_id=poles[0].id, evidence_class="confirmed_dark", device_health="healthy"))
    session.add(PoleEvidenceState(pole_id=poles[1].id, evidence_class="unknown_silent", device_health="silent"))
    session.flush()

    body = client.get("/api/v1/network/poles").json()

    assert body["type"] == "FeatureCollection"
    states = {
        feature["properties"]["id"]: feature["properties"]["state"]
        for feature in body["features"] if feature["properties"]["asset"] == "pole"
    }
    assert states[str(poles[0].id)] == "confirmed_dark"
    assert states[str(poles[1].id)] == "unknown_silent"
    # No row at all means there is no device on that pole.
    assert states[str(poles[2].id)] == "uninstrumented"


def test_live_network_draws_recorded_wiring_and_transformers(client, session):
    body = client.get("/api/v1/network/poles").json()
    assets = {feature["properties"]["asset"] for feature in body["features"]}

    assert "pole" in assets
    assert "transformer" in assets
    for feature in body["features"]:
        if feature["properties"]["asset"] == "line":
            assert feature["geometry"]["type"] == "LineString"
            assert len(feature["geometry"]["coordinates"]) == 2
