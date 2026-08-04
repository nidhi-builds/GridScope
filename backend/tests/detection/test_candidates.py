from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.detection.candidates import evaluate_events
from app.detection.evidence import PoleEvidence
from app.topology.graph import NetworkGraph


NOW = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
P3, P4, P5 = uuid4(), uuid4(), uuid4()
LINE_GRAPH = NetworkGraph("DT", [("DT", P3), (P3, P4), (P4, P5)])


@dataclass(frozen=True)
class Event:
    pole_id: object
    event_type: str
    received_at: datetime
    energized: bool
    processing_state: str = "processed"


def test_one_dark_report_opens_candidate_only():
    # Break caught: one packet dispatches a fault ticket before the settle window.
    outcome = evaluate_events([Event(P4, "power_lost", NOW, False)], graph=LINE_GRAPH, now=NOW + timedelta(seconds=30))

    assert outcome.candidate_state == "investigating"
    assert outcome.incidents == []
    assert outcome.actionable is False


def test_live_child_turns_isolated_dark_into_device_issue():
    # Break caught: a downstream live report cannot defeat an isolated dark sensor.
    outcome = evaluate_events(
        [
            Event(P4, "power_lost", NOW, False),
            Event(P5, "heartbeat", NOW + timedelta(seconds=1), True),
        ],
        graph=LINE_GRAPH,
        now=NOW + timedelta(seconds=30),
    )

    assert outcome.classification == "device_issue"
    assert outcome.defeated_reason == "fresh_live_child"


def test_two_consistent_dark_reports_are_actionable_after_settle_window():
    # Break caught: corroborated dark evidence remains stuck in Tier 1.
    outcome = evaluate_events(
        [Event(P4, "power_lost", NOW, False), Event(P5, "power_lost", NOW + timedelta(seconds=2), False)],
        graph=LINE_GRAPH,
        now=NOW + timedelta(seconds=30),
    )

    assert outcome.candidate_state == "actionable"
    assert outcome.actionable is True


def test_two_dark_reports_wait_for_the_settle_window():
    # Break caught: correlated reports dispatch before the configured settle window closes.
    outcome = evaluate_events(
        [Event(P4, "power_lost", NOW, False), Event(P5, "power_lost", NOW + timedelta(seconds=2), False)],
        graph=LINE_GRAPH,
        now=NOW + timedelta(seconds=2),
    )

    assert outcome.candidate_state == "investigating"
    assert outcome.actionable is False


def test_live_parent_waits_for_the_settle_window():
    # Break caught: a live parent promotes a candidate before the settle window closes.
    outcome = evaluate_events(
        [Event(P4, "power_lost", NOW, False), Event(P3, "heartbeat", NOW + timedelta(seconds=2), True)],
        graph=LINE_GRAPH,
        now=NOW + timedelta(seconds=2),
    )

    assert outcome.candidate_state == "investigating"
    assert outcome.actionable is False


def test_live_reports_after_the_hard_deadline_are_ignored():
    # Break caught: late live reports change a closed correlation window.
    for live_pole in (P3, P5):
        outcome = evaluate_events(
            [Event(P4, "power_lost", NOW, False), Event(live_pole, "heartbeat", NOW + timedelta(seconds=50), True)],
            graph=LINE_GRAPH,
            now=NOW + timedelta(seconds=50),
        )

        assert outcome.candidate_state == "investigating"
        assert outcome.classification is None


def test_uncorroborated_dark_becomes_device_health_after_120_seconds():
    # Break caught: a lone sensor report remains an outage candidate indefinitely.
    outcome = evaluate_events([Event(P4, "power_lost", NOW, False)], graph=LINE_GRAPH, now=NOW + timedelta(seconds=120))

    assert outcome.candidate_state == "device_health"
    assert outcome.classification == "device_issue"
