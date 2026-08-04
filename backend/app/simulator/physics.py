from dataclasses import dataclass
from datetime import timedelta
from random import Random
from typing import Any

import networkx as nx


@dataclass(frozen=True)
class FaultResult:
    deenergized: set[Any]


def simulate_span_fault(truth_graph: nx.DiGraph, edge: tuple[Any, Any], seed: int) -> FaultResult:
    """The child side of a radial edge is the electrically dark scope."""
    del seed  # Kept in the public deterministic simulation contract.
    return FaultResult({edge[1], *nx.descendants(truth_graph, edge[1])})


def simulate_scope_fault(truth_graph: nx.DiGraph, roots: set[Any]) -> FaultResult:
    """DT/feeder faults are the union of their rooted radial scopes."""
    return FaultResult({node for root in roots for node in {root, *(nx.descendants(truth_graph, root) if root in truth_graph else ())}})


def emit_loss_events(devices, *, occurred_at, seed: int, repaired: bool = False) -> list[dict]:
    """Create public-ingest payloads; firmware 1.2 devices have no dying packet."""
    events = []
    for device in devices:
        if not getattr(device, "is_online", True) or str(device.firmware).startswith("1.2."):
            continue
        common = {
            "device_id": device.id,
            "pole_id": device.pole_id,
            "firmware": device.firmware,
            "battery": device.battery_pct,
            "rssi": device.rssi_dbm,
        }
        rng = Random(f"{seed}:{device.id}")
        if repaired:
            when = occurred_at + timedelta(seconds=rng.randrange(21))
            events.extend((
                {**common, "seq": 0, "ts": when, "event_type": "boot", "energized": True},
                {**common, "seq": 1, "ts": when, "event_type": "power_restored", "energized": True},
            ))
        elif rng.random() >= 0.30:
            events.append({**common, "seq": 1, "ts": occurred_at, "event_type": "power_lost", "energized": False})
    return events
