"""Visualization utilities for rule analytics.

Combines tree adapters, supertree adapters, and HTML rendering utilities
from Workbench core/visualization/ and shared/visualization/.
"""

from __future__ import annotations

import contextlib
import html
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from src.rules.service import (
        ConsistencyBlock,
        Rule,
    )


# ============================================================================
# Tree Adapter Data Classes
# ============================================================================


@dataclass
class NodeConsistencyInfo:
    """Consistency information for a single tree node."""

    status: str = "unverified"
    confidence: float = 0.0
    evidence: list[Any] = field(default_factory=list)
    pass_count: int = 0
    fail_count: int = 0
    warning_count: int = 0

    @property
    def color(self) -> str:
        return {
            "verified": "#28a745",
            "needs_review": "#ffc107",
            "inconsistent": "#dc3545",
            "unverified": "#6c757d",
        }.get(self.status, "#6c757d")

    @property
    def emoji(self) -> str:
        return {
            "verified": "✓",
            "needs_review": "?",
            "inconsistent": "✗",
            "unverified": "○",
        }.get(self.status, "○")

    @property
    def border_color(self) -> str:
        return {
            "verified": "#1e7e34",
            "needs_review": "#d39e00",
            "inconsistent": "#bd2130",
            "unverified": "#545b62",
        }.get(self.status, "#545b62")


@dataclass
class TreeNode:
    """A node in the visualization graph."""

    id: str
    node_type: Literal["branch", "leaf", "root"]
    label: str
    description: str | None = None
    condition_field: str | None = None
    condition_operator: str | None = None
    condition_value: str | None = None
    decision: str | None = None
    obligations: list[str] = field(default_factory=list)
    consistency: NodeConsistencyInfo = field(default_factory=NodeConsistencyInfo)
    depth: int = 0
    position: int = 0


@dataclass
class TreeEdge:
    """An edge connecting two nodes."""

    source_id: str
    target_id: str
    label: str
    is_true_branch: bool = True

    @property
    def color(self) -> str:
        return "#28a745" if self.is_true_branch else "#dc3545"

    @property
    def style(self) -> str:
        return "solid"


