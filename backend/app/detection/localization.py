from collections.abc import Hashable, Mapping
from dataclasses import dataclass
from math import hypot
from typing import Any

from app.topology.graph import NetworkGraph


Point = tuple[float, float]


@dataclass(frozen=True)
class BoundaryResult:
    kind: str
    edge: tuple[Hashable, Hashable] | None
    pole_path: list[Hashable]
    geometry: tuple[Point, ...]
    navigation_point: Point | None
    downstream_pole_id: Hashable | None
    affected_count: int
    affected_count_estimated: bool
    transformer_id: Hashable | None = None
    feeder_id: Hashable | None = None
    branch_id: Hashable | None = None


def midpoint_of_path(points: tuple[Point, ...]) -> Point | None:
    if not points:
        return None
    if len(points) == 1:
        return points[0]
    lengths = [hypot(second[0] - first[0], second[1] - first[1]) for first, second in zip(points, points[1:])]
    remaining = sum(lengths) / 2
    for first, second, length in zip(points, points[1:], lengths):
        if remaining <= length:
            ratio = remaining / length if length else 0
            return (first[0] + (second[0] - first[0]) * ratio, first[1] + (second[1] - first[1]) * ratio)
        remaining -= length
    return points[-1]


def localize(graph: NetworkGraph, evidence: Any) -> list[BoundaryResult]:
    """Return only boundaries directly supported by live and dark evidence."""
    live, dark = _values(evidence, "live"), _values(evidence, "dark")
    assets = _value(evidence, "assets", {})
    source = _value(evidence, "topology_source", "registry")
    inferred_exact = source == "registry" or (source == "inferred" and float(_value(evidence, "calibration_precision", 0)) >= 0.90)
    roots = [node for node in dark if not any(node != other and graph.path(other, node) for other in dark)]
    results = []
    for dark_node in sorted(roots, key=str):
        path = _nearest_live_path(graph, dark_node, live)
        if not path:
            continue
        exact = len(path) == 2 and path[0] in live and inferred_exact
        pole_path = path if not exact else path
        geometry = tuple(_point(assets, node) for node in pole_path if _point(assets, node) is not None)
        downstream = path[-1]
        parent = path[-2] if len(path) > 1 else None
        results.append(BoundaryResult(
            "span" if exact else "corridor",
            (parent, downstream) if exact else None,
            pole_path,
            geometry,
            midpoint_of_path(geometry),
            downstream,
            len(graph.descendants(downstream)) + 1 if downstream in graph.graph else 0,
            source == "inferred",
            _value(evidence, "transformer_id", graph.root_id),
            _value(evidence, "feeder_id"),
            path[1] if len(path) > 1 and path[0] == graph.root_id else None,
        ))
    return results


def _nearest_live_path(graph: NetworkGraph, dark: Hashable, live: set[Hashable]) -> list[Hashable]:
    current = dark
    reverse = [dark]
    while current != graph.root_id:
        parents = list(graph.graph.predecessors(current))
        if not parents:
            break
        current = parents[0]
        reverse.append(current)
        if current in live:
            break
    return list(reversed(reverse))


def _values(value: Any, name: str) -> set[Hashable]:
    return set(_value(value, name, ()))


def _value(value: Any, name: str, default: Any = None) -> Any:
    return value.get(name, default) if isinstance(value, Mapping) else getattr(value, name, default)


def _point(assets: Any, node: Hashable) -> Point | None:
    asset = assets.get(node) if isinstance(assets, Mapping) else next((item for item in assets if _value(item, "id") == node), None)
    if asset is None:
        return None
    latitude, longitude = _value(asset, "latitude"), _value(asset, "longitude")
    return (latitude, longitude) if latitude is not None and longitude is not None else None
