from sqlalchemy import select

from app.db.models.assets import Pole
from app.db.models.telemetry import PoleEvidenceState


def _pole_states(client) -> dict[str, str]:
    body = client.get("/api/v1/network/poles").json()
    assert body["type"] == "FeatureCollection"
    return {
        feature["properties"]["id"]: feature["properties"]["state"]
        for feature in body["features"] if feature["properties"]["asset"] == "pole"
    }


def test_live_network_reports_the_recorded_state_of_each_pole(client, session):
    """The map must show what the pole actually reported, not a guess."""
    states = list(session.scalars(select(PoleEvidenceState).limit(2)))
    assert len(states) >= 2, "seed must provide poles carrying evidence state"
    states[0].evidence_class = "confirmed_dark"
    states[1].evidence_class = "unknown_silent"
    session.flush()

    reported = _pole_states(client)

    assert reported[str(states[0].pole_id)] == "confirmed_dark"
    assert reported[str(states[1].pole_id)] == "unknown_silent"


def test_a_pole_with_no_device_reads_as_uninstrumented_not_silent(client, session):
    """Silence and absence of a sensor are different facts.

    `unknown_silent` is a pole that should be reporting and is not.
    `uninstrumented` is a pole that has no device and never can. Collapsing them
    on the map would be the same error as treating silence as darkness, so a
    pole with no evidence row must never inherit a silent classification.
    """
    donor = session.scalars(select(Pole).limit(1)).one()
    bare = Pole(
        transformer_id=donor.transformer_id, code="TEST-POLE-NO-DEVICE",
        latitude=donor.latitude, longitude=donor.longitude, pin_code=donor.pin_code,
        parent_pole_id=None, branch_index=0, seq_on_line=None,
    )
    session.add(bare)
    session.flush()

    reported = _pole_states(client)

    assert reported[str(bare.id)] == "uninstrumented"
    assert reported[str(bare.id)] != "unknown_silent"


def test_live_network_draws_recorded_wiring_and_transformers(client, session):
    body = client.get("/api/v1/network/poles").json()
    assets = {feature["properties"]["asset"] for feature in body["features"]}

    assert "pole" in assets
    assert "transformer" in assets
    for feature in body["features"]:
        if feature["properties"]["asset"] == "line":
            assert feature["geometry"]["type"] == "LineString"
            assert len(feature["geometry"]["coordinates"]) == 2
