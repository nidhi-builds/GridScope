from app.detection.classification import classify
from app.detection.localization import BoundaryResult


def boundary(transformer_id: str, branch: str, feeder_id: str = "F1") -> BoundaryResult:
    return BoundaryResult("span", ("live", branch), ["live", branch], (), None, branch, 1, False, transformer_id, feeder_id, branch)


def test_two_independent_first_level_branches_classify_as_dt():
    # Break caught: a DT loss is split into multiple span tickets.
    result = classify(
        [boundary("DT1", "A"), boundary("DT1", "B")],
        {"dt_branches": {"DT1": {"dark": {"A", "B"}, "observable": {"A", "B", "C"}}}},
    )

    assert result.kind == "dt"
    assert result.transformer_id == "DT1"


def test_feeder_requires_sixty_percent_quorum_not_two_dts():
    # Break caught: two coincident DT faults become a feeder outage on a larger feeder.
    boundaries = [boundary(f"DT{number}", "A") for number in range(1, 4)]
    result = classify(
        boundaries,
        {"feeder_dts": {"F1": {"qualifying": {"DT1", "DT2", "DT3"}, "total": 6}}},
    )

    assert result.kind == "span"


def test_fresh_live_branch_blocks_dt_scope_and_lone_branch_stays_span():
    # Break caught: a live contradiction or one observable branch becomes a DT outage.
    contradictory = classify(
        [boundary("DT1", "A"), boundary("DT1", "B")],
        {"dt_branches": {"DT1": {"dark": {"A", "B"}, "observable": {"A", "B"}, "live": {"C"}}}},
    )
    lone = classify(
        [boundary("DT2", "A")],
        {"dt_branches": {"DT2": {"dark": {"A"}, "observable": {"A"}}}},
    )

    assert contradictory.kind == "span"
    assert lone.kind == "span"
