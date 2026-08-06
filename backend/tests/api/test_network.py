from sqlalchemy import func, select

from app.db.models.assets import Pole
from app.db.models.telemetry import PoleEvidenceState


def _pole_states(client) -> dict[str, str]:
    body = client.get("/api/v1/network/poles").json()
    assert body["type"] == "FeatureCollection"
    return {
        feature["properties"]["id"]: feature["properties"]["state"]
        for feature in body["features"] if feature["properties"]["asset"] == "pole"
    }


# These tests are deliberately read-only. An earlier version inserted a pole and
# mutated evidence rows; the rollback fixture did not fully contain those writes
# and they broke eight unrelated tests in the correlation, simulator and
# telemetry suites. Asserting against seeded state costs nothing here and cannot
# contaminate anything downstream.


def test_live_network_mirrors_the_recorded_state_of_every_pole(client, session):
    """The map shows what each pole actually reported, never a guess."""
    stored = {str(row.pole_id): row.evidence_class for row in session.scalars(select(PoleEvidenceState))}
    assert stored, "seed must provide poles carrying evidence state"

    reported = _pole_states(client)

    for pole_id, evidence_class in stored.items():
        assert reported[pole_id] == evidence_class


def test_a_pole_with_no_device_reads_as_uninstrumented_not_silent(client, session):
    """Silence and absence of a sensor are different facts.

    `unknown_silent` is a pole that should be reporting and is not.
    `uninstrumented` is a pole that has no device and never can. Collapsing them
    on the map would be the same error as treating silence as darkness, so a
    pole with no evidence row must never inherit a silent classification.
    """
    bare = [
        str(pole_id) for pole_id in session.scalars(
            select(Pole.id)
            .outerjoin(PoleEvidenceState, PoleEvidenceState.pole_id == Pole.id)
            .where(PoleEvidenceState.id.is_(None))
        )
    ]

    reported = _pole_states(client)

    # Every pole reaches the map, whether or not it carries a device.
    assert len(reported) == (session.scalar(select(func.count()).select_from(Pole)) or 0)
    # A pole with no evidence row must never be published as silent.
    for pole_id in bare:
        assert reported[pole_id] == "uninstrumented"


def test_live_network_draws_recorded_wiring_and_transformers(client, session):
    body = client.get("/api/v1/network/poles").json()
    assets = {feature["properties"]["asset"] for feature in body["features"]}

    assert "pole" in assets
    assert "transformer" in assets
    for feature in body["features"]:
        if feature["properties"]["asset"] == "line":
            assert feature["geometry"]["type"] == "LineString"
            assert len(feature["geometry"]["coordinates"]) == 2
