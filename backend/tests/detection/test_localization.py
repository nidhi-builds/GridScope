from dataclasses import dataclass

from app.detection.localization import localize, midpoint_of_path
from app.topology.graph import NetworkGraph


@dataclass(frozen=True)
class Pole:
    id: str
    latitude: float
    longitude: float


GRAPH = NetworkGraph("DT", [("DT", "P1"), ("P1", "P2"), ("P2", "P3"), ("P3", "P4"), ("P4", "P5")])
ASSETS = {name: Pole(name, 12.0, 77.0 + index / 100) for index, name in enumerate(("P1", "P2", "P3", "P4", "P5"))}


def test_adjacent_live_dark_boundary_returns_exact_span():
    # Break caught: an adjacent supported boundary is widened to a corridor.
    result = localize(GRAPH, {"live": {"P2"}, "dark": {"P3", "P4"}, "assets": ASSETS})

    assert result[0].kind == "span"
    assert result[0].edge == ("P2", "P3")
    assert result[0].affected_count == 3


def test_unobserved_gap_returns_containing_corridor():
    # Break caught: unknown intervening poles are incorrectly imputed dark.
    result = localize(GRAPH, {"live": {"P1"}, "dark": {"P5"}, "assets": ASSETS})

    assert result[0].kind == "corridor"
    assert result[0].pole_path == ["P1", "P2", "P3", "P4", "P5"]
    assert result[0].navigation_point == midpoint_of_path(result[0].geometry)


def test_weak_inferred_boundary_is_not_reported_as_exact_span():
    # Break caught: uncalibrated inferred geometry is presented with false precision.
    result = localize(
        GRAPH,
        {"live": {"P2"}, "dark": {"P3"}, "assets": ASSETS, "topology_source": "inferred"},
    )

    assert result[0].kind == "corridor"


def test_measured_high_precision_inferred_bucket_can_emit_exact_span():
    # Break caught: calibrated Task 3 inference is unnecessarily degraded forever.
    result = localize(
        GRAPH,
        {"live": {"P2"}, "dark": {"P3"}, "assets": ASSETS, "topology_source": "inferred", "calibration_precision": 0.95},
    )

    assert result[0].kind == "span"


def test_unknown_topology_never_claims_an_exact_span():
    # Break caught: a quarantined or absent topology is treated as a registry tree.
    result = localize(GRAPH, {"live": {"P2"}, "dark": {"P3"}, "assets": ASSETS, "topology_source": "unknown"})

    assert result[0].kind == "corridor"
