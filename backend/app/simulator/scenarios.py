from dataclasses import dataclass


@dataclass(frozen=True)
class ScenarioDefinition:
    key: str
    label: str
    expected_incident_count: int
    expected_classes: tuple[str, ...]
    boundary_kind: str
    observability: str = "observable"
    effects: tuple[str, ...] = ()


def _scenario(key: str, label: str, count: int, classes: tuple[str, ...] = (), boundary: str = "span", observability: str = "observable", effects: tuple[str, ...] = ()) -> ScenarioDefinition:
    return ScenarioDefinition(key, label, count, classes, boundary, observability, effects)


SCENARIOS = {
    item.key: item for item in (
        _scenario("device_death", "Device death with live downstream", 0, effects=("device_unavailable", "live_downstream")),
        _scenario("dt_fault", "Distribution transformer fault", 1, ("dt",), "dt", effects=("dt_scope_fault",)),
        _scenario("feeder_fault", "Feeder fault", 1, ("feeder",), "feeder", effects=("feeder_scope_fault",)),
        _scenario("firmware_12_silence", "Firmware 1.2 terminal silence", 0, observability="unobservable", effects=("firmware_12_silence",)),
        _scenario("inferred_span", "Inferred span fault (corridor until calibrated)", 1, ("corridor",), "corridor", effects=("inferred_topology",)),
        _scenario("known_span", "Exact known-topology span fault", 1, ("span",), "span", effects=("known_topology",)),
        _scenario("missing_endpoints", "Uninstrumented span endpoints", 1, ("corridor",), "corridor", effects=("missing_endpoints",)),
        _scenario("noise_baseline", "Offline baseline and noise", 0, effects=("offline_baseline", "heartbeat_noise")),
        _scenario("planned_outage", "Late, overrun, and cancelled schedule", 0, effects=("planned_schedule", "schedule_variants")),
        _scenario("real_fault_during_schedule", "Unmatched fault during schedule", 1, ("span",), "span", effects=("unmatched_schedule", "span_fault")),
        _scenario("reboot_replay", "Reboot and stale pre-boot replay", 0, effects=("reboot", "stale_replay")),
        _scenario("repair_relapse", "Repair, verification, and relapse", 1, ("span",), "span", effects=("repair", "relapse")),
        _scenario("same_path_faults", "Two same-path faults", 1, ("corridor",), "corridor", "limited", ("same_path_faults",)),
        _scenario("three_branch_faults", "Three independent DT branches", 3, ("span", "span", "span"), "span", effects=("independent_branches",)),
        _scenario("tier_one", "Uncorroborated and corroborated packets", 1, ("span",), "span", effects=("tier_one_expiry", "tier_one_promotion")),
        _scenario("transport_noise", "Duplicate, ordering, skew, stale delivery", 0, effects=("duplicate", "out_of_order", "retry")),
        _scenario("weak_inferred", "Weak inferred topology", 1, ("corridor",), "corridor", effects=("weak_inferred_topology",)),
    )
}


def scenario(key: str) -> ScenarioDefinition:
    try:
        return SCENARIOS[key]
    except KeyError as error:
        raise ValueError(f"unknown simulator scenario: {key}") from error
