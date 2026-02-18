"""Graph-based rule embedding service.

Uses NetworkX and Node2Vec for structural similarity analysis.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlmodel import Session

from .models import (
    EmbeddingRule,
    GraphEmbedding,
)


class GraphEmbeddingService:
    """Graph-based rule embedding using NetworkX and Node2Vec.

    Converts rules to graph structures and generates embeddings
    that capture structural relationships between rule components.
    """

    def __init__(self, session: Session | None = None):
        self.session = session
        self._nx = None
        self._np = None

    @property
    def nx(self):
        """Lazy-load networkx."""
        if self._nx is None:
            try:
                import networkx as nx

                self._nx = nx
            except ImportError as err:
                raise ImportError(
                    "networkx is required for graph embeddings. Install with: pip install networkx"
                ) from err
        return self._nx

    @property
    def np(self):
        """Lazy-load numpy."""
        if self._np is None:
            try:
                import numpy as np

                self._np = np
            except ImportError as err:
                raise ImportError("numpy is required for graph embeddings. Install with: pip install numpy") from err
        return self._np

    def rule_to_graph(self, rule: EmbeddingRule) -> Any:
        """Convert a rule to a NetworkX graph."""
        nx = self.nx
        G = nx.Graph()

        rule_node_id = f"rule:{rule.rule_id}"
        G.add_node(
            rule_node_id,
            node_type="rule",
            label=rule.name,
            rule_id=rule.rule_id,
        )

        for i, condition in enumerate(rule.conditions):
            cond_node_id = f"cond:{rule.rule_id}:{i}"
            G.add_node(
                cond_node_id,
                node_type="condition",
                label=f"{condition.field} {condition.operator}",
                field=condition.field,
                operator=condition.operator,
            )
            G.add_edge(
                rule_node_id,
                cond_node_id,
                edge_type="HAS_CONDITION",
                weight=1.0,
            )

            field_parts = condition.field.split(".")
            for part in field_parts:
                entity_node_id = f"entity:{part}"
                if not G.has_node(entity_node_id):
                    G.add_node(
                        entity_node_id,
                        node_type="entity",
                        label=part,
                    )
                G.add_edge(
                    cond_node_id,
                    entity_node_id,
                    edge_type="REFERENCES_ENTITY",
                    weight=0.5,
                )

            try:
                value = json.loads(condition.value)
                if isinstance(value, str):
                    value_node_id = f"value:{value}"
                    if not G.has_node(value_node_id):
                        G.add_node(
                            value_node_id,
                            node_type="value",
                            label=str(value)[:30],
                        )
                    G.add_edge(
                        cond_node_id,
                        value_node_id,
                        edge_type="HAS_VALUE",
                        weight=0.3,
                    )
            except (json.JSONDecodeError, TypeError):
                pass

        if rule.decision:
            decision_node_id = f"decision:{rule.rule_id}"
            G.add_node(
                decision_node_id,
                node_type="decision",
                label=rule.decision.outcome,
                confidence=rule.decision.confidence,
            )
            G.add_edge(
                rule_node_id,
                decision_node_id,
                edge_type="PRODUCES_DECISION",
                weight=1.0,
            )

        for i, source in enumerate(rule.legal_sources):
            source_node_id = f"source:{rule.rule_id}:{i}"
            G.add_node(
                source_node_id,
                node_type="legal_source",
                label=source.citation[:50] if source.citation else "Unknown",
                document_id=source.document_id,
            )
            G.add_edge(
                rule_node_id,
                source_node_id,
                edge_type="CITES_SOURCE",
                weight=0.8,
            )

        return G

    def generate_graph_embedding(
        self,
        graph: Any,
        dimensions: int = 128,
        walk_length: int = 80,
        num_walks: int = 10,
        p: float = 1.0,
        q: float = 1.0,
    ) -> Any:
        """Generate an embedding for a graph using Node2Vec."""
        np = self.np

        if graph.number_of_nodes() == 0:
            return np.zeros(dimensions, dtype=np.float32)

        try:
            from node2vec import Node2Vec

            node2vec = Node2Vec(
                graph,
                dimensions=dimensions,
                walk_length=walk_length,
                num_walks=num_walks,
                p=p,
                q=q,
                workers=1,
                quiet=True,
            )
            model = node2vec.fit(window=10, min_count=1, batch_words=4)

            embeddings = []
            for node in graph.nodes():
                try:
                    embeddings.append(model.wv[str(node)])
                except KeyError:
                    continue

            if embeddings:
                return np.mean(embeddings, axis=0).astype(np.float32)
            return np.zeros(dimensions, dtype=np.float32)

        except ImportError:
            return self._fallback_embedding(graph, dimensions)

    def _fallback_embedding(self, graph: Any, dimensions: int) -> Any:
        """Generate embedding using structural features when Node2Vec unavailable."""
        np = self.np
        nx = self.nx

        features = []

        n_nodes = graph.number_of_nodes()
        n_edges = graph.number_of_edges()
        features.extend([n_nodes, n_edges])

        node_types = ["rule", "condition", "entity", "value", "decision", "legal_source"]
        for ntype in node_types:
            count = sum(1 for _, data in graph.nodes(data=True) if data.get("node_type") == ntype)
            features.append(count)

        edge_types = ["HAS_CONDITION", "REFERENCES_ENTITY", "HAS_VALUE", "PRODUCES_DECISION", "CITES_SOURCE"]
        for etype in edge_types:
            count = sum(1 for _, _, data in graph.edges(data=True) if data.get("edge_type") == etype)
            features.append(count)

        if n_nodes > 0:
            degrees = [d for _, d in graph.degree()]
            features.extend(
                [
                    np.mean(degrees),
                    np.std(degrees) if len(degrees) > 1 else 0,
                    max(degrees),
                    min(degrees),
                ]
            )
        else:
            features.extend([0, 0, 0, 0])

        features.append(nx.density(graph))
        try:
            features.append(nx.average_clustering(graph))
        except Exception:
            features.append(0)

        features = np.array(features, dtype=np.float32)

        if len(features) < dimensions:
            padded = np.zeros(dimensions, dtype=np.float32)
            padded[: len(features)] = features
            return padded
        else:
            result = np.zeros(dimensions, dtype=np.float32)
            for i, f in enumerate(features):
                result[i % dimensions] += f
            norm = np.linalg.norm(result)
            if norm > 0:
                result = result / norm
            return result

    def find_similar_by_structure(
        self,
        query_rule_id: str,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Find rules with similar graph structures."""
        from sqlmodel import select

        if not self.session:
            raise ValueError("Session required for database operations")

        stmt = select(GraphEmbedding).join(EmbeddingRule).where(EmbeddingRule.rule_id == query_rule_id)
        query_embedding = self.session.exec(stmt).first()

        if not query_embedding:
            raise ValueError(f"No graph embedding found for rule: {query_rule_id}")

        query_vector = query_embedding.get_vector_as_numpy()

        stmt = select(GraphEmbedding, EmbeddingRule).join(EmbeddingRule).where(EmbeddingRule.rule_id != query_rule_id)
        results = self.session.exec(stmt).all()

        similarities = []
        for emb, rule in results:
            try:
                other_vector = emb.get_vector_as_numpy()
                similarity = self._cosine_similarity(query_vector, other_vector)
                similarities.append(
                    {
                        "rule_id": rule.rule_id,
                        "name": rule.name,
                        "similarity_score": float(similarity),
                        "num_nodes": emb.num_nodes,
                        "num_edges": emb.num_edges,
                    }
                )
            except Exception:
                continue

        similarities.sort(key=lambda x: x["similarity_score"], reverse=True)
        return similarities[:top_k]

    def compare_graphs(
        self,
        rule_id_a: str,
        rule_id_b: str,
    ) -> dict[str, Any]:
        """Compare the graph structures of two rules."""
        from sqlmodel import select

        if not self.session:
            raise ValueError("Session required for database operations")

        np = self.np
        nx = self.nx

        stmt = select(EmbeddingRule).where(EmbeddingRule.rule_id == rule_id_a)
        rule_a = self.session.exec(stmt).first()
        if not rule_a:
            raise ValueError(f"Rule not found: {rule_id_a}")

        stmt = select(EmbeddingRule).where(EmbeddingRule.rule_id == rule_id_b)
        rule_b = self.session.exec(stmt).first()
        if not rule_b:
            raise ValueError(f"Rule not found: {rule_id_b}")

        graph_a = self.rule_to_graph(rule_a)
        graph_b = self.rule_to_graph(rule_b)

        result = {
            "rule_a": {
                "rule_id": rule_id_a,
                "num_nodes": graph_a.number_of_nodes(),
                "num_edges": graph_a.number_of_edges(),
            },
            "rule_b": {
                "rule_id": rule_id_b,
                "num_nodes": graph_b.number_of_nodes(),
                "num_edges": graph_b.number_of_edges(),
            },
        }

        def get_node_types(g):
            types = {}
            for _, data in g.nodes(data=True):
                ntype = data.get("node_type", "unknown")
                types[ntype] = types.get(ntype, 0) + 1
            return types

        types_a = get_node_types(graph_a)
        types_b = get_node_types(graph_b)
        all_types = set(types_a.keys()) | set(types_b.keys())

        result["node_type_comparison"] = {
            ntype: {
                "rule_a": types_a.get(ntype, 0),
                "rule_b": types_b.get(ntype, 0),
            }
            for ntype in all_types
        }

        entities_a = {data.get("label") for _, data in graph_a.nodes(data=True) if data.get("node_type") == "entity"}
        entities_b = {data.get("label") for _, data in graph_b.nodes(data=True) if data.get("node_type") == "entity"}

        common_entities = entities_a & entities_b
        result["common_entities"] = list(common_entities)
        result["entity_jaccard"] = len(common_entities) / len(entities_a | entities_b) if entities_a | entities_b else 0

        emb_a = self.generate_graph_embedding(graph_a)
        emb_b = self.generate_graph_embedding(graph_b)
        result["embedding_similarity"] = float(self._cosine_similarity(emb_a, emb_b))

        metrics_a = np.array(
            [
                graph_a.number_of_nodes(),
                graph_a.number_of_edges(),
                nx.density(graph_a),
            ],
            dtype=np.float32,
        )
        metrics_b = np.array(
            [
                graph_b.number_of_nodes(),
                graph_b.number_of_edges(),
                nx.density(graph_b),
            ],
            dtype=np.float32,
        )
        result["structural_similarity"] = float(self._cosine_similarity(metrics_a, metrics_b))

        return result

    def get_rule_graph_stats(self, rule_id: str) -> dict[str, Any]:
        """Get statistics about a rule's graph structure."""
        from sqlmodel import select

        if not self.session:
            raise ValueError("Session required for database operations")

        nx = self.nx

        stmt = select(EmbeddingRule).where(EmbeddingRule.rule_id == rule_id)
        rule = self.session.exec(stmt).first()
        if not rule:
            raise ValueError(f"Rule not found: {rule_id}")

        graph = self.rule_to_graph(rule)

        stats: dict[str, Any] = {
            "rule_id": rule_id,
            "num_nodes": graph.number_of_nodes(),
            "num_edges": graph.number_of_edges(),
            "density": nx.density(graph),
        }

        node_types: dict[str, int] = {}
        for _, data in graph.nodes(data=True):
            ntype = data.get("node_type", "unknown")
            node_types[ntype] = node_types.get(ntype, 0) + 1
        stats["node_types"] = node_types

        edge_types: dict[str, int] = {}
        for _, _, data in graph.edges(data=True):
            etype = data.get("edge_type", "unknown")
            edge_types[etype] = edge_types.get(etype, 0) + 1
        stats["edge_types"] = edge_types

        degrees = [d for _, d in graph.degree()]
        if degrees:
            stats["degree_stats"] = {
                "mean": sum(degrees) / len(degrees),
                "max": max(degrees),
                "min": min(degrees),
            }
        else:
            stats["degree_stats"] = {"mean": 0, "max": 0, "min": 0}

        try:
            stats["avg_clustering"] = nx.average_clustering(graph)
        except Exception:
            stats["avg_clustering"] = 0

        return stats

    def visualize_graph(
        self,
        rule_id: str,
        format: str = "json",
    ) -> dict[str, Any]:
        """Get a visualization-ready representation of a rule's graph."""
        from sqlmodel import select

        if not self.session:
            raise ValueError("Session required for database operations")

        nx = self.nx

        stmt = select(EmbeddingRule).where(EmbeddingRule.rule_id == rule_id)
        rule = self.session.exec(stmt).first()
        if not rule:
            raise ValueError(f"Rule not found: {rule_id}")

        graph = self.rule_to_graph(rule)

        if format == "json":
            return nx.node_link_data(graph)

        elif format == "dot":
            try:
                from networkx.drawing.nx_pydot import to_pydot

                pydot_graph = to_pydot(graph)
                return {"dot": pydot_graph.to_string()}
            except ImportError:
                lines = ["digraph G {"]
                for node, data in graph.nodes(data=True):
                    label = data.get("label", node)
                    ntype = data.get("node_type", "unknown")
                    lines.append(f'  "{node}" [label="{label}" type="{ntype}"];')
                for u, v, data in graph.edges(data=True):
                    etype = data.get("edge_type", "")
                    lines.append(f'  "{u}" -> "{v}" [label="{etype}"];')
                lines.append("}")
                return {"dot": "\n".join(lines)}

        else:
            raise ValueError(f"Unsupported format: {format}")

    def batch_generate_embeddings(
        self,
        rule_ids: list[str] | None = None,
    ) -> dict[str, int]:
        """Generate graph embeddings for multiple rules."""
        from sqlmodel import select

        if not self.session:
            raise ValueError("Session required for database operations")

        np = self.np
        nx = self.nx

        stmt = select(EmbeddingRule).where(EmbeddingRule.rule_id.in_(rule_ids)) if rule_ids else select(EmbeddingRule)

        rules = self.session.exec(stmt).all()

        processed = 0
        failed = 0

        for rule in rules:
            try:
                graph = self.rule_to_graph(rule)
                embedding = self.generate_graph_embedding(graph)

                graph_json = json.dumps(nx.node_link_data(graph))

                graph_emb = GraphEmbedding(
                    rule_id=rule.id,
                    embedding_vector=embedding.astype(np.float32).tobytes(),
                    vector_json=json.dumps(embedding.tolist()),
                    vector_dim=len(embedding),
                    graph_json=graph_json,
                    num_nodes=graph.number_of_nodes(),
                    num_edges=graph.number_of_edges(),
                    created_at=datetime.now(UTC),
                )

                existing_stmt = select(GraphEmbedding).where(GraphEmbedding.rule_id == rule.id)
                existing = self.session.exec(existing_stmt).first()

                if existing:
                    existing.embedding_vector = graph_emb.embedding_vector
                    existing.vector_json = graph_emb.vector_json
                    existing.vector_dim = graph_emb.vector_dim
                    existing.graph_json = graph_emb.graph_json
                    existing.num_nodes = graph_emb.num_nodes
                    existing.num_edges = graph_emb.num_edges
                    self.session.add(existing)
                else:
                    self.session.add(graph_emb)

                processed += 1

            except Exception:
                failed += 1
                continue

        self.session.commit()

        return {
            "processed": processed,
            "failed": failed,
            "total": len(rules),
        }

    def _cosine_similarity(self, a: Any, b: Any) -> float:
        """Compute cosine similarity between two vectors."""
        np = self.np

        if len(a) != len(b):
            return 0.0

        dot_product = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return float(dot_product / (norm_a * norm_b))
