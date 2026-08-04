from datetime import UTC, datetime, timedelta
from random import Random
from uuid import UUID

import networkx as nx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models.assets import Device, DeviceAssignment, Pole, TopologyEdge, Transformer
from app.db.models.incidents import Incident, IncidentBoundary, IncidentEvidence, PlannedOperation, ScheduledOutage, TicketEvent
from app.db.models.simulator import SimulatedFault, SimulatorRun
from app.db.models.telemetry import DetectionCandidate, DeviceStreamState, PoleEvidenceState, TelemetryEvent
from app.simulator.physics import emit_loss_events, simulate_scope_fault, simulate_span_fault
from app.simulator.scenarios import ScenarioDefinition, scenario
from app.incidents.workflow import transition_ticket
from app.telemetry.ingestion import accept_payload
from app.telemetry.schemas import TelemetryPayload
from app.telemetry.worker import process_inbox_batch


def _truth_graph(session: Session) -> nx.DiGraph:
    return nx.DiGraph(
        (edge.parent_pole_id, edge.child_pole_id)
        for edge in session.scalars(select(TopologyEdge).where(TopologyEdge.source.in_(("hidden_truth", "registry"))))
    )


def _devices(session: Session, pole_ids: set[UUID]):
    return session.execute(
        select(Device, DeviceAssignment.pole_id).join(DeviceAssignment, DeviceAssignment.device_id == Device.id)
        .where(DeviceAssignment.effective_to.is_(None), DeviceAssignment.pole_id.in_(pole_ids))
    ).all()


def _event_devices(rows):
    return [type("SimulatorDevice", (), {"id": device.id, "pole_id": pole_id, "firmware": device.firmware, "battery_pct": device.battery_pct, "rssi_dbm": device.rssi_dbm, "is_online": device.is_online}) for device, pole_id in rows]


def _live_anchor(session: Session, parent_id: UUID):
    row = session.execute(
        select(Device, DeviceAssignment.pole_id).join(DeviceAssignment, DeviceAssignment.device_id == Device.id)
        .where(DeviceAssignment.effective_to.is_(None), DeviceAssignment.pole_id == parent_id, Device.is_online.is_(True))
    ).first()
    return _event_devices([row])[0] if row else None


def _edge_for(session: Session, definition: ScenarioDefinition, seed: int, graph: nx.DiGraph) -> TopologyEdge | None:
    if definition.key in {"inferred_span", "weak_inferred"}:
        bucket = "high" if definition.key == "inferred_span" else "low"
        inferred = {
            (edge.parent_pole_id, edge.child_pole_id)
            for edge in session.scalars(select(TopologyEdge).where(
                TopologyEdge.source == "inferred", TopologyEdge.calibration_bucket == bucket,
            ))
        }
        edges = [
            edge for edge in session.scalars(select(TopologyEdge).where(TopologyEdge.source == "hidden_truth"))
            if (edge.parent_pole_id, edge.child_pole_id) in inferred
        ]
    else:
        source = "registry" if definition.expected_classes == ("span",) or definition.boundary_kind in {"dt", "feeder"} else "hidden_truth"
        edges = list(session.scalars(select(TopologyEdge).where(TopologyEdge.source == source).order_by(TopologyEdge.id)))
    useful = [edge for edge in edges if edge.child_pole_id in graph and len(nx.descendants(graph, edge.child_pole_id)) >= 2]
    live_parents = set(session.scalars(
        select(DeviceAssignment.pole_id).join(Device, Device.id == DeviceAssignment.device_id).where(
            DeviceAssignment.effective_to.is_(None), Device.is_online.is_(True),
        )
    ))
    choices = [edge for edge in (useful or edges) if edge.parent_pole_id in live_parents] or useful or edges
    if definition.expected_classes == ("span",):
        eventable_children = {
            pole_id for device, pole_id in session.execute(
                select(Device, DeviceAssignment.pole_id).join(DeviceAssignment, DeviceAssignment.device_id == Device.id).where(
                DeviceAssignment.effective_to.is_(None), Device.is_online.is_(True), ~Device.firmware.startswith("1.2."),
            )
            ) if Random(f"{seed}:{device.id}").random() >= 0.30
        }
        choices = [edge for edge in choices if edge.child_pole_id in eventable_children]
    return choices[Random(seed).randrange(len(choices))] if choices else None