@dataclass
class TreeGraph:
    """Complete graph representation of a decision tree."""

    rule_id: str
    nodes: list[TreeNode] = field(default_factory=list)
    edges: list[TreeEdge] = field(default_factory=list)
    overall_status: str = "unverified"
    overall_confidence: float = 0.0
    total_pass: int = 0
    total_fail: int = 0
    total_warning: int = 0

    def get_node(self, node_id: str) -> TreeNode | None:
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def get_root(self) -> TreeNode | None:
        for node in self.nodes:
            if node.node_type == "root" or node.depth == 0:
                return node
        return self.nodes[0] if self.nodes else None

    def get_children(self, node_id: str) -> list[tuple[TreeEdge, TreeNode]]:
        result = []
        for edge in self.edges:
            if edge.source_id == node_id:
                node = self.get_node(edge.target_id)
                if node:
                    result.append((edge, node))
        return result

    def to_dot(
        self,
        show_consistency: bool = True,
        highlight_nodes: set[str] | None = None,
        highlight_edges: set[tuple[str, str]] | None = None,
    ) -> str:
        """Generate Graphviz DOT format string."""
        highlight_nodes = highlight_nodes or set()
        highlight_edges = highlight_edges or set()

        lines = [
            "digraph DecisionTree {",
            "    rankdir=TB;",
            '    node [shape=box, style="rounded,filled", fontname="Arial"];',
            '    edge [fontname="Arial", fontsize=10];',
            "",
        ]

        for node in self.nodes:
            is_highlighted = node.id in highlight_nodes

            if is_highlighted:
                fill_color = "#fff3cd"
                border_color = "#000000"
                penwidth = 4
            elif show_consistency:
                fill_color = node.consistency.color
                border_color = node.consistency.border_color
                penwidth = 2
            else:
                fill_color = "#e9ecef"
                border_color = "#495057"
                penwidth = 2

            if node.node_type == "leaf":
                label = f"{node.decision or 'Unknown'}"
                shape = "ellipse"
            else:
                if node.condition_field:
                    label = f"{node.condition_field}\\n{node.condition_operator} {node.condition_value}"
                else:
                    label = node.label
                shape = "box"

            if show_consistency and node.consistency.status != "unverified":
                label = f"{node.consistency.emoji} {label}"

            if is_highlighted:
                label = f"→ {label}"

            lines.append(
                f'    "{node.id}" ['
                f'label="{label}", '
                f"shape={shape}, "
                f'fillcolor="{fill_color}", '
                f'color="{border_color}", '
                f"penwidth={penwidth}"
                f"];"
            )

        lines.append("")

        for edge in self.edges:
            is_highlighted = (edge.source_id, edge.target_id) in highlight_edges

            if is_highlighted:
                color = "#000000"
                penwidth = 3
                style = "bold"
            else:
                color = edge.color
                penwidth = 1
                style = "solid"

            label = "T" if edge.is_true_branch else "F"
            lines.append(
                f'    "{edge.source_id}" -> "{edge.target_id}" ['
                f'label="{label}", '
                f'color="{color}", '
                f'fontcolor="{color}", '
                f"penwidth={penwidth}, "
                f"style={style}"
                f"];"
            )

        lines.append("}")
        return "\n".join(lines)

    def to_mermaid(self, show_consistency: bool = True) -> str:
        """Generate Mermaid flowchart format string."""
        lines = ["flowchart TD"]

        for node in self.nodes:
            if node.node_type == "leaf":
                label = node.decision or "Unknown"
                lines.append(f'    {node.id}(("{label}"))')
            else:
                if node.condition_field:
                    label = f"{node.condition_field} {node.condition_operator} {node.condition_value}"
                else:
                    label = node.label
                lines.append(f'    {node.id}["{label}"]')

        for edge in self.edges:
            label = "Yes" if edge.is_true_branch else "No"
            lines.append(f"    {edge.source_id} -->|{label}| {edge.target_id}")

        if show_consistency:
            lines.append("")
            for node in self.nodes:
                color = node.consistency.color.replace("#", "")
                lines.append(f"    style {node.id} fill:#{color}")

        return "\n".join(lines)


# ============================================================================
# Tree Adapter
# ============================================================================


