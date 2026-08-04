from collections import defaultdict
from collections.abc import Hashable, Iterable
from dataclasses import dataclass


Edge = tuple[Hashable, Hashable]


@dataclass(frozen=True, slots=True)
class ExactSpanResult:
    confidence_bucket: str
    predicted_edge: Edge
    truth_edge: Edge


@dataclass(frozen=True, slots=True)
class CorridorResult:
    candidate_edges: set[Edge] | frozenset[Edge]
    truth_edge: Edge


@dataclass(frozen=True, slots=True)
class CalibrationCase:
    inferred_edges: set[Edge] | frozenset[Edge]
    truth_edges: set[Edge] | frozenset[Edge]
    exact_spans: tuple[ExactSpanResult, ...] = ()
    corridors: tuple[CorridorResult, ...] = ()


@dataclass(frozen=True, slots=True)
class CalibrationBucket:
    exact_span_precision: float
    sample_count: int
    allow_exact_inferred: bool


@dataclass(frozen=True, slots=True)
class CalibrationReport:
    edge_precision: float
    edge_recall: float
    buckets: dict[str, CalibrationBucket]
    corridor_containment: float
    degradation_rate: float

    @property
    def allow_exact_inferred(self) -> dict[str, bool]:
        return {name: bucket.allow_exact_inferred for name, bucket in self.buckets.items()}


def calibrate_inference(cases: Iterable[CalibrationCase]) -> CalibrationReport:
    cases = tuple(cases)
    inferred = set().union(*(case.inferred_edges for case in cases)) if cases else set()
    truth = set().union(*(case.truth_edges for case in cases)) if cases else set()
    overlap = inferred & truth
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    corridor_results = [result for case in cases for result in case.corridors]
    degraded = 0
    for case in cases:
        wrong_exact = False
        for result in case.exact_spans:
            totals[result.confidence_bucket][0] += result.predicted_edge == result.truth_edge
            totals[result.confidence_bucket][1] += 1
            wrong_exact |= result.predicted_edge != result.truth_edge
        degraded += wrong_exact
    buckets = {
        name: CalibrationBucket(correct / count, count, correct / count >= 0.90)
        for name, (correct, count) in totals.items()
    }
    contained = sum(result.truth_edge in result.candidate_edges for result in corridor_results)
    return CalibrationReport(
        len(overlap) / len(inferred) if inferred else 0.0,
        len(overlap) / len(truth) if truth else 0.0,
        buckets,
        contained / len(corridor_results) if corridor_results else 0.0,
        degraded / len(cases) if cases else 0.0,
    )