def _edges_for(session: Session, definition: ScenarioDefinition, seed: int, graph: nx.DiGraph) -> list[TopologyEdge]:
    if definition.key != "three_branch_faults":
        edge = _edge_for(session, definition, seed, graph)
        return [edge] if edge else []
    live_parents = set(session.scalars(
        select(DeviceAssignment.pole_id).join(Device, Device.id == DeviceAssignment.device_id).where(
            DeviceAssignment.effective_to.is_(None), Device.is_online.is_(True),
        )
    ))
    grouped: dict[UUID, dict[int, list[TopologyEdge]]] = {}
    for edge, branch in session.execute(
        select(TopologyEdge, Pole.branch_index).join(Pole, Pole.id == TopologyEdge.child_pole_id).where(
            TopologyEdge.source == "registry",
        ).order_by(TopologyEdge.id)
    ):
        if edge.parent_pole_id not in live_parents or len(nx.descendants(graph, edge.child_pole_id)) < 2:
            continue
        device = session.execute(
            select(Device).join(DeviceAssignment, DeviceAssignment.device_id == Device.id).where(
                DeviceAssignment.effective_to.is_(None), DeviceAssignment.pole_id == edge.child_pole_id,
                Device.is_online.is_(True), ~Device.firmware.startswith("1.2."),
            )
        ).scalar()
        if device and Random(f"{seed}:{device.id}").random() >= 0.30:
            grouped.setdefault(edge.transformer_id, {}).setdefault(branch, []).append(edge)
    choices = [branches for branches in grouped.values() if len(branches) >= 3]
    if not choices:
        return []
    branches = choices[Random(seed).randrange(len(choices))]
    return [edges[0] for _, edges in sorted(branches.items())[:3]]


def _snapshot_state(session: Session, pole_ids: set[UUID], device_ids: set[UUID]) -> dict:
    """Keep only state this run can replace, so reset preserves real telemetry."""
    evidence = [
        {
            "pole_id": str(state.pole_id), "evidence_class": state.evidence_class,
            "source_event_id": str(state.source_event_id) if state.source_event_id else None,
            "fresh_until": state.fresh_until.isoformat() if state.fresh_until else None,
            "device_health": state.device_health, "evidence": state.evidence,
        }
        for state in session.scalars(select(PoleEvidenceState).where(PoleEvidenceState.pole_id.in_(pole_ids)))
    ]
    streams = [
        {
            "device_id": str(state.device_id), "current_epoch": state.current_epoch,
            "last_sequence": state.last_sequence, "last_device_time": state.last_device_time.isoformat(),
            "last_received_at": state.last_received_at.isoformat(),
        }
        for state in session.scalars(select(DeviceStreamState).where(DeviceStreamState.device_id.in_(device_ids)))
    ]
    return {"evidence": evidence, "streams": streams}


def _restore_state(session: Session, run: SimulatorRun, event_ids: set[UUID]) -> None:
    before = run.truth.get("before", {})
    evidence_before = {UUID(item["pole_id"]): item for item in before.get("evidence", ())}
    stream_before = {UUID(item["device_id"]): item for item in before.get("streams", ())}
    for state in session.scalars(select(PoleEvidenceState).where(PoleEvidenceState.source_event_id.in_(event_ids))):
        previous = evidence_before.get(state.pole_id)
        if previous is None:
            session.delete(state)
            continue
        state.evidence_class = previous["evidence_class"]
        state.source_event_id = UUID(previous["source_event_id"]) if previous["source_event_id"] else None
        state.fresh_until = datetime.fromisoformat(previous["fresh_until"]) if previous["fresh_until"] else None
        state.device_health = previous["device_health"]
        state.evidence = previous["evidence"]
    simulated_until = {}
    for event in session.scalars(select(TelemetryEvent).where(TelemetryEvent.id.in_(event_ids))):
        simulated_until[event.device_id] = max(simulated_until.get(event.device_id, event.received_at), event.received_at)
    device_ids = {UUID(value) for value in run.truth.get("device_ids", ())}
    for state in session.scalars(select(DeviceStreamState).where(DeviceStreamState.device_id.in_(device_ids))):
        latest_simulated_at = simulated_until.get(state.device_id)
        if latest_simulated_at is None or state.last_received_at > latest_simulated_at:
            continue
        previous = stream_before.get(state.device_id)
        if previous is None:
            session.delete(state)
            continue
        state.current_epoch = previous["current_epoch"]
        state.last_sequence = previous["last_sequence"]
        state.last_device_time = datetime.fromisoformat(previous["last_device_time"])
        state.last_received_at = datetime.fromisoformat(previous["last_received_at"])


