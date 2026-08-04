from contextlib import contextmanager

from app.ai.service import _create_after_commit, _start_queued_explanations, queue_explanation
from app.ai.schemas import IncidentExplanationFacts
from app.ai.summary import facts_from_incident


def test_queued_post_commit_work_uses_a_frozen_fact_snapshot(monkeypatch, session, seeded_incident):
    started = []

    class RecordingThread:
        def __init__(self, target, args, daemon):
            self.args = args

        def start(self):
            started.append(self.args[0])

    monkeypatch.setattr("app.ai.service.Thread", RecordingThread)
    expected = facts_from_incident(session, seeded_incident)

    queue_explanation(session, seeded_incident)
    seeded_incident.confidence = "low"
    _start_queued_explanations(session)

    assert started == [expected]


def test_post_commit_worker_ignores_a_snapshot_without_a_committed_incident(monkeypatch):
    persisted = []

    class MissingIncidentSession:
        def get(self, *_):
            return None

    class Factory:
        @contextmanager
        def begin(self):
            yield MissingIncidentSession()

    monkeypatch.setattr("app.ai.service.SessionLocal", Factory())
    monkeypatch.setattr("app.ai.service._persist_explanation", lambda *args: persisted.append(args))

    _create_after_commit(IncidentExplanationFacts(
        incident_id="00000000-0000-0000-0000-000000000001", fault_class="span", location_class="span",
        affected_count=1, confidence="high", status="detected", asset_ids=(), boundary_ids=(),
        confidence_reasons=(), unknowns=(), navigation=(0.0, 0.0), pin_code="estimated",
    ))

    assert persisted == []
