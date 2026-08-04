from dataclasses import dataclass, replace

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db import engine
from app.db.models.assets import Substation, TopologyEdge
from app.seed import seed_if_empty
from app.simulator.generator import generate_network
from app.topology.inference import infer_tree


@dataclass(frozen=True)
class Point:
    id: str
    latitude: float
    longitude: float


DT = Point("DT", 0.0, 0.0)


def pairs(tree):
    return {(edge.parent_id, edge.child_id) for edge in tree.edges}


def test_inference_connects_every_pole_once_on_a_curved_path():
    # Break caught: an incomplete candidate graph leaves a curved branch disconnected.
    poles = (
        Point("A", 0.0, 0.0008),
        Point("B", 0.0007, 0.0015),
        Point("C", 0.0015, 0.0018),
    )

    tree = infer_tree(transformer=DT, poles=poles, span_limits=[140.0])

    assert len(tree.edges) == len(poles)
    assert tree.is_connected
    assert tree.is_acyclic
    assert pairs(tree) == {("DT", "A"), ("A", "B"), ("B", "C")}


def test_inference_keeps_nearby_opposite_branches_separate():
    # Break caught: a nearest-neighbor shortcut crosses between nearby opposite branches.
    poles = (
        Point("east-1", 0.0, 0.001),
        Point("east-2", 0.0, 0.002),
        Point("north-1", 0.001, 0.0),
        Point("north-2", 0.002, 0.0),
    )

    tree = infer_tree(transformer=DT, poles=poles, span_limits=[125.0])

    assert pairs(tree) == {
        ("DT", "east-1"),
        ("east-1", "east-2"),
        ("DT", "north-1"),
        ("north-1", "north-2"),
    }


def test_inference_adds_a_longer_candidate_only_to_restore_connectivity():
    # Break caught: a strict learned span cap leaves a remote pole out of the inferred tree.
    poles = (
        Point("A", 0.0, 0.0005),
        Point("B", 0.0, 0.0010),
        Point("C", 0.0, 0.0030),
    )

    tree = infer_tree(transformer=DT, poles=poles, span_limits=[100.0], neighbor_count=1)

    assert tree.is_connected
    assert ("B", "C") in pairs(tree)
    assert tree.edge("B", "C").distance_m > 100.0


def test_inference_stops_degraded_after_one_longer_bridge():
    # Break caught: fallback repeatedly adds long bridges and pretends a sparse DT is connected.
    poles = (
        Point("A", 0.0, 0.0005),
        Point("B", 0.0, 0.0030),
        Point("C", 0.0, 0.0060),
    )

    tree = infer_tree(transformer=DT, poles=poles, span_limits=[100.0], neighbor_count=1)

    assert tree.is_connected is False
    assert ("A", "B") in pairs(tree)
    assert all("C" not in (edge.parent_id, edge.child_id) for edge in tree.edges)


def test_inference_marks_close_competing_edges_low_margin():
    # Break caught: nearly interchangeable edges are presented as confidently inferred.
    poles = (
        Point("A", 0.0, 0.0010),
        Point("B", 0.0001, 0.0020),
        Point("C", -0.0001, 0.0020),
    )

    tree = infer_tree(transformer=DT, poles=poles, span_limits=[130.0])

    assert any(edge.calibration_bucket == "low" for edge in tree.edges)
    assert all(edge.alternative_margin >= 0.0 for edge in tree.edges)


def test_seed_persists_inferred_pole_edges_without_replacing_hidden_truth():
    # Break caught: masked DTs retain no inferred topology or overwrite simulator-only truth.
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("truncate table substations, devices cascade"))
            with Session(bind=connection) as session:
                seed_if_empty(session, seed=20260803)

                inferred = session.scalar(
                    select(func.count()).select_from(TopologyEdge).where(TopologyEdge.source == "inferred")
                )
                hidden_truth = session.scalar(
                    select(func.count()).select_from(TopologyEdge).where(TopologyEdge.source == "hidden_truth")
                )

                assert inferred > 0
                assert hidden_truth > 0
        finally:
            transaction.rollback()


def test_seed_retains_hidden_truth_and_marks_quarantined_registry(monkeypatch):
    # Break caught: registry quarantine overwrites hidden-truth provenance or duplicates its edges.
    network = generate_network(seed=20260803)
    transformer_id = next(
        transformer.id
        for transformer in network.transformers
        if transformer.id not in network.masked_transformer_ids
    )
    poles = [pole for pole in network.exported_poles if pole.transformer_id == transformer_id]
    expected_hidden_edges = sum(
        pole.transformer_id == transformer_id and pole.parent_id is not None and pole.parent_id != transformer_id
        for pole in network.hidden_poles
    )
    mutated = list(network.exported_poles)
    last_index = next(index for index, pole in enumerate(mutated) if pole.id == poles[-1].id)
    mutated[last_index] = replace(mutated[last_index], parent_id=poles[-1].id)
    monkeypatch.setattr("app.seed.generate_network", lambda seed: replace(network, exported_poles=tuple(mutated)))

    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("truncate table substations, devices cascade"))
            with Session(bind=connection) as session:
                seed_if_empty(session, seed=20260803)
                rows = session.execute(
                    select(TopologyEdge.source, TopologyEdge.calibration_bucket, TopologyEdge.is_visible).where(
                        TopologyEdge.transformer_id == transformer_id
                    )
                ).all()

                assert len(rows) == expected_hidden_edges
                assert {source for source, _, _ in rows} == {"hidden_truth"}
                assert {bucket for _, bucket, _ in rows} == {"registry_quarantined"}
                assert all(not visible for _, _, visible in rows)
        finally:
            transaction.rollback()
