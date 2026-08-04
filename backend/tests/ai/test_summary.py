from app.ai.summary import facts_from_incident, render_fallback
from app.db.models.incidents import IncidentBoundary


def test_persisted_incident_facts_render_a_deterministic_bilingual_fallback(session, seeded_incident):
    session.add(IncidentBoundary(
        incident_id=seeded_incident.id,
        boundary_type="span",
        upstream_pole_id=seeded_incident.pole_id,
        downstream_pole_id=seeded_incident.pole_id,
        candidate_spans=[],
        geometry={},
    ))
    session.flush()

    facts = facts_from_incident(session, seeded_incident)
    explanation = render_fallback(facts)

    assert facts.protected["incident_id"] == str(seeded_incident.id)
    assert facts.protected["affected_count"] == seeded_incident.affected_count
    assert facts.protected["boundary_ids"] == [str(seeded_incident.pole_id)]
    assert explanation.english == render_fallback(facts).english
    assert explanation.kannada
