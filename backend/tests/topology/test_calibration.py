from app.topology.calibration import CalibrationCase, CorridorResult, ExactSpanResult, calibrate_inference


def test_calibration_allows_only_buckets_at_or_above_ninety_percent_precision():
    # Break caught: low-precision inferred spans remain eligible for exact operator output.
    cases = [
        CalibrationCase(
            inferred_edges={("DT", "A"), ("A", "B")},
            truth_edges={("DT", "A"), ("A", "B")},
            exact_spans=(ExactSpanResult("high", ("A", "B"), ("A", "B")),),
        ),
        CalibrationCase(
            inferred_edges={("DT", "C")},
            truth_edges={("DT", "C")},
            exact_spans=tuple(
                ExactSpanResult("medium", ("DT", "C"), truth)
                for truth in [("DT", "C")] * 8 + [("C", "D")] * 2
            ),
        ),
    ]

    report = calibrate_inference(cases)

    assert report.edge_precision == 1.0
    assert report.edge_recall == 1.0
    assert report.buckets["high"].allow_exact_inferred is True
    assert report.buckets["medium"].exact_span_precision == 0.8
    assert report.buckets["medium"].allow_exact_inferred is False


def test_calibration_reports_corridor_containment_and_degradation():
    # Break caught: degraded corridors are not measured against the hidden true span.
    report = calibrate_inference(
        [
            CalibrationCase(
                inferred_edges={("DT", "A")},
                truth_edges={("DT", "A"), ("A", "B")},
                exact_spans=(ExactSpanResult("low", ("DT", "A"), ("A", "B")),),
                corridors=(CorridorResult({("DT", "A"), ("A", "B")}, ("A", "B")),),
            ),
            CalibrationCase(
                inferred_edges={("DT", "C")},
                truth_edges={("DT", "C")},
                corridors=(CorridorResult({("DT", "C")}, ("A", "B")),),
            ),
        ]
    )

    assert report.edge_precision == 1.0
    assert report.edge_recall == 2 / 3
    assert report.corridor_containment == 0.5
    assert report.degradation_rate == 0.5
