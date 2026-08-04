from collections import Counter
from collections.abc import Hashable, Iterable, Mapping
from dataclasses import dataclass

import networkx as nx

from app.topology.graph import NetworkGraph


@dataclass(frozen=True, slots=True)
class TopologyValidation:
    valid: bool
    reason: str | None = None
    graph: NetworkGraph | None = None
    quarantined: bool = False
    localization_scope: str = "tree"


def _node_details(nodes: Iterable[object] | Mapping[Hashable, object]) -> dict[Hashable, object | None]:
    if isinstance(nodes, Mapping):
        details = {}
        for node_id, node in nodes.items():
            if isinstance(node, str):
                details[node_id] = node
            elif isinstance(node, Mapping):
                details[node_id] = node.get("transformer_id")
            else:
                details[node_id] = getattr(node, "transformer_id", None)
        return details
    return {getattr(node, "id", node): getattr(node, "transformer_id", None) for node in nodes}


def _invalid(reason: str) -> TopologyValidation:
    return TopologyValidation(False, reason, quarantined=True, localization_scope="dt")


def validate_registry_tree(
    nodes: Iterable[object] | Mapping[Hashable, object], edges: Iterable[tuple[Hashable, Hashable]]
) -> TopologyValidation:
    """Validate one DT's registry edges before they become a navigable tree."""
    node_transformers = _node_details(nodes)
    edge_list = list(edges)
    transformer_ids = {value for value in node_transformers.values() if value is not None}
    if len(transformer_ids) > 1:
        return _invalid("cross_dt")

    for parent, child in edge_list:
        parent_dt = node_transformers.get(parent)
        child_dt = node_transformers.get(child)
        if parent_dt is not None and child_dt is not None and parent_dt != child_dt:
            return _invalid("cross_dt")

    child_counts = Counter(child for _, child in edge_list)
    if any(count > 1 for count in child_counts.values()):
        return _invalid("multiple_parents")

    graph = nx.DiGraph()
    graph.add_nodes_from(node_transformers)
    graph.add_edges_from(edge_list)
    if not nx.is_directed_acyclic_graph(graph):
        return _invalid("cycle")

    if graph and not nx.is_weakly_connected(graph):
        return _invalid("disconnected")

    root_id = next(iter(transformer_ids), next(iter(node_transformers), None))
    if root_id is None:
        return _invalid("disconnected")
    if root_id in graph and any(node not in nx.descendants(graph, root_id) | {root_id} for node in graph):
        return _invalid("disconnected")
    graph_edges = edge_list.copy()
    if root_id not in graph:
        graph_edges.extend((root_id, node) for node in graph if graph.in_degree(node) == 0)
    return TopologyValidation(True, graph=NetworkGraph(root_id, graph_edges))