class TreeAdapter:
    """Converts Rule decision trees to visualization graphs."""

    def __init__(self) -> None:
        self._node_counter = 0

    def _generate_node_id(self, prefix: str = "node") -> str:
        self._node_counter += 1
        return f"{prefix}_{self._node_counter}"

    def _reset_counter(self) -> None:
        self._node_counter = 0

    def convert(
        self,
        rule: Rule,
        node_consistency_map: dict[str, NodeConsistencyInfo] | None = None,
    ) -> TreeGraph:
        """Convert a Rule's decision tree to a TreeGraph."""
        self._reset_counter()
        node_consistency_map = node_consistency_map or {}

        graph = TreeGraph(rule_id=rule.rule_id)

        if rule.decision_tree is None:
            empty_node = TreeNode(
                id="empty",
                node_type="leaf",
                label="No decision tree defined",
                decision="undefined",
            )
            graph.nodes.append(empty_node)
            return graph

        self._build_tree(
            node=rule.decision_tree,
            graph=graph,
            node_consistency_map=node_consistency_map,
            depth=0,
            position=0,
        )

        if rule.consistency:
            graph.overall_status = rule.consistency.summary.status.value
            graph.overall_confidence = rule.consistency.summary.confidence
            graph.total_pass = sum(1 for e in rule.consistency.evidence if e.label == "pass")
            graph.total_fail = sum(1 for e in rule.consistency.evidence if e.label == "fail")
            graph.total_warning = sum(1 for e in rule.consistency.evidence if e.label == "warning")

        return graph

    def _build_tree(
        self,
        node: Any,
        graph: TreeGraph,
        node_consistency_map: dict[str, NodeConsistencyInfo],
        depth: int,
        position: int,
        parent_id: str | None = None,
        is_true_branch: bool = True,
    ) -> str:
        node_class = type(node).__name__
        is_leaf = node_class == "DecisionLeaf" or "result" in type(node).model_fields

        if is_leaf:
            return self._build_leaf(node, graph, node_consistency_map, depth, position, parent_id, is_true_branch)
        else:
            return self._build_branch(node, graph, node_consistency_map, depth, position, parent_id, is_true_branch)

    def _build_leaf(
        self,
        node: Any,
        graph: TreeGraph,
        node_consistency_map: dict[str, NodeConsistencyInfo],
        depth: int,
        position: int,
        parent_id: str | None,
        is_true_branch: bool,
    ) -> str:
        node_id = self._generate_node_id("leaf")
        consistency = node_consistency_map.get(node_id, NodeConsistencyInfo())

        tree_node = TreeNode(
            id=node_id,
            node_type="leaf",
            label=node.result,
            description=node.notes,
            decision=node.result,
            obligations=[obl.id for obl in node.obligations],
            consistency=consistency,
            depth=depth,
            position=position,
        )
        graph.nodes.append(tree_node)

        if parent_id:
            edge = TreeEdge(
                source_id=parent_id,
                target_id=node_id,
                label="true" if is_true_branch else "false",
                is_true_branch=is_true_branch,
            )
            graph.edges.append(edge)

        return node_id

    def _build_branch(
        self,
        node: Any,
        graph: TreeGraph,
        node_consistency_map: dict[str, NodeConsistencyInfo],
        depth: int,
        position: int,
        parent_id: str | None,
        is_true_branch: bool,
    ) -> str:
        node_id = node.node_id or self._generate_node_id("branch")
        consistency = node_consistency_map.get(node_id, NodeConsistencyInfo())

        condition_field = None
        condition_operator = None
        condition_value = None
        label = node_id

        if node.condition:
            condition_field = node.condition.field
            condition_operator = node.condition.operator
            condition_value = str(node.condition.value) if node.condition.value is not None else "null"
            label = f"{condition_field} {condition_operator} {condition_value}"

        condition_description = None
        if node.condition:
            with contextlib.suppress(AttributeError):
                condition_description = node.condition.description

        tree_node = TreeNode(
            id=node_id,
            node_type="root" if depth == 0 else "branch",
            label=label,
            description=condition_description,
            condition_field=condition_field,
            condition_operator=condition_operator,
            condition_value=condition_value,
            consistency=consistency,
            depth=depth,
            position=position,
        )
        graph.nodes.append(tree_node)

        if parent_id:
            edge = TreeEdge(
                source_id=parent_id,
                target_id=node_id,
                label="true" if is_true_branch else "false",
                is_true_branch=is_true_branch,
            )
            graph.edges.append(edge)

        next_position = 0

        if node.true_branch:
            self._build_tree(
                node=node.true_branch,
                graph=graph,
                node_consistency_map=node_consistency_map,
                depth=depth + 1,
                position=next_position,
                parent_id=node_id,
                is_true_branch=True,
            )
            next_position += 1

        if node.false_branch:
            self._build_tree(
                node=node.false_branch,
                graph=graph,
                node_consistency_map=node_consistency_map,
                depth=depth + 1,
                position=next_position,
                parent_id=node_id,
                is_true_branch=False,
            )

        return node_id

    def build_node_consistency_map(
        self,
        rule: Rule,
        consistency_block: ConsistencyBlock | None = None,
    ) -> dict[str, NodeConsistencyInfo]:
        """Build a mapping of node IDs to consistency information."""
        result: dict[str, NodeConsistencyInfo] = {}

        if consistency_block is None:
            consistency_block = rule.consistency

        if consistency_block is None:
            return result

        for evidence in consistency_block.evidence:
            node_id = evidence.rule_element or "__rule__"

            if node_id not in result:
                result[node_id] = NodeConsistencyInfo()

            result[node_id].evidence.append(evidence)

            if evidence.label == "pass":
                result[node_id].pass_count += 1
            elif evidence.label == "fail":
                result[node_id].fail_count += 1
            elif evidence.label == "warning":
                result[node_id].warning_count += 1

        for info in result.values():
            if info.fail_count > 0:
                info.status = "inconsistent"
            elif info.warning_count > 0:
                info.status = "needs_review"
            elif info.pass_count > 0:
                info.status = "verified"
            else:
                info.status = "unverified"

            total = info.pass_count + info.fail_count + info.warning_count
            if total > 0:
                info.confidence = info.pass_count / total

        return result


