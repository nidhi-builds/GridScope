from collections.abc import Hashable, Iterable

import networkx as nx


class NetworkGraph:
    def __init__(self, root_id: Hashable, edges: Iterable[tuple[Hashable, Hashable]] = ()):
        self.root_id = root_id
        self._graph = nx.DiGraph()
        self._graph.add_node(root_id)
        self._graph.add_edges_from(edges)

    @property
    def graph(self) -> nx.DiGraph:
        return self._graph

    def descendants(self, node_id: Hashable) -> set[Hashable]:
        return nx.descendants(self._graph, node_id)

    def path(self, ancestor_id: Hashable, descendant_id: Hashable) -> list[Hashable]:
        try:
            return nx.shortest_path(self._graph, ancestor_id, descendant_id)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []
