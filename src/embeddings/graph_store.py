"""Graph Store — manages rule relationship graph in-memory with persistence."""

from __future__ import annotations

import json
import time
from collections import deque
from pathlib import Path

from .schemas import (
    GraphQuery,
    GraphQueryResult,
    GraphStats,
    StoreGraphEdge,
    StoreGraphNode,
)


class GraphStore:
    """In-memory graph store for rule relationships.

    Supports:
    - Node and edge CRUD operations
    - Graph traversal (BFS/DFS)
    - Path finding
    - Subgraph extraction
    - JSON file persistence
    """

    def __init__(self, persist_path: str | Path | None = None):
        self._nodes: dict[str, StoreGraphNode] = {}
        self._edges: dict[str, StoreGraphEdge] = {}

        self._outgoing: dict[str, list[str]] = {}
        self._incoming: dict[str, list[str]] = {}

        self._nodes_by_type: dict[str, set[str]] = {}
        self._nodes_by_rule: dict[str, set[str]] = {}

        self._persist_path = Path(persist_path) if persist_path else None

        if self._persist_path and self._persist_path.exists():
            self._load()

    # =========================================================================
    # Node Operations
    # =========================================================================

    def add_node(self, node: StoreGraphNode) -> str:
        """Add a node to the graph."""
        self._nodes[node.id] = node

        if node.id not in self._outgoing:
            self._outgoing[node.id] = []
        if node.id not in self._incoming:
            self._incoming[node.id] = []

        if node.node_type not in self._nodes_by_type:
            self._nodes_by_type[node.node_type] = set()
        self._nodes_by_type[node.node_type].add(node.id)

        if node.rule_id:
            if node.rule_id not in self._nodes_by_rule:
                self._nodes_by_rule[node.rule_id] = set()
            self._nodes_by_rule[node.rule_id].add(node.id)

        self._persist()
        return node.id

    def get_node(self, node_id: str) -> StoreGraphNode | None:
        """Get a node by ID."""
        return self._nodes.get(node_id)

    def get_nodes_by_type(self, node_type: str) -> list[StoreGraphNode]:
        """Get all nodes of a type."""
        node_ids = self._nodes_by_type.get(node_type, set())
        return [self._nodes[nid] for nid in node_ids if nid in self._nodes]

    def get_nodes_by_rule(self, rule_id: str) -> list[StoreGraphNode]:
        """Get all nodes for a rule."""
        node_ids = self._nodes_by_rule.get(rule_id, set())
        return [self._nodes[nid] for nid in node_ids if nid in self._nodes]

    def update_node(self, node: StoreGraphNode) -> bool:
        """Update an existing node."""
        if node.id not in self._nodes:
            return False

        old_node = self._nodes[node.id]

        if old_node.node_type != node.node_type:
            if old_node.node_type in self._nodes_by_type:
                self._nodes_by_type[old_node.node_type].discard(node.id)
            if node.node_type not in self._nodes_by_type:
                self._nodes_by_type[node.node_type] = set()
            self._nodes_by_type[node.node_type].add(node.id)

        if old_node.rule_id != node.rule_id:
            if old_node.rule_id and old_node.rule_id in self._nodes_by_rule:
                self._nodes_by_rule[old_node.rule_id].discard(node.id)
            if node.rule_id:
                if node.rule_id not in self._nodes_by_rule:
                    self._nodes_by_rule[node.rule_id] = set()
                self._nodes_by_rule[node.rule_id].add(node.id)

        self._nodes[node.id] = node
        self._persist()
        return True

    def delete_node(self, node_id: str) -> bool:
        """Delete a node and its edges."""
        if node_id not in self._nodes:
            return False

        node = self._nodes[node_id]

        for edge_id in list(self._outgoing.get(node_id, [])):
            self._delete_edge_internal(edge_id)
        for edge_id in list(self._incoming.get(node_id, [])):
            self._delete_edge_internal(edge_id)

        if node.node_type in self._nodes_by_type:
            self._nodes_by_type[node.node_type].discard(node_id)
        if node.rule_id and node.rule_id in self._nodes_by_rule:
            self._nodes_by_rule[node.rule_id].discard(node_id)

        del self._nodes[node_id]
        self._outgoing.pop(node_id, None)
        self._incoming.pop(node_id, None)

        self._persist()
        return True

    # =========================================================================
    # Edge Operations
    # =========================================================================

    def add_edge(self, edge: StoreGraphEdge) -> str:
        """Add an edge to the graph."""
        if edge.source_id not in self._nodes:
            self.add_node(StoreGraphNode(id=edge.source_id, node_type="rule", label="Unknown"))
        if edge.target_id not in self._nodes:
            self.add_node(StoreGraphNode(id=edge.target_id, node_type="rule", label="Unknown"))

        self._edges[edge.id] = edge

        if edge.source_id not in self._outgoing:
            self._outgoing[edge.source_id] = []
        self._outgoing[edge.source_id].append(edge.id)

        if edge.target_id not in self._incoming:
            self._incoming[edge.target_id] = []
        self._incoming[edge.target_id].append(edge.id)

        self._persist()
        return edge.id

    def get_edge(self, edge_id: str) -> StoreGraphEdge | None:
        """Get an edge by ID."""
        return self._edges.get(edge_id)

    def get_edges_from(self, node_id: str) -> list[StoreGraphEdge]:
        """Get all outgoing edges from a node."""
        edge_ids = self._outgoing.get(node_id, [])
        return [self._edges[eid] for eid in edge_ids if eid in self._edges]

    def get_edges_to(self, node_id: str) -> list[StoreGraphEdge]:
        """Get all incoming edges to a node."""
        edge_ids = self._incoming.get(node_id, [])
        return [self._edges[eid] for eid in edge_ids if eid in self._edges]

    def delete_edge(self, edge_id: str) -> bool:
        """Delete an edge."""
        result = self._delete_edge_internal(edge_id)
        if result:
            self._persist()
        return result

    def _delete_edge_internal(self, edge_id: str) -> bool:
        """Delete edge without persisting (internal use)."""
        if edge_id not in self._edges:
            return False

        edge = self._edges.pop(edge_id)

        if edge.source_id in self._outgoing:
            self._outgoing[edge.source_id] = [eid for eid in self._outgoing[edge.source_id] if eid != edge_id]
        if edge.target_id in self._incoming:
            self._incoming[edge.target_id] = [eid for eid in self._incoming[edge.target_id] if eid != edge_id]

        return True

    # =========================================================================
    # Graph Traversal
    # =========================================================================

    def query(self, query: GraphQuery) -> GraphQueryResult:
        """Execute a graph query."""
        start_time = time.time()

        start_nodes = self._resolve_start_nodes(query)

        if not start_nodes:
            return GraphQueryResult(query_time_ms=int((time.time() - start_time) * 1000))

        visited_nodes: set[str] = set()
        visited_edges: set[str] = set()
        paths: list[list[str]] = []

        for start_id in start_nodes:
            self._bfs_traverse(
                start_id,
                query,
                visited_nodes,
                visited_edges,
                paths,
            )

        result_nodes = [
            self._nodes[nid] for nid in visited_nodes if nid in self._nodes and len(visited_nodes) <= query.limit
        ]
        result_edges = [self._edges[eid] for eid in visited_edges if eid in self._edges]

        return GraphQueryResult(
            nodes=result_nodes[: query.limit],
            edges=result_edges,
            paths=paths[: query.limit] if paths else None,
            total_nodes=len(result_nodes),
            total_edges=len(result_edges),
            query_time_ms=int((time.time() - start_time) * 1000),
        )

    def _resolve_start_nodes(self, query: GraphQuery) -> list[str]:
        """Resolve starting nodes for a query."""
        if query.start_node_ids:
            return [nid for nid in query.start_node_ids if nid in self._nodes]
        if query.start_rule_id:
            return list(self._nodes_by_rule.get(query.start_rule_id, set()))
        if query.start_node_type:
            return list(self._nodes_by_type.get(query.start_node_type, set()))
        return []

    def _bfs_traverse(
        self,
        start_id: str,
        query: GraphQuery,
        visited_nodes: set[str],
        visited_edges: set[str],
        paths: list[list[str]],
    ) -> None:
        """BFS traversal from a start node."""
        queue: deque[tuple[str, int, list[str]]] = deque()
        queue.append((start_id, 0, [start_id]))

        while queue:
            node_id, depth, path = queue.popleft()

            if node_id in visited_nodes:
                continue

            visited_nodes.add(node_id)

            if depth > 0:
                paths.append(path)

            if depth >= query.max_depth:
                continue

            edges_to_traverse: list[StoreGraphEdge] = []

            if query.direction in ("outgoing", "both"):
                edges_to_traverse.extend(self.get_edges_from(node_id))

            if query.direction in ("incoming", "both"):
                edges_to_traverse.extend(self.get_edges_to(node_id))

            for edge in edges_to_traverse:
                if query.edge_types and edge.edge_type not in query.edge_types:
                    continue
                if query.min_weight and edge.weight < query.min_weight:
                    continue

                visited_edges.add(edge.id)

                next_id = edge.target_id if edge.source_id == node_id else edge.source_id

                if next_id not in visited_nodes:
                    next_node = self._nodes.get(next_id)
                    if query.node_types and next_node and next_node.node_type not in query.node_types:
                        continue

                    queue.append((next_id, depth + 1, path + [next_id]))

    def get_neighbors(
        self,
        node_id: str,
        edge_types: list[str] | None = None,
        direction: str = "both",
    ) -> list[StoreGraphNode]:
        """Get neighboring nodes."""
        neighbor_ids: set[str] = set()

        if direction in ("outgoing", "both"):
            for edge in self.get_edges_from(node_id):
                if edge_types is None or edge.edge_type in edge_types:
                    neighbor_ids.add(edge.target_id)

        if direction in ("incoming", "both"):
            for edge in self.get_edges_to(node_id):
                if edge_types is None or edge.edge_type in edge_types:
                    neighbor_ids.add(edge.source_id)

        return [self._nodes[nid] for nid in neighbor_ids if nid in self._nodes]

    def find_path(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 5,
    ) -> list[str] | None:
        """Find shortest path between two nodes."""
        if source_id not in self._nodes or target_id not in self._nodes:
            return None

        visited: set[str] = set()
        queue: deque[tuple[str, list[str]]] = deque()
        queue.append((source_id, [source_id]))

        while queue:
            node_id, path = queue.popleft()

            if node_id == target_id:
                return path

            if node_id in visited or len(path) > max_depth:
                continue

            visited.add(node_id)

            for edge in self.get_edges_from(node_id) + self.get_edges_to(node_id):
                next_id = edge.target_id if edge.source_id == node_id else edge.source_id
                if next_id not in visited:
                    queue.append((next_id, path + [next_id]))

        return None

    # =========================================================================
    # Subgraph Operations
    # =========================================================================

    def get_rule_subgraph(self, rule_id: str, depth: int = 1) -> GraphQueryResult:
        """Get subgraph centered on a rule."""
        return self.query(
            GraphQuery(
                start_rule_id=rule_id,
                max_depth=depth,
                direction="both",
            )
        )

    def get_connected_rules(self, rule_id: str) -> list[str]:
        """Get IDs of rules connected to a given rule."""
        connected: set[str] = set()

        for node_id in self._nodes_by_rule.get(rule_id, set()):
            for neighbor in self.get_neighbors(node_id):
                if neighbor.rule_id and neighbor.rule_id != rule_id:
                    connected.add(neighbor.rule_id)

        return list(connected)

    # =========================================================================
    # Statistics
    # =========================================================================

    def stats(self) -> GraphStats:
        """Get graph statistics."""
        nodes_by_type = {ntype: len(node_ids) for ntype, node_ids in self._nodes_by_type.items()}

        edges_by_type: dict[str, int] = {}
        for edge in self._edges.values():
            edges_by_type[edge.edge_type] = edges_by_type.get(edge.edge_type, 0) + 1

        total_nodes = len(self._nodes)
        total_edges = len(self._edges)
        avg_edges = total_edges / total_nodes if total_nodes > 0 else 0

        return GraphStats(
            total_nodes=total_nodes,
            total_edges=total_edges,
            nodes_by_type=nodes_by_type,
            edges_by_type=edges_by_type,
            rules_with_embeddings=sum(1 for node in self._nodes.values() if node.embedding is not None),
            avg_edges_per_node=round(avg_edges, 2),
        )

    # =========================================================================
    # Persistence
    # =========================================================================

    def _persist(self) -> None:
        """Persist graph to disk."""
        if not self._persist_path:
            return

        data = {
            "nodes": [node.model_dump(mode="json") for node in self._nodes.values()],
            "edges": [edge.model_dump(mode="json") for edge in self._edges.values()],
        }

        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._persist_path, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def _load(self) -> None:
        """Load graph from disk."""
        if not self._persist_path or not self._persist_path.exists():
            return

        try:
            with open(self._persist_path) as f:
                data = json.load(f)

            for node_data in data.get("nodes", []):
                node = StoreGraphNode(**node_data)
                self._nodes[node.id] = node

                if node.id not in self._outgoing:
                    self._outgoing[node.id] = []
                if node.id not in self._incoming:
                    self._incoming[node.id] = []

                if node.node_type not in self._nodes_by_type:
                    self._nodes_by_type[node.node_type] = set()
                self._nodes_by_type[node.node_type].add(node.id)

                if node.rule_id:
                    if node.rule_id not in self._nodes_by_rule:
                        self._nodes_by_rule[node.rule_id] = set()
                    self._nodes_by_rule[node.rule_id].add(node.id)

            for edge_data in data.get("edges", []):
                edge = StoreGraphEdge(**edge_data)
                self._edges[edge.id] = edge

                if edge.source_id in self._outgoing:
                    self._outgoing[edge.source_id].append(edge.id)
                if edge.target_id in self._incoming:
                    self._incoming[edge.target_id].append(edge.id)

        except Exception:
            pass

    def clear(self) -> None:
        """Clear all data from the store."""
        self._nodes.clear()
        self._edges.clear()
        self._outgoing.clear()
        self._incoming.clear()
        self._nodes_by_type.clear()
        self._nodes_by_rule.clear()
        self._persist()