# ============================================================================
# Convenience Functions
# ============================================================================


def rule_to_graph(
    rule: Rule,
    include_consistency: bool = True,
) -> TreeGraph:
    """Convert a rule to a tree graph."""
    adapter = TreeAdapter()

    node_map = {}
    if include_consistency and rule.consistency:
        node_map = adapter.build_node_consistency_map(rule)

    return adapter.convert(rule, node_map)


def render_dot(
    graph: TreeGraph,
    show_consistency: bool = True,
    highlight_nodes: set[str] | None = None,
    highlight_edges: set[tuple[str, str]] | None = None,
) -> str:
    """Render a tree graph as Graphviz DOT format."""
    return graph.to_dot(
        show_consistency=show_consistency,
        highlight_nodes=highlight_nodes,
        highlight_edges=highlight_edges,
    )


def render_mermaid(graph: TreeGraph, show_consistency: bool = True) -> str:
    """Render a tree graph as Mermaid flowchart format."""
    return graph.to_mermaid(show_consistency=show_consistency)


def extract_trace_path(trace: list) -> tuple[set[str], set[tuple[str, str]]]:
    """Extract highlighted nodes and edges from a decision trace."""
    highlight_nodes: set[str] = set()
    highlight_edges: set[tuple[str, str]] = set()

    prev_node_id = None

    for step in trace:
        node_id = getattr(step, "node_path", None) or getattr(step, "node", None)

        if node_id:
            if "." in node_id:
                parts = node_id.split(".")
                for part in reversed(parts):
                    if not part.startswith("all[") and not part.startswith("any["):
                        node_id = part
                        break

            highlight_nodes.add(node_id)

            if prev_node_id and prev_node_id != node_id:
                highlight_edges.add((prev_node_id, node_id))

            prev_node_id = node_id

    return highlight_nodes, highlight_edges


# ============================================================================
# Supertree Adapters
# ============================================================================


