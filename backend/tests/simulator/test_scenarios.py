from app.simulator.scenarios import SCENARIOS, scenario


def test_all_required_scenarios_are_named_and_deterministic():
    assert len(SCENARIOS) == 17
    assert tuple(SCENARIOS) == tuple(sorted(SCENARIOS))
    assert scenario("known_span").expected_incident_count == 1


def test_unobservable_presets_are_honest():
    assert scenario("firmware_12_silence").observability == "unobservable"
    assert scenario("device_death").expected_incident_count == 0


def test_every_preset_declares_the_effect_it_exercises():
    expected = {
        "device_death": {"device_unavailable", "live_downstream"},
        "dt_fault": {"dt_scope_fault"},
        "feeder_fault": {"feeder_scope_fault"},
        "firmware_12_silence": {"firmware_12_silence"},
        "inferred_span": {"inferred_topology"},
        "known_span": {"known_topology"},
        "missing_endpoints": {"missing_endpoints"},
        "noise_baseline": {"offline_baseline", "heartbeat_noise"},
        "planned_outage": {"planned_schedule", "schedule_variants"},
        "real_fault_during_schedule": {"unmatched_schedule", "span_fault"},
        "reboot_replay": {"reboot", "stale_replay"},
        "repair_relapse": {"repair", "relapse"},
        "same_path_faults": {"same_path_faults"},
        "three_branch_faults": {"independent_branches"},
        "tier_one": {"tier_one_expiry", "tier_one_promotion"},
        "transport_noise": {"duplicate", "out_of_order", "retry"},
        "weak_inferred": {"weak_inferred_topology"},
    }

    assert {key: set(definition.effects) for key, definition in SCENARIOS.items()} == expected
