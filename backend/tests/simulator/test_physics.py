from datetime import UTC, datetime
from types import SimpleNamespace

import networkx as nx

from app.simulator.physics import emit_loss_events, simulate_scope_fault, simulate_span_fault
from app.telemetry.schemas import TelemetryPayload


NOW = datetime(2026, 8, 3, tzinfo=UTC)


def test_span_fault_affects_only_descendants():
    graph = nx.DiGraph([("P1", "P2"), ("P2", "P3"), ("P3", "P4"), ("P4", "P5")])

    result = simulate_span_fault(graph, edge=("P2", "P3"), seed=7)

    assert result.deenergized == {"P3", "P4", "P5"}
    assert "P1" not in result.deenergized


def test_scope_fault_unions_complete_roots():
    graph = nx.DiGraph([("DT", "P1"), ("P1", "P2"), ("DT", "P3")])

    assert simulate_scope_fault(graph, {"P1", "P3"}).deenergized == {"P1", "P2", "P3"}


def test_scope_fault_keeps_isolated_member_roots():
    graph = nx.DiGraph([("DT", "P1")])

    assert simulate_scope_fault(graph, {"P1", "P2"}).deenergized == {"P1", "P2"}


def test_firmware_12_goes_silent():
    device = SimpleNamespace(id="D1", pole_id="P1", firmware="1.2.7", battery_pct=80, rssi_dbm=-70, is_online=True)

    assert emit_loss_events([device], occurred_at=NOW, seed=7) == []


def test_modern_messages_use_public_ingest_contract():
    device = SimpleNamespace(id="00000000-0000-0000-0000-000000000001", pole_id="00000000-0000-0000-0000-000000000002", firmware="1.3.0", battery_pct=80, rssi_dbm=-70, is_online=True)

    event = emit_loss_events([device], occurred_at=NOW, seed=1)[0]

    assert TelemetryPayload.model_validate(event).event_type == "power_lost"


def test_repair_emits_boot_and_restoration_within_twenty_seconds():
    device = SimpleNamespace(id="00000000-0000-0000-0000-000000000001", pole_id="00000000-0000-0000-0000-000000000002", firmware="1.3.0", battery_pct=80, rssi_dbm=-70, is_online=True)

    events = emit_loss_events([device], occurred_at=NOW, seed=1, repaired=True)

    assert {event["event_type"] for event in events} == {"boot", "power_restored"}
    assert all(NOW <= event["ts"] <= NOW.replace(second=20) for event in events)