def build_rulebook_outline(rules: list[Rule]) -> dict:
    """Build a tree structure representing the rulebook outline."""
    legal_docs = []
    try:
        from src.rag.corpus_loader import load_all_legal_documents

        legal_docs = list(load_all_legal_documents())
    except Exception:
        pass

    rule_coverage: dict[str, dict[str, list[Any]]] = defaultdict(lambda: defaultdict(list))
    unlinked_rules: list[Any] = []

    for rule in rules:
        if rule.source and rule.source.document_id:
            doc_id = rule.source.document_id
            article = rule.source.article or "General"
            match = re.search(r"(\d+)", str(article))
            if match:
                article = match.group(1)
            rule_coverage[doc_id][article].append(rule)
        else:
            unlinked_rules.append(rule)

    doc_children = []

    for doc in legal_docs:
        doc_articles = _extract_articles_from_text(doc.text)
        doc_rules_map = rule_coverage.get(doc.document_id, {})

        article_children = []
        total_doc_rules = 0

        for article_num in sorted(doc_articles, key=lambda x: int(x) if x.isdigit() else 0):
            article_rules = doc_rules_map.get(article_num, [])
            total_doc_rules += len(article_rules)

            rule_nodes = [
                {
                    "title": r.rule_id,
                    "description": r.description or "",
                    "tags": r.tags,
                    "version": r.version,
                }
                for r in article_rules
            ]

            article_node: dict[str, Any] = {
                "title": f"Article {article_num}",
                "count": len(article_rules),
                "status": "covered" if article_rules else "gap",
            }
            if rule_nodes:
                article_node["children"] = rule_nodes

            article_children.append(article_node)

        for article_num, article_rules in doc_rules_map.items():
            if article_num not in doc_articles and article_num != "General":
                total_doc_rules += len(article_rules)
                rule_nodes = [
                    {
                        "title": r.rule_id,
                        "description": r.description or "",
                        "tags": r.tags,
                    }
                    for r in article_rules
                ]
                article_children.append(
                    {
                        "title": f"Article {article_num}",
                        "count": len(article_rules),
                        "status": "covered",
                        "children": rule_nodes,
                    }
                )

        doc_children.append(
            {
                "title": doc.title or doc.document_id,
                "document_id": doc.document_id,
                "citation": doc.citation,
                "jurisdiction": doc.jurisdiction,
                "articles": len(doc_articles),
                "rules": total_doc_rules,
                "children": article_children,
            }
        )

    for doc_id, articles_map in rule_coverage.items():
        if not any(d.document_id == doc_id for d in legal_docs):
            article_children = []
            total_rules = 0
            for article_num, article_rules in sorted(articles_map.items()):
                total_rules += len(article_rules)
                rule_nodes = [
                    {
                        "title": r.rule_id,
                        "description": r.description or "",
                        "tags": r.tags,
                    }
                    for r in article_rules
                ]
                article_children.append(
                    {
                        "title": f"Article {article_num}" if article_num != "General" else "General",
                        "count": len(article_rules),
                        "children": rule_nodes,
                    }
                )

            doc_children.append(
                {
                    "title": doc_id.replace("_", " ").title(),
                    "document_id": doc_id,
                    "rules": total_rules,
                    "children": article_children,
                }
            )

    if unlinked_rules:
        unlinked_nodes = [
            {
                "title": r.rule_id,
                "description": r.description or "",
                "tags": r.tags,
            }
            for r in unlinked_rules
        ]
        doc_children.append(
            {
                "title": "Unlinked Rules",
                "count": len(unlinked_rules),
                "children": unlinked_nodes,
            }
        )

    return {
        "title": "Legal Corpus & Rulebook",
        "total_rules": len(rules),
        "documents": len(doc_children),
        "children": doc_children,
    }


def build_decision_trace_tree(
    trace: list[Any],
    decision: str | None = None,
    rule_id: str | None = None,
) -> dict:
    """Build a tree structure from a decision trace."""
    if not trace:
        return {
            "title": "Decision Trace",
            "rule_id": rule_id,
            "decision": decision,
            "children": [],
        }

    trace_nodes = []
    for step in trace:
        node: dict[str, Any] = {
            "title": step.node,
            "condition": step.condition,
            "result": step.result,
            "result_label": "TRUE" if step.result else "FALSE",
        }
        if step.value_checked is not None:
            node["value_checked"] = step.value_checked
        trace_nodes.append(node)

    return {
        "title": "Decision Trace",
        "rule_id": rule_id,
        "decision": decision,
        "steps": len(trace),
        "children": trace_nodes,
    }


def build_ontology_tree() -> dict:
    """Build a tree structure representing the regulatory ontology."""
    from src.ontology.instrument import ActivityType, InstrumentType
    from src.ontology.types import ActorType, ProvisionType

    def enum_to_children(enum_class: Any) -> list[dict]:
        return [{"title": e.value, "name": e.name} for e in enum_class]

    return {
        "title": "Regulatory Ontology",
        "children": [
            {
                "title": "Actor Types",
                "description": "Types of regulated entities",
                "children": enum_to_children(ActorType),
            },
            {
                "title": "Instrument Types",
                "description": "Types of crypto-assets and financial instruments",
                "children": enum_to_children(InstrumentType),
            },
            {
                "title": "Activity Types",
                "description": "Types of regulated activities",
                "children": enum_to_children(ActivityType),
            },
            {
                "title": "Provision Types",
                "description": "Types of legal provisions",
                "children": enum_to_children(ProvisionType),
            },
        ],
    }


