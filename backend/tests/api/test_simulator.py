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
