from collections.abc import Hashable, Iterable, Mapping
from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt

import networkx as nx


@dataclass(frozen=True, slots=True)
class InferredEdge:
    parent_id: Hashable
    child_id: Hashable
    distance_m: float
    alternative_margin: float
    calibration_bucket: str


@dataclass(frozen=True, slots=True)
class InferredTree:
    root_id: Hashable
    edges: tuple[InferredEdge, ...]
    is_connected: bool
    is_acyclic: bool

    def edge(self, parent_id: Hashable, child_id: Hashable) -> InferredEdge:
        return next(edge for edge in self.edges if (edge.parent_id, edge.child_id) == (parent_id, child_id))


def haversine_m(first: object, second: object) -> float:
    latitude_1, longitude_1 = radians(first.latitude), radians(first.longitude)
    latitude_2, longitude_2 = radians(second.latitude), radians(second.longitude)
    latitude_delta, longitude_delta = latitude_2 - latitude_1, longitude_2 - longitude_1
    value = sin(latitude_delta / 2) ** 2 + cos(latitude_1) * cos(latitude_2) * sin(longitude_delta / 2) ** 2
    return 6_371_000 * 2 * asin(sqrt(value))


def _span_cap(span_limits: Iterable[float] | Mapping[str, object]) -> float:
    if isinstance(span_limits, Mapping):
        if "max_length_m" in span_limits:
            return float(span_limits["max_length_m"])
        span_limits = span_limits.get("known_spans", span_limits.get("distances", ()))
    values = [float(value) for value in span_limits]
    if not values:
        raise ValueError("span_limits must include at least one known span")
    return max(values)


def _bucket(margin: float) -> str:
    if margin >= 0.50:
        return "high"
    if margin >= 0.15:
        return "medium"
    return "low"


def infer_tree(
    transformer: object,
    poles: Iterable[object],
    span_limits: Iterable[float] | Mapping[str, object],
    neighbor_count: int = 6,
) -> InferredTree:
    """Infer a DT tree from geography without assuming a straight or radial route."""
    if neighbor_count < 1:
        raise ValueError("neighbor_count must be positive")
    root_id = transformer.id
    pole_list = sorted(poles, key=lambda pole: str(pole.id))
    points = [transformer, *pole_list]
    cap = _span_cap(span_limits)
    candidates: dict[tuple[Hashable, Hashable], float] = {}
    for point in points:
        nearest = sorted(
            (
                (haversine_m(point, other), other.id)
                for other in points
                if other.id != point.id
            ),
            key=lambda item: (item[0], str(item[1])),
        )[:neighbor_count]
        for distance, other_id in nearest:
            if distance <= cap:
                key = tuple(sorted((point.id, other_id), key=str))
                candidates[key] = min(candidates.get(key, distance), distance)

    graph = nx.Graph()
    graph.add_nodes_from(point.id for point in points)
    graph.add_weighted_edges_from((first, second, distance) for (first, second), distance in candidates.items())
    if graph.number_of_nodes() > 1 and not nx.is_connected(graph):
        components = list(nx.connected_components(graph))
        bridge = min(
            (
                (haversine_m(first, second), first.id, second.id)
                for index, component in enumerate(components)
                for first in points if first.id in component
                for other_component in components[index + 1 :]
                for second in points if second.id in other_component
            ),
            key=lambda item: (item[0], str(item[1]), str(item[2])),
        )
        distance, first_id, second_id = bridge
        key = tuple(sorted((first_id, second_id), key=str))
        candidates[key] = distance
        graph.add_edge(first_id, second_id, weight=distance)

    tree = nx.minimum_spanning_tree(graph, weight="weight")
    oriented = nx.bfs_tree(tree, root_id, sort_neighbors=lambda ids: sorted(ids, key=str))
    inferred_edges = []
    for parent_id, child_id in oriented.edges:
        selected = tree[parent_id][child_id]["weight"]
        alternatives = [
            distance
            for (first, second), distance in candidates.items()
            if child_id in (first, second) and {first, second} != {parent_id, child_id}
        ]
        alternative = min(alternatives, default=selected)
        margin = max(0.0, (alternative - selected) / selected) if selected else 0.0
        inferred_edges.append(
            InferredEdge(parent_id, child_id, round(selected, 2), round(margin, 4), _bucket(margin))
        )
    return InferredTree(root_id, tuple(inferred_edges), nx.is_connected(tree), nx.is_tree(tree))
