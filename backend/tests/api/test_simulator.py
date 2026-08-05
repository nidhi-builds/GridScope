def test_simulator_lists_all_presets(client):
    response = client.get("/api/v1/simulator/scenarios")

    assert response.status_code == 200
    assert len(response.json()) == 17


def test_simulator_start_status_and_repair(client):
    created = client.post("/api/v1/simulator/runs", json={"scenario_key": "known_span", "seed": 7})

    assert created.status_code == 201
    run = created.json()
    assert run["status"] == "completed"
    assert run["actual"]["effect_evidence"]["known_topology"]["topology_source"] == "registry"
    assert run["actual"]["effect_evidence"]["known_topology"]["target_edge"]
    assert run["actual"]["effect_evidence"]["known_topology"]["loss_event_ids"]
    assert client.get(f"/api/v1/simulator/runs/{run['id']}").status_code == 200
    assert client.post(f"/api/v1/simulator/runs/{run['id']}/repair").status_code == 200


def test_reset_retries_when_the_worker_wins_a_race_on_ticket_events(client, monkeypatch):
    """Reset failed 11 times in ~200 calls once the worker drained continuously:
    it commits a ticket event between reset's child delete and its parent delete."""
    from sqlalchemy.exc import IntegrityError

    from app.api import simulator as simulator_api

    calls = {"count": 0}
    real_reset = simulator_api.reset_runs

    def flaky_reset(session):
        calls["count"] += 1
        if calls["count"] == 1:
            raise IntegrityError("ticket_events_incident_id_fkey", None, Exception("race"))
        return real_reset(session)

    monkeypatch.setattr(simulator_api, "reset_runs", flaky_reset)

    response = client.post("/api/v1/simulator/reset")

    assert response.status_code == 200
    assert response.json() == {"status": "cleared"}
    assert calls["count"] == 2