def _accept(session: Session, run: SimulatorRun, payload: dict, received_at: datetime, accepted: list[str], event_ids: list[str]) -> None:
    result = accept_payload(session, TelemetryPayload.model_validate({**payload, "simulator_run_id": run.id}), received_at)
    accepted.append(result.outcome)
    if result.event_id:
        event_ids.append(str(result.event_id))


def _process_run(session: Session, run: SimulatorRun, now: datetime) -> None:
    schedules = list(session.scalars(
        select(ScheduledOutage).where(ScheduledOutage.external_id.like(f"sim:{run.id}:%"))
    ))
    process_inbox_batch(session, 5_000, now, schedules, run.id)


def _events(session: Session, event_ids: list[str], event_type: str | None = None) -> list[TelemetryEvent]:
    rows = [session.get(TelemetryEvent, UUID(event_id)) for event_id in event_ids]
    return [row for row in rows if row and (event_type is None or row.event_type == event_type)]


def _fault_effects(
    session: Session, run: SimulatorRun, definition: ScenarioDefinition, stages, event_ids: list[str], suppressed: set[UUID],
) -> dict[str, dict]:
    losses = _events(session, event_ids, "power_lost")
    loss_ids = [str(event.id) for event in losses]
    edge = stages[0][0] if stages else None
    deenergized = [str(pole_id) for _, result, _, _ in stages for pole_id in result.deenergized]
    if definition.key == "dt_fault":
        return {"dt_scope_fault": {"transformer_id": str(edge.transformer_id), "deenergized_pole_ids": deenergized, "loss_event_ids": loss_ids}}
    if definition.key == "feeder_fault":
        feeder_id = session.get(Transformer, edge.transformer_id).feeder_id
        transformer_ids = [str(item) for item in session.scalars(select(Transformer.id).where(Transformer.feeder_id == feeder_id))]
        return {"feeder_scope_fault": {"feeder_id": str(feeder_id), "transformer_ids": transformer_ids, "loss_event_ids": loss_ids}}
    if definition.key in {"inferred_span", "weak_inferred"}:
        return {definition.effects[0]: {"topology_source": "inferred", "calibration_bucket": "high" if definition.key == "inferred_span" else "low", "loss_event_ids": loss_ids}}
    if definition.key == "known_span":
        return {"known_topology": {"topology_source": "registry", "target_edge": [str(edge.parent_pole_id), str(edge.child_pole_id)], "loss_event_ids": loss_ids}}
    if definition.key == "missing_endpoints":
        return {"missing_endpoints": {"suppressed_endpoint_pole_ids": [str(item) for item in sorted(suppressed, key=str)], "loss_event_ids": loss_ids}}
    if definition.key == "real_fault_during_schedule":
        schedule_ids = [str(item.id) for item in session.scalars(select(ScheduledOutage).where(ScheduledOutage.external_id.like(f"sim:{run.id}:%")))]
        return {"unmatched_schedule": {"schedule_ids": schedule_ids, "fault_transformer_id": str(edge.transformer_id)}, "span_fault": {"loss_event_ids": loss_ids}}
    if definition.key == "same_path_faults":
        midpoint = len(loss_ids) // 2
        return {"same_path_faults": {"first_loss_event_ids": loss_ids[:midpoint], "second_loss_event_ids": loss_ids[midpoint:]}}
    if definition.key == "three_branch_faults":
        return {"independent_branches": {"target_edges": [[str(item.parent_pole_id), str(item.child_pole_id)] for item, *_ in stages], "loss_event_ids": loss_ids}}
    if definition.key == "tier_one":
        candidate = session.scalar(select(DetectionCandidate).where(DetectionCandidate.scope_key.like(f"sim:{run.id}:%")).order_by(DetectionCandidate.created_at))
        incident = session.scalar(select(Incident).where(Incident.simulation_id == run.id, Incident.status != "closed"))
        return {"tier_one_expiry": {"expired_candidate_id": str(candidate.id) if candidate else None}, "tier_one_promotion": {"promoted_incident_id": str(incident.id) if incident else None, "loss_event_ids": loss_ids}}
    if definition.key == "repair_relapse":
        return {}
    if definition.key == "planned_outage":
        return {}
    return {effect: {"loss_event_ids": loss_ids} for effect in definition.effects}