def build_corpus_rule_links(rules: list[Rule]) -> dict:
    """Build a tree showing corpus-to-rule mappings."""
    if not rules:
        return {"title": "Corpus-Rule Links", "children": []}

    legal_docs_metadata: dict[str, dict] = {}
    try:
        from src.rag.corpus_loader import load_all_legal_documents

        for doc in load_all_legal_documents():
            legal_docs_metadata[doc.document_id] = {
                "document_title": doc.title,
                "citation": doc.citation,
                "jurisdiction": doc.jurisdiction,
                "source_url": doc.source_url,
            }
    except Exception:
        pass

    corpus_map: dict[str, dict[str, list[Any]]] = defaultdict(lambda: defaultdict(list))

    for rule in rules:
        if rule.source:
            doc_id = rule.source.document_id
            article = rule.source.article or "General"
            corpus_map[doc_id][article].append(rule)
        else:
            corpus_map["unlinked"]["No Source"].append(rule)

    doc_children = []
    for doc_id, articles in sorted(corpus_map.items()):
        article_children = []
        for article, article_rules in sorted(articles.items()):
            rule_nodes = [
                {
                    "title": r.rule_id,
                    "description": r.description or "",
                    "tags": r.tags,
                }
                for r in article_rules
            ]
            article_children.append(
                {
                    "title": f"Art. {article}" if article not in ("General", "No Source") else article,
                    "count": len(article_rules),
                    "children": rule_nodes,
                }
            )

        doc_meta = legal_docs_metadata.get(doc_id, {})
        doc_node: dict[str, Any] = {
            "title": doc_id,
            "articles": len(articles),
            "rules": sum(len(ar) for ar in articles.values()),
            "children": article_children,
        }
        if doc_meta:
            doc_node["document_title"] = doc_meta.get("document_title")
            doc_node["citation"] = doc_meta.get("citation")
            doc_node["jurisdiction"] = doc_meta.get("jurisdiction")
            doc_node["source_url"] = doc_meta.get("source_url")

        doc_children.append(doc_node)

    return {
        "title": "Corpus-Rule Links",
        "documents": len(corpus_map),
        "total_rules": len(rules),
        "children": doc_children,
    }


def build_legal_corpus_coverage(rules: list[Rule]) -> dict:
    """Build a tree showing legal corpus coverage status."""
    legal_docs = []
    try:
        from src.rag.corpus_loader import load_all_legal_documents

        legal_docs = list(load_all_legal_documents())
    except Exception:
        pass

    if not legal_docs:
        return {
            "title": "Legal Corpus Coverage",
            "children": [],
            "message": "No legal corpus available",
        }

    rule_coverage: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for rule in rules:
        if rule.source and rule.source.document_id:
            doc_id = rule.source.document_id
            article = rule.source.article or "General"
            match = re.search(r"(\d+)", str(article))
            if match:
                article = match.group(1)
            rule_coverage[doc_id][article].append(rule.rule_id)

    doc_children = []
    total_covered = 0
    total_gaps = 0

    for doc in legal_docs:
        doc_articles = _extract_articles_from_text(doc.text)
        doc_coverage = rule_coverage.get(doc.document_id, {})

        article_children = []
        covered_count = 0

        for article_num in sorted(doc_articles, key=lambda x: int(x) if x.isdigit() else 0):
            rules_for_article = doc_coverage.get(article_num, [])
            has_rules = len(rules_for_article) > 0

            if has_rules:
                covered_count += 1
                total_covered += 1
                status = "covered"
            else:
                total_gaps += 1
                status = "gap"

            article_children.append(
                {
                    "title": f"Art. {article_num}",
                    "article": article_num,
                    "has_rules": has_rules,
                    "rule_count": len(rules_for_article),
                    "rules": rules_for_article,
                    "status": status,
                }
            )

        total_articles = len(doc_articles)
        coverage_pct = (covered_count / total_articles * 100) if total_articles > 0 else 0

        doc_children.append(
            {
                "title": doc.title or doc.document_id,
                "document_id": doc.document_id,
                "jurisdiction": doc.jurisdiction,
                "citation": doc.citation,
                "source_url": doc.source_url,
                "coverage": round(coverage_pct, 1),
                "covered_articles": covered_count,
                "total_articles": total_articles,
                "gap_articles": total_articles - covered_count,
                "children": article_children,
            }
        )

    return {
        "title": "Legal Corpus Coverage",
        "documents": len(legal_docs),
        "total_covered": total_covered,
        "total_gaps": total_gaps,
        "children": doc_children,
    }


