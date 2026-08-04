from app.detection.confidence import score_confidence


def test_high_confidence_needs_calibrated_exact_boundary_and_live_support():
    # Break caught: direct dark reports alone are labelled high confidence.
    high = score_confidence({"topology_source": "registry", "boundary_kind": "span", "direct_dark_count": 2, "post_onset_live": True})
    low = score_confidence({"topology_source": "inferred", "boundary_kind": "span", "direct_dark_count": 2, "post_onset_live": True})

    assert high.level == "high"
    assert low.level != "high"


def test_confidence_uses_measured_calibration_and_explains_coverage_and_silence():
    # Break caught: an arbitrary boolean upgrades inferred output while missing evidence is hidden.
    result = score_confidence({
        "topology_source": "inferred", "topology_validation": "valid", "inferred_calibrated": True,
        "calibration_precision": 0.89, "boundary_kind": "span", "direct_dark_count": 2,
        "post_onset_live": True, "downstream_coverage": 0.4, "silent_count": 2, "topology_ambiguity": 0.7,
    })

    assert result.level != "high"
    assert result.reasons[:3] == ("topology:inferred", "topology-validation:valid", "topology-ambiguity:0.70")
    assert "downstream-coverage:0.40" in result.reasons
    assert "silent:2" in result.reasons
