from dataclasses import dataclass

from app.detection.location import resolve_location
from app.detection.localization import BoundaryResult


@dataclass(frozen=True)
class Pole:
    id: str
    transformer_id: str
    latitude: float
    longitude: float
    pin_code: str | None
    feeder_id: str | None = None


def test_location_uses_downstream_registry_pin_then_nearest_same_dt():
    # Break caught: missing boundary PIN triggers an unnecessary external lookup.
    boundary = BoundaryResult("span", ("P1", "P2"), ["P1", "P2"], ((12.0, 77.0), (12.0, 77.02)), None, "P2", 2, False, "DT1")
    assets = {"P1": Pole("P1", "DT1", 12.0, 77.0, "560001"), "P2": Pole("P2", "DT1", 12.0, 77.02, None)}

    result = resolve_location(boundary, assets)

    assert result.pin_code == "560001"
    assert result.pin_source == "nearest-registry"
    assert result.latitude == 12.0


def test_dt_and_feeder_locations_use_asset_and_dt_cluster():
    # Break caught: a DT/feeder is navigated as though a span had an exact break point.
    dt = BoundaryResult("dt", None, [], (), None, None, 0, False, "DT1", "F1")
    feeder = BoundaryResult("feeder", None, [], (), None, None, 0, False, None, "F1")
    assets = {
        "DT1": Pole("DT1", "unused", 12.0, 77.0, None, "F1"),
        "DT2": Pole("DT2", "unused", 14.0, 79.0, None, "F1"),
        "P1": Pole("P1", "DT1", 12.1, 77.1, "560001"),
    }

    assert resolve_location(dt, assets).latitude == 12.0
    assert (resolve_location(feeder, assets).latitude, resolve_location(feeder, assets).longitude) == (13.0, 78.0)


def test_feeder_uses_nearest_member_pole_pin_before_offline_lookup():
    # Break caught: feeder location skips its member-pole PINs and reports an invented fallback.
    feeder = BoundaryResult("feeder", None, [], (), None, None, 0, False, None, "F1")
    assets = {
        "DT1": Pole("DT1", "unused", 12.0, 77.0, None, "F1"),
        "DT2": Pole("DT2", "unused", 14.0, 79.0, None, "F1"),
        "P1": Pole("P1", "DT1", 12.9, 77.9, "560001"),
        "P2": Pole("P2", "OTHER", 13.0, 78.0, "999999"),
        "offline_pin_lookup": {"F1": "560999"},
    }

    result = resolve_location(feeder, assets)

    assert result.pin_code == "560001"
    assert result.pin_source == "nearest-registry"