def _one_device(session: Session, *, firmware_12: bool = False, online: bool | None = True):
    query = select(Device, DeviceAssignment.pole_id).join(DeviceAssignment, DeviceAssignment.device_id == Device.id).where(DeviceAssignment.effective_to.is_(None))
    if firmware_12:
        query = query.where(Device.firmware.startswith("1.2."))
    if online is not None:
        query = query.where(Device.is_online.is_(online))
    row = session.execute(query.order_by(Device.id)).first()
    return _event_devices([row])[0] if row else None


def _heartbeat(device, at: datetime, seq: int = 1) -> dict:
    return {"device_id": device.id, "pole_id": device.pole_id, "seq": seq, "ts": at, "event_type": "heartbeat", "energized": True, "firmware": device.firmware, "battery": device.battery_pct, "rssi": device.rssi_dbm}


def _nonfault_effects(session: Session, run: SimulatorRun, definition: ScenarioDefinition, now: datetime, accepted: list[str], event_ids: list[str]) -> dict:
    """Exercise transport/device cases with real public payloads, never synthetic evidence rows."""
    evidence: dict[str, dict] = {}
    device = _one_device(session)
    if definition.key == "firmware_12_silence":
        legacy = _one_device(session, firmware_12=True)
        messages = emit_loss_events([legacy] if legacy else [], occurred_at=now, seed=run.seed)
        evidence["firmware_12_silence"] = {"silent_device_id": str(legacy.id) if legacy else None, "attempted_loss_event_ids": [str(message.get("id")) for message in messages if message.get("id")]}
    elif definition.key == "device_death" and device:
        device_row = session.get(Device, device.id)
        run.truth = {**run.truth, "device_online_before": {str(device.id): device_row.is_online}}
        device_row.is_online = False
        downstream = _one_device(session)
        if downstream:
            _accept(session, run, _heartbeat(downstream, now), now, accepted, event_ids)
        evidence = {
            "device_unavailable": {"observed": not device_row.is_online, "device_id": str(device.id)},
            "live_downstream": {"event_ids": list(event_ids)},
        }
    elif definition.key == "noise_baseline" and device:
        _accept(session, run, _heartbeat(device, now), now, accepted, event_ids)
        evidence = {
            "offline_baseline": {"offline_device_id": str(_one_device(session, online=False).id) if _one_device(session, online=False) else None},
            "heartbeat_noise": {"event_ids": list(event_ids)},
        }
    elif definition.key == "reboot_replay" and device:
        boot = {**_heartbeat(device, now, 0), "event_type": "boot"}
        _accept(session, run, boot, now, accepted, event_ids)
        _accept(session, run, _heartbeat(device, now - timedelta(seconds=1), 0), now + timedelta(seconds=1), accepted, event_ids)
        evidence = {"reboot": {"boot_event_ids": event_ids[:1]}, "stale_replay": {"audit_event_ids": event_ids[1:], "audit_decisions": {}}}
    elif definition.key == "transport_noise" and device:
        current = _heartbeat(device, now, 2)
        _accept(session, run, current, now, accepted, event_ids)
        _accept(session, run, current, now + timedelta(seconds=1), accepted, event_ids)
        _accept(session, run, _heartbeat(device, now + timedelta(seconds=2), 1), now + timedelta(seconds=2), accepted, event_ids)
        evidence = {
            "duplicate": {"duplicate_attempts": accepted.count("duplicate")},
            "out_of_order": {"audit_event_ids": list(event_ids), "audit_decisions": {}},
            "retry": {"retried_payload_ids": list(event_ids)},
        }
    return evidence


