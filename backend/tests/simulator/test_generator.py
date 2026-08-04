from collections import Counter

import pytest

from app.simulator.generator import generate_network


def test_seed_has_required_shape():
    # Break caught: an asset-count or corruption-rate change makes the seed unrealistic.
    network = generate_network(seed=20260803)

    assert len(network.substations) == 4
    assert len(network.feeders) == 12
    assert len(network.transformers) == 60
    assert 4000 <= len(network.poles) <= 4400
    assert 0.89 <= network.device_coverage <= 0.93
    assert 0.58 <= network.missing_topology_ratio <= 0.62
    assert 0.03 <= network.offline_device_ratio <= 0.05


def test_hidden_truth_is_complete_but_export_is_not():
    # Break caught: corruption mutates or leaks the simulator's complete topology truth.
    network = generate_network(seed=20260803)

    assert all(pole.parent_id is not None for pole in network.hidden_poles)
    assert any(pole.parent_id is None for pole in network.exported_poles)
    assert network.hidden_poles is not network.exported_poles


def test_default_seed_applies_exact_corruption_counts():
    # Break caught: independent corruption percentages drift through rounding or overlap.
    network = generate_network(seed=20260803)

    assert len(network.poles) == 4200
    assert len(network.devices) == 3822
    assert sum(pole.pin_code is None for pole in network.exported_poles) == 126
    assert sum(device.firmware.startswith("1.2.") for device in network.devices) == 306
    assert sum(not device.is_online for device in network.devices) == 153
    assert len({pole.transformer_id for pole in network.exported_poles if pole.parent_id is None}) == 36


def test_seed_controls_every_generated_value():
    # Break caught: global randomness or a time-based value makes a seeded run irreproducible.
    first = generate_network(seed=7)
    repeated = generate_network(seed=7)
    different = generate_network(seed=8)

    assert first == repeated
    assert first != different


def test_network_varies_dt_size_and_branch_count_without_losing_poles():
    # Break caught: a flat or malformed generator stops representing varied radial networks.
    network = generate_network(seed=20260803)
    pole_counts = Counter(pole.transformer_id for pole in network.hidden_poles)
    branch_counts = Counter(line.transformer_id for line in network.branch_polylines)

    assert sum(pole_counts.values()) == 4200
    assert min(pole_counts.values()) == 9
    assert max(pole_counts.values()) == 240
    assert 65 <= sorted(pole_counts.values())[29] <= 75
    assert set(branch_counts.values()).issubset({1, 2, 3, 4, 5})
    assert len(set(branch_counts.values())) > 1


def test_online_devices_have_bounded_staggered_heartbeat_timing():
    # Break caught: synchronized or out-of-range heartbeats invalidate silence scenarios.
    network = generate_network(seed=20260803)
    online = [device for device in network.devices if device.is_online]
    offline = [device for device in network.devices if not device.is_online]

    assert all(855 <= device.heartbeat_interval_seconds <= 945 for device in online)
    assert all(0 <= device.next_heartbeat_offset_seconds < device.heartbeat_interval_seconds for device in online)
    assert len({device.next_heartbeat_offset_seconds for device in online}) > 800
    assert all(device.next_heartbeat_offset_seconds is None for device in offline)


def test_device_signal_distributions_are_bounded_and_seeded():
    # Break caught: battery/RSSI generation drifts, collapses, or stops obeying the seed contract.
    network = generate_network(seed=20260803)
    batteries = [device.battery_pct for device in network.devices]
    signals = [device.rssi_dbm for device in network.devices]

    assert (min(batteries), max(batteries)) == (35.0, 100.0)
    assert (
        sum(value < 50 for value in batteries),
        sum(50 <= value < 80 for value in batteries),
        sum(value >= 80 for value in batteries),
    ) == (849, 1723, 1250)
    assert (min(signals), max(signals)) == (-105.0, -55.0)
    assert (
        sum(value < -90 for value in signals),
        sum(-90 <= value < -70 for value in signals),
        sum(value >= -70 for value in signals),
    ) == (1137, 1522, 1163)


def test_explicit_pole_target_is_honored():
    # Break caught: callers requesting a smaller benchmark silently receive the default size.
    network = generate_network(seed=17, pole_target=1200)

    assert len(network.poles) == 1200
    assert min(Counter(pole.transformer_id for pole in network.poles).values()) >= 9


@pytest.mark.parametrize(("pole_target", "expected_count"), ((540, 9), (14_400, 240)))
def test_pole_target_accepted_boundaries_preserve_transformer_limits(pole_target, expected_count):
    # Break caught: redistribution can create a transformer above the declared 240-pole limit.
    network = generate_network(seed=29, pole_target=pole_target)
    counts = Counter(pole.transformer_id for pole in network.poles)

    assert len(network.poles) == pole_target
    assert len(counts) == 60
    assert set(counts.values()) == {expected_count}


def test_pin_and_device_corruption_are_independent():
    # Break caught: reusing one shuffled sample makes every missing-PIN pole instrumented.
    network = generate_network(seed=20260803)
    missing_pin_ids = {pole.id for pole in network.poles if pole.pin_code is None}
    device_pole_ids = {device.pole_id for device in network.devices}

    assert missing_pin_ids - device_pole_ids
    assert missing_pin_ids & device_pole_ids
