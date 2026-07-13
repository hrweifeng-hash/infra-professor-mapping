"""M5-PR1 — Navigation graph container and builder.

Public API:
  NavigationGraph        – nodes, edges, visited URLs, candidate pages, stats
  NavigationGraphBuilder – construct and mutate navigation graphs
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from research_group_agent.navigation_models import (
    FRAMEWORK_VERSION,
    NavigationEdge,
    NavigationNode,
    NavigationStatistics,
    VisitStatus,
    infer_page_type,
    is_candidate_page,
    normalize_navigation_url,
)


@dataclass
class NavigationGraph:
    """Bounded navigation graph produced by NavigationExplorer."""

    root_url: str
    nodes: dict[str, NavigationNode] = field(default_factory=dict)
    edges: list[NavigationEdge] = field(default_factory=list)
    visited_urls: set[str] = field(default_factory=set)
    candidate_pages: list[NavigationNode] = field(default_factory=list)
    statistics: NavigationStatistics = field(default_factory=NavigationStatistics)
    framework_version: str = FRAMEWORK_VERSION
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def add_node(self, node: NavigationNode) -> bool:
        """Insert a node; return False when the normalized URL already exists."""
        key = node.normalized_url
        if key in self.nodes:
            return False
        self.nodes[key] = node
        return True

    def add_edge(self, edge: NavigationEdge) -> None:
        self.edges.append(edge)

    def mark_visited(self, normalized_url: str) -> None:
        self.visited_urls.add(normalized_url)
        node = self.nodes.get(normalized_url)
        if node is not None and node.visit_status != VisitStatus.SKIPPED:
            node.visit_status = VisitStatus.VISITED

    def mark_skipped(self, normalized_url: str) -> None:
        node = self.nodes.get(normalized_url)
        if node is not None:
            node.visit_status = VisitStatus.SKIPPED

    def register_candidate(self, node: NavigationNode) -> None:
        if node.normalized_url not in {c.normalized_url for c in self.candidate_pages}:
            self.candidate_pages.append(node)
            self.statistics.candidate_pages = len(self.candidate_pages)

    def finalize_statistics(self) -> None:
        stats = self.statistics
        stats.pages_visited = sum(
            1
            for node in self.nodes.values()
            if node.visit_status in (VisitStatus.VISITED, VisitStatus.CANDIDATE)
        )
        stats.pages_skipped = sum(
            1 for node in self.nodes.values() if node.visit_status == VisitStatus.SKIPPED
        )
        stats.maximum_depth = max((node.depth for node in self.nodes.values()), default=0)

        depth_counts: dict[str, int] = {}
        for node in self.nodes.values():
            if node.visit_status in (VisitStatus.VISITED, VisitStatus.CANDIDATE):
                key = str(node.depth)
                depth_counts[key] = depth_counts.get(key, 0) + 1
        stats.depth_distribution = depth_counts

        outgoing: dict[str, int] = {}
        for edge in self.edges:
            parent_key = normalize_navigation_url(edge.from_url)
            outgoing[parent_key] = outgoing.get(parent_key, 0) + 1
        if outgoing:
            stats.average_branching_factor = sum(outgoing.values()) / len(outgoing)
        else:
            stats.average_branching_factor = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "framework_version": self.framework_version,
            "generated_at": self.generated_at,
            "root_url": self.root_url,
            "statistics": self.statistics.to_dict(),
            "visited_urls": sorted(self.visited_urls),
            "candidate_pages": [node.to_dict() for node in self.candidate_pages],
            "nodes": {
                key: node.to_dict()
                for key, node in sorted(self.nodes.items())
            },
            "edges": [edge.to_dict() for edge in self.edges],
        }


class NavigationGraphBuilder:
    """Construct the initial navigation graph and register discovered nodes."""

    def create(self, root_url: str) -> NavigationGraph:
        normalized = normalize_navigation_url(root_url)
        graph = NavigationGraph(root_url=root_url)
        root_node = NavigationNode(
            url=root_url,
            parent_url=None,
            depth=0,
            page_type=infer_page_type(root_url, ""),
            anchor_text="",
            discovered_from="root",
            visit_status=VisitStatus.PENDING,
            normalized_url=normalized,
        )
        graph.add_node(root_node)
        if is_candidate_page(root_url, ""):
            graph.register_candidate(root_node)
        return graph

    def register_discovered(
        self,
        graph: NavigationGraph,
        *,
        url: str,
        parent_url: str,
        depth: int,
        anchor_text: str,
        discovered_from: str,
        edge_type: str,
    ) -> NavigationNode | None:
        """
        Register a newly discovered link.

        Returns the new NavigationNode, or None when the URL was already known
        (loop prevention).
        """
        normalized = normalize_navigation_url(url)
        if normalized in graph.visited_urls or normalized in graph.nodes:
            graph.statistics.loops_prevented += 1
            return None

        page_type = infer_page_type(url, anchor_text)
        node = NavigationNode(
            url=url,
            parent_url=parent_url,
            depth=depth,
            page_type=page_type,
            anchor_text=anchor_text,
            discovered_from=discovered_from,
            visit_status=VisitStatus.PENDING,
            normalized_url=normalized,
        )
        if not graph.add_node(node):
            graph.statistics.loops_prevented += 1
            return None

        graph.add_edge(
            NavigationEdge(
                from_url=parent_url,
                to_url=url,
                edge_type=edge_type,
                anchor_text=anchor_text,
                depth=depth,
            )
        )

        if is_candidate_page(url, anchor_text):
            graph.register_candidate(node)

        return node