def start_run(session: Session, scenario_key: str, seed: int, overrides: dict | None = None) -> SimulatorRun:
    definition = scenario(scenario_key)
    now = datetime.now(UTC)
    run = SimulatorRun(seed=seed, scenario=definition.key, status="running", started_at=now, finished_at=None, truth={}, expected_results={"incident_count": definition.expected_incident_count, "classes": definition.expected_classes, "observability": definition.observability}, actual_results={})
    session.add(run)
    session.flush()
    graph = _truth_graph(session)
    edges = _edges_for(session, definition, seed, graph)
    accepted = []
    effect_evidence: dict[str, dict] = {}
    if definition.key in {"planned_outage", "real_fault_during_schedule"} and edges:
        target = edges[0].transformer_id
        if definition.key == "real_fault_during_schedule":
            target = session.scalar(select(Transformer.id).where(Transformer.id != target).order_by(Transformer.id)) or target
        variants = ("late", "overrun", "cancelled") if definition.key == "planned_outage" else ("unmatched",)
        schedule_ids = []
        for index, variant in enumerate(variants):
            scheduled = ScheduledOutage(
                external_id=f"sim:{run.id}:schedule:{index}", scope={"transformer_id": str(target)},
                scheduled_start=now - timedelta(minutes=5 + index), scheduled_end=now + timedelta(minutes=5 - index),
                source_updated_at=now,
            )
            session.add(scheduled)
            session.flush()
            schedule_ids.append(str(scheduled.id))
        effect_evidence.update({
            "planned_schedule" if definition.key == "planned_outage" else "unmatched_schedule": {"schedule_ids": schedule_ids},
            **({"schedule_variants": {"variants": list(variants)}} if definition.key == "planned_outage" else {"span_fault": {"loss_event_ids": []}}),
        })
    if edges and (definition.expected_incident_count or definition.key == "planned_outage"):
        stages = []
        for edge in edges:
            if definition.key in {"dt_fault", "planned_outage"}:
                roots = set(session.scalars(select(Pole.id).where(Pole.transformer_id == edge.transformer_id)))
                result = simulate_scope_fault(graph, roots)
            elif definition.key == "feeder_fault":
                feeder_id = session.scalar(select(Transformer.feeder_id).where(Transformer.id == edge.transformer_id))
                roots = set(session.scalars(select(Pole.id).join(Transformer).where(Transformer.feeder_id == feeder_id)))
                result = simulate_scope_fault(graph, roots)
            else:
                result = simulate_span_fault(graph, (edge.parent_pole_id, edge.child_pole_id), seed)
            devices = _event_devices(_devices(session, result.deenergized))
            anchor = _live_anchor(session, edge.parent_pole_id)
            stages.append((edge, result, devices, anchor))
        all_devices = [item for _, _, devices, anchor in stages for item in [*devices, *([anchor] if anchor else [])]]
        run.truth = {
            "before": _snapshot_state(session, {item.pole_id for item in all_devices}, {item.id for item in all_devices}),
            "device_ids": [str(item.id) for item in all_devices],
        }
        event_ids = []
        suppressed: set[UUID] = set()
        for index, (edge, result, devices, anchor) in enumerate(stages):
            occurred_at = now + timedelta(seconds=index * 60)
            session.add(SimulatedFault(
                simulator_run_id=run.id, fault_class=definition.boundary_kind,
                target={"edge": [str(edge.parent_pole_id), str(edge.child_pole_id)]}, occurred_at=occurred_at,
                repaired_at=None, truth={"deenergized": [str(item) for item in result.deenergized]},
            ))
            if definition.key == "missing_endpoints":
                suppressed.update((edge.parent_pole_id, edge.child_pole_id))
                devices = [device for device in devices if device.pole_id not in suppressed]
            losses = emit_loss_events(devices, occurred_at=occurred_at, seed=seed)
            for payload in losses:
                _accept(session, run, payload, occurred_at, accepted, event_ids)
            if definition.key == "same_path_faults":
                for payload in losses:
                    _accept(session, run, {**payload, "seq": payload["seq"] + 1, "ts": occurred_at + timedelta(seconds=1)}, occurred_at + timedelta(seconds=1), accepted, event_ids)
            if anchor:
                _accept(session, run, {
                    "device_id": anchor.id, "pole_id": anchor.pole_id, "seq": 1, "ts": occurred_at + timedelta(seconds=1),
                    "event_type": "heartbeat", "energized": True, "firmware": anchor.firmware,
                    "battery": anchor.battery_pct, "rssi": anchor.rssi_dbm,
                }, occurred_at + timedelta(seconds=1), accepted, event_ids)
            _process_run(session, run, occurred_at + timedelta(seconds=31))
        run.truth = {**run.truth, "deenergized": [str(item) for _, result, _, _ in stages for item in result.deenergized], "event_ids": event_ids}
        effect_evidence.update(_fault_effects(session, run, definition, stages, event_ids, suppressed))
    else:
        event_ids = []
        effect_evidence.update(_nonfault_effects(session, run, definition, now, accepted, event_ids))
        if event_ids:
            _process_run(session, run, now + timedelta(seconds=31))
            for details in effect_evidence.values():
                if "audit_event_ids" in details:
                    details["audit_decisions"] = {str(event.id): event.epoch_decision for event in _events(session, details["audit_event_ids"])}
        run.truth = {**run.truth, "event_ids": event_ids}
    repair_results = {}
    if definition.key == "repair_relapse":
        repair_run(session, run.id)
        repair_results = dict(run.actual_results)
        effect_evidence.update(_relapse_run(session, run))
    run.status = "completed"
    run.finished_at = datetime.now(UTC)
    observed_query = select(Incident).where(Incident.simulation_id == run.id)
    if definition.key == "repair_relapse":
        observed_query = observed_query.where(Incident.status != "closed")
    observed = list(session.scalars(observed_query))
    actual_classes = tuple(sorted(item.fault_class for item in observed))
    matched = len(observed) == definition.expected_incident_count and actual_classes == tuple(sorted(definition.expected_classes))
    run.actual_results = {
        **repair_results,
        "accepted_events": accepted.count("accepted"), "incident_count": len(observed), "classes": actual_classes,
        "outcome": "unobservable" if definition.observability == "unobservable" else ("matched" if matched else "mismatch"),
        "generated_effects": definition.effects, "effect_evidence": effect_evidence,
        "detection_elapsed_seconds": (run.finished_at - run.started_at).total_seconds(),
        "overrides": overrides or {},
    }
    session.flush()
    return run


