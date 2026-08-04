from dataclasses import dataclass

from app.topology.graph import NetworkGraph
from app.topology.importer import validate_registry_tree


@dataclass(frozen=True)
class RegistryPole:
    id: str
    transformer_id: str


def test_registry_cycle_is_quarantined():
    # Break caught: accepting a directed cycle lets downstream localization loop forever.
    result = validate_registry_tree(nodes={"A", "B"}, edges=[("A", "B"), ("B", "A")])

    assert result.valid is False
    assert result.reason == "cycle"
    assert result.quarantined is True
    assert result.localization_scope == "dt"


def test_registry_rejects_cross_dt_parent():
    # Break caught: a parent from another DT joins unrelated outage scopes.
    result = validate_registry_tree(
        nodes=[RegistryPole("A", "DT-1"), RegistryPole("B", "DT-2")],
        edges=[("A", "B")],
    )

    assert result.valid is False
    assert result.reason == "cross_dt"


def test_registry_rejects_multiple_parents_before_building_graph():
    # Break caught: one pole with two parents makes descendant counts ambiguous.
    result = validate_registry_tree(
        nodes={"DT": "DT", "A": "DT", "B": "DT", "C": "DT"},
        edges=[("DT", "A"), ("DT", "B"), ("A", "C"), ("B", "C")],
    )

    assert result.valid is False
    assert result.reason == "multiple_parents"


def test_registry_rejects_component_without_dt_root():
    # Break caught: a disconnected component is incorrectly exposed as a usable tree.
    result = validate_registry_tree(
        nodes={"DT": "DT", "A": "DT", "B": "DT", "C": "DT"},
        edges=[("DT", "A"), ("B", "C")],
    )

    assert result.valid is False
    assert result.reason == "disconnected"


def test_network_graph_returns_descendants_and_directed_path():
    # Break caught: traversal leaks siblings or reverses the parent-to-child path.
    graph = NetworkGraph("DT", [("DT", "A"), ("A", "B"), ("DT", "C")])

    assert graph.descendants("A") == {"B"}
    assert graph.path("DT", "B") == ["DT", "A", "B"]
    assert graph.path("B", "DT") == []


def test_valid_registry_connects_its_virtual_dt_root_to_pole_paths():
    # Break caught: a valid pole-only registry isolates its DT root from traversal.
    result = validate_registry_tree(
        nodes=[RegistryPole("A", "DT"), RegistryPole("B", "DT")],
        edges=[("A", "B")],
    )

    assert result.valid is True
    assert result.graph.descendants("DT") == {"A", "B"}
    assert result.graph.path("DT", "B") == ["DT", "A", "B"]