def build_decision_tree_structure(node: Any) -> dict | None:
    """Build a tree structure from a rule's decision tree."""
    if node is None:
        return None

    from src.rules.service import DecisionBranch, DecisionLeaf, DecisionNode

    if isinstance(node, DecisionLeaf) or (hasattr(node, "result") and not hasattr(node, "node_id")):
        result: dict[str, Any] = {
            "title": f"Result: {node.result}",
            "type": "leaf",
            "result": node.result,
        }
        if hasattr(node, "notes") and node.notes:
            result["notes"] = node.notes
        if hasattr(node, "obligations") and node.obligations:
            result["obligations"] = [
                {"id": o.id, "description": getattr(o, "description", None)} for o in node.obligations
            ]
        return result

    if isinstance(node, (DecisionBranch, DecisionNode)) or hasattr(node, "node_id"):
        condition_str = ""
        if hasattr(node, "condition") and node.condition:
            condition_str = f"{node.condition.field} {node.condition.operator} {node.condition.value}"

        children = []
        if hasattr(node, "true_branch") and node.true_branch:
            true_child = build_decision_tree_structure(node.true_branch)
            if true_child:
                true_child["branch"] = "true"
                children.append(true_child)

        if hasattr(node, "false_branch") and node.false_branch:
            false_child = build_decision_tree_structure(node.false_branch)
            if false_child:
                false_child["branch"] = "false"
                children.append(false_child)

        return {
            "title": node.node_id,
            "type": "branch",
            "condition": condition_str,
            "children": children,
        }

    return None


def _extract_articles_from_text(text: str) -> list[str]:
    """Extract article numbers from legal document text."""
    articles = set()

    for match in re.finditer(r"Article\s+(\d+)", text, re.IGNORECASE):
        articles.add(match.group(1))

    for match in re.finditer(r"Section\s+(\d+)", text, re.IGNORECASE):
        articles.add(match.group(1))

    return list(articles)


# ============================================================================
# HTML Rendering Utilities
# ============================================================================

SUPERTREE_AVAILABLE = True


def _escape(text: Any) -> str:
    """Escape HTML entities in text."""
    return html.escape(str(text)) if text is not None else ""