def repair_run(session: Session, run_id: UUID) -> SimulatorRun:
    run = session.get(SimulatorRun, run_id)
    if run is None:
        raise ValueError("unknown simulator run")
    fault = session.scalar(select(SimulatedFault).where(SimulatedFault.simulator_run_id == run.id).order_by(SimulatedFault.occurred_at.desc()))
    if fault is None:
        return run
    now = datetime.now(UTC)
    pole_ids = {UUID(value) for value in fault.truth.get("deenergized", [])}
    event_ids = run.truth.get("event_ids", [])
    restoration_event_ids = []
    accepted = []
    for payload in emit_loss_events(_event_devices(_devices(session, pole_ids)), occurred_at=now, seed=run.seed, repaired=True):
        _accept(session, run, payload, now, accepted, event_ids)
        if event_ids:
            restoration_event_ids.append(event_ids[-1])
    run.truth = {**run.truth, "event_ids": event_ids}
    fault.repaired_at = now
    # Restoration evidence is not a simulator shortcut: it traverses inbox, stream ordering,
    # evidence, the ordinary operator transition, then the normal restoration verifier.
    _process_run(session, run, now + timedelta(seconds=31))
    for incident in session.scalars(select(Incident).where(Incident.simulation_id == run.id, Incident.status == "detected")):
        transition_ticket(session, incident.id, "acknowledge", "simulator", {})
        transition_ticket(session, incident.id, "assign_crew", "simulator", {})
        transition_ticket(session, incident.id, "report_resolved", "simulator", {})
    _process_run(session, run, now + timedelta(seconds=61))
    verified = all(
        incident.status == "closed"
        for incident in session.scalars(select(Incident).where(Incident.simulation_id == run.id))
    )
    run.actual_results = {
        **run.actual_results, "repair_requested_at": now.isoformat(), "repair_accepted_events": accepted.count("accepted"),
        "repair_outcome": "verified" if verified else "mismatch", "restoration_elapsed_seconds": 61,
        "restoration_event_ids": restoration_event_ids,
    }
    session.flush()
    return run