def _render_tree_node(node: dict, depth: int = 0) -> str:
    """Recursively render a tree node as HTML."""
    title = _escape(node.get("title", "Node"))
    children = node.get("children", [])

    metadata = []
    for key, value in node.items():
        if key not in ("title", "children"):
            if isinstance(value, (str, int, float, bool)):
                metadata.append(f'<span class="tree-meta"><strong>{_escape(key)}:</strong> {_escape(value)}</span>')
            elif isinstance(value, list) and all(isinstance(v, (str, int)) for v in value):
                metadata.append(
                    f'<span class="tree-meta"><strong>{_escape(key)}:</strong> {_escape(", ".join(map(str, value)))}</span>'
                )

    meta_html = " ".join(metadata) if metadata else ""

    if children:
        children_html = "\n".join(_render_tree_node(child, depth + 1) for child in children)
        return f"""
        <details class="tree-node" {"open" if depth < 1 else ""}>
            <summary class="tree-branch">
                <span class="tree-icon">▶</span>
                <span class="tree-title">{title}</span>
                {meta_html}
            </summary>
            <div class="tree-children">
                {children_html}
            </div>
        </details>
        """
    else:
        return f"""
        <div class="tree-leaf">
            <span class="tree-icon">•</span>
            <span class="tree-title">{title}</span>
            {meta_html}
        </div>
        """


def _render_tree_html(tree_data: dict, chart_title: str) -> str:
    """Render a complete tree as interactive HTML."""
    tree_content = _render_tree_node(tree_data)

    return f"""
    <div class="tree-container">
        <style>
            .tree-container {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 14px; line-height: 1.5; padding: 16px; background: #fafafa; border-radius: 8px; max-height: 600px; overflow: auto; }}
            .tree-header {{ font-size: 18px; font-weight: 600; margin-bottom: 16px; padding-bottom: 8px; border-bottom: 2px solid #e0e0e0; color: #333; }}
            .tree-node {{ margin: 4px 0; }}
            .tree-branch {{ cursor: pointer; padding: 6px 8px; border-radius: 4px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}
            .tree-branch:hover {{ background: #e8f4fc; }}
            .tree-leaf {{ padding: 6px 8px 6px 24px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}
            .tree-children {{ margin-left: 20px; padding-left: 12px; border-left: 2px solid #ddd; }}
            .tree-icon {{ color: #666; font-size: 10px; width: 12px; transition: transform 0.2s; }}
            details[open] > summary .tree-icon {{ transform: rotate(90deg); }}
            .tree-title {{ font-weight: 500; color: #1a73e8; }}
            .tree-leaf .tree-title {{ color: #333; font-weight: 400; }}
            .tree-meta {{ font-size: 12px; color: #666; background: #e8e8e8; padding: 2px 6px; border-radius: 3px; margin-left: 4px; }}
            details > summary {{ list-style: none; }}
            details > summary::-webkit-details-marker {{ display: none; }}
        </style>
        <div class="tree-header">{_escape(chart_title)}</div>
        {tree_content}
    </div>
    """


def render_rulebook_outline_html(tree_data: dict) -> str:
    """Render the rulebook outline tree as HTML."""
    try:
        return _render_tree_html(tree_data, tree_data.get("title", "Rulebook Outline"))
    except Exception as e:
        return f'<div style="color: red; padding: 20px;">Error rendering chart: {_escape(str(e))}</div>'


def render_decision_trace_html(tree_data: dict) -> str:
    """Render the decision trace tree as HTML."""
    try:
        return _render_tree_html(tree_data, tree_data.get("title", "Decision Trace"))
    except Exception as e:
        return f'<div style="color: red; padding: 20px;">Error rendering chart: {_escape(str(e))}</div>'


def render_ontology_tree_html(tree_data: dict) -> str:
    """Render the ontology browser tree as HTML."""
    try:
        return _render_tree_html(tree_data, tree_data.get("title", "Regulatory Ontology"))
    except Exception as e:
        return f'<div style="color: red; padding: 20px;">Error rendering chart: {_escape(str(e))}</div>'


def render_corpus_links_html(tree_data: dict) -> str:
    """Render the corpus-to-rule links tree as HTML."""
    try:
        return _render_tree_html(tree_data, tree_data.get("title", "Corpus-Rule Links"))
    except Exception as e:
        return f'<div style="color: red; padding: 20px;">Error rendering chart: {_escape(str(e))}</div>'


def is_supertree_available() -> bool:
    """Check if tree visualization is available."""
    return SUPERTREE_AVAILABLE