def _relapse_run(session: Session, run: SimulatorRun) -> dict[str, dict]:
    fault = session.scalar(select(SimulatedFault).where(SimulatedFault.simulator_run_id == run.id).order_by(SimulatedFault.occurred_at.desc()))
    if fault is None:
        return {}
    now = datetime.now(UTC) + timedelta(minutes=2)
    pole_ids = {UUID(value) for value in fault.truth.get("deenergized", [])}
    event_ids = run.truth.get("event_ids", [])
    accepted = []
    for payload in emit_loss_events(_event_devices(_devices(session, pole_ids)), occurred_at=now, seed=run.seed):
        _accept(session, run, {**payload, "seq": payload["seq"] + 1}, now, accepted, event_ids)
    parent_id = UUID(fault.target["edge"][0])
    if anchor := _live_anchor(session, parent_id):
        _accept(session, run, {**_heartbeat(anchor, now + timedelta(seconds=1), 2)}, now + timedelta(seconds=1), accepted, event_ids)
    run.truth = {**run.truth, "event_ids": event_ids}
    _process_run(session, run, now + timedelta(seconds=31))
    closed = session.scalar(select(Incident).where(Incident.simulation_id == run.id, Incident.status == "closed").order_by(Incident.updated_at))
    relapse = session.scalar(select(Incident).where(Incident.simulation_id == run.id, Incident.status != "closed").order_by(Incident.created_at.desc()))
    return {
        "repair": {"closed_incident_id": str(closed.id) if closed else None, "restoration_event_ids": run.actual_results.get("restoration_event_ids", [])},
        "relapse": {"incident_id": str(relapse.id) if relapse else None, "relapse_of": str(closed.id) if closed else None},
    }


def reset_runs(session: Session) -> None:
    """Remove simulator-owned effects, restoring any state it temporarily replaced."""
    for run in session.scalars(select(SimulatorRun).order_by(SimulatorRun.started_at.desc())):
        rows = [
            event for event in session.scalars(select(TelemetryEvent))
            if event.payload.get("simulator_run_id") == str(run.id)
        ]
        event_ids = {event.id for event in rows}
        _restore_state(session, run, event_ids)
        for device_id, was_online in run.truth.get("device_online_before", {}).items():
            if device := session.get(Device, UUID(device_id)):
                device.is_online = was_online
        session.execute(delete(DetectionCandidate).where(DetectionCandidate.scope_key.like(f"sim:{run.id}:%")))
        incident_ids = list(session.scalars(select(Incident.id).where(Incident.simulation_id == run.id)))
        if incident_ids:
            session.execute(delete(PlannedOperation).where(PlannedOperation.incident_id.in_(incident_ids)))
            session.execute(delete(IncidentEvidence).where(IncidentEvidence.incident_id.in_(incident_ids)))
            session.execute(delete(IncidentBoundary).where(IncidentBoundary.incident_id.in_(incident_ids)))
            session.execute(delete(TicketEvent).where(TicketEvent.incident_id.in_(incident_ids)))
            session.execute(delete(Incident).where(Incident.id.in_(incident_ids)))
        if event_ids:
            # Runs created before provenance snapshots have no prior state to restore.
            session.execute(delete(PoleEvidenceState).where(PoleEvidenceState.source_event_id.in_(event_ids)))
            session.flush()
            session.execute(delete(TelemetryEvent).where(TelemetryEvent.id.in_(event_ids)))
        session.execute(delete(SimulatedFault).where(SimulatedFault.simulator_run_id == run.id))
        schedule_ids = list(session.scalars(select(ScheduledOutage.id).where(ScheduledOutage.external_id.like(f"sim:{run.id}:%"))))
        if schedule_ids:
            session.execute(delete(PlannedOperation).where(PlannedOperation.scheduled_outage_id.in_(schedule_ids)))
            session.execute(delete(ScheduledOutage).where(ScheduledOutage.id.in_(schedule_ids)))
        session.delete(run)
    session.flush()
