"""Data models for the Homepage Intelligence Agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


SCHEMA_VERSION = "1.2"
PIPELINE_VERSION = "PR13.2"


class FetchStatus(str, Enum):
    SUCCESS = "success"
    TIMEOUT = "timeout"
    HTTP_ERROR = "http_error"
    NETWORK_ERROR = "network_error"
    INVALID_URL = "invalid_url"
    EMPTY_RESPONSE = "empty_response"


class NodeCategory(str, Enum):
    """Navigation node types in a professor homepage graph."""

    HOMEPAGE = "homepage"
    PEOPLE_PAGE = "people_page"
    LAB_PAGE = "lab_page"
    RESEARCH_GROUP_PAGE = "research_group_page"
    PROJECTS_PAGE = "projects_page"
    PUBLICATIONS_PAGE = "publications_page"
    SOFTWARE_PAGE = "software_page"
    TEACHING_PAGE = "teaching_page"
    NEWS_PAGE = "news_page"
    CONTACT_PAGE = "contact_page"


# Ordered slots used for backward-compatible dict views and reports.
GRAPH_NODE_SLOTS: tuple[NodeCategory, ...] = (
    NodeCategory.HOMEPAGE,
    NodeCategory.PEOPLE_PAGE,
    NodeCategory.LAB_PAGE,
    NodeCategory.RESEARCH_GROUP_PAGE,
    NodeCategory.PROJECTS_PAGE,
    NodeCategory.PUBLICATIONS_PAGE,
    NodeCategory.SOFTWARE_PAGE,
    NodeCategory.TEACHING_PAGE,
    NodeCategory.NEWS_PAGE,
    NodeCategory.CONTACT_PAGE,
)


@dataclass
class HomepageDocument:
    url: str
    html: str
    title: str
    fetch_status: FetchStatus
    final_url: str | None = None
    status_code: int | None = None
    markdown: str | None = None
    error_message: str | None = None


@dataclass
class Hyperlink:
    anchor_text: str
    href: str
    absolute_url: str
    surrounding_context: str | None = None


@dataclass
class ParsedPage:
    page_title: str
    visible_text: str
    links: list[Hyperlink] = field(default_factory=list)


@dataclass
class ConfidenceScore:
    """
    Decomposed confidence for navigation decisions.

    Public consumers should use final_score; component scores are for debugging
    and future LLM provider attribution.
    """

    keyword_score: float = 0.0
    structure_score: float = 0.0
    provider_score: float = 0.0
    final_score: float = 0.0

    @classmethod
    def from_stub(
        cls,
        keyword_score: float,
        structure_score: float,
    ) -> ConfidenceScore:
        provider_score = keyword_score
        final_score = round(
            min(1.0, (keyword_score * 0.65) + (structure_score * 0.35)),
            3,
        )
        return cls(
            keyword_score=round(keyword_score, 3),
            structure_score=round(structure_score, 3),
            provider_score=round(provider_score, 3),
            final_score=final_score,
        )

    @classmethod
    def certain(cls) -> ConfidenceScore:
        return cls(
            keyword_score=1.0,
            structure_score=1.0,
            provider_score=1.0,
            final_score=1.0,
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "keyword_score": self.keyword_score,
            "structure_score": self.structure_score,
            "provider_score": self.provider_score,
            "final_score": self.final_score,
        }


@dataclass
class NavigationDecision:
    """A single navigation classification produced by the Navigator."""

    candidate_url: str
    candidate_type: NodeCategory
    confidence: ConfidenceScore
    reason: str
    anchor_text: str | None = None
    title: str | None = None

    @property
    def final_confidence(self) -> float:
        return self.confidence.final_score


@dataclass
class GraphNode:
    """
    A node in the homepage navigation graph.

    Canonical storage unit — all navigation targets live in HomepageGraph.graph_nodes.
    """

    node_type: str
    url: str
    confidence: ConfidenceScore
    discovery_method: str
    title: str | None = None
    anchor_text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def confidence_value(self) -> float:
        """Public-facing confidence (backward compatible with pre-PR12.1 float usage)."""
        return self.confidence.final_score

    @property
    def category(self) -> NodeCategory | None:
        try:
            return NodeCategory(self.node_type)
        except ValueError:
            return None

    @property
    def method(self) -> str:
        """Backward-compatible alias for discovery_method."""
        return self.discovery_method

    def to_dict(self, include_score_detail: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "node_type": self.node_type,
            "url": self.url,
            "confidence": round(self.confidence.final_score, 3),
            "discovery_method": self.discovery_method,
        }
        if self.title:
            payload["title"] = self.title
        if self.anchor_text:
            payload["anchor_text"] = self.anchor_text
        if self.metadata:
            payload["metadata"] = self.metadata
        if include_score_detail:
            payload["confidence_detail"] = self.confidence.to_dict()
        return payload

    def to_legacy_dict(self) -> dict[str, Any]:
        """Slot-oriented dict shape preserved for backward-compatible JSON export."""
        payload: dict[str, Any] = {
            "url": self.url,
            "confidence": round(self.confidence.final_score, 3),
            "method": self.discovery_method,
        }
        if self.anchor_text:
            payload["anchor_text"] = self.anchor_text
        return payload


@dataclass
class HomepageGraph:
    """
    Long-lived navigation graph for a professor homepage.

    Canonical node storage is graph_nodes (list). Dict/slot views are computed.
    """

    professor_name: str
    homepage_url: str
    fetch_status: FetchStatus
    graph_nodes: list[GraphNode] = field(default_factory=list)
    provider: str = "stub"
    link_count: int = 0
    errors: list[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    pipeline_version: str = PIPELINE_VERSION
    original_homepage: str | None = None
    canonical_homepage: str | None = None
    homepage_resolution_method: str | None = None
    homepage_resolution_confidence: float = 0.0

    @property
    def effective_homepage(self) -> str:
        return self.canonical_homepage or self.homepage_url

    @property
    def homepage_status(self) -> str:
        return self.fetch_status.value

    @property
    def nodes(self) -> dict[str, GraphNode | None]:
        """Backward-compatible slot view — computed from graph_nodes, not stored."""
        return self.nodes_by_type

    @property
    def nodes_by_type(self) -> dict[str, GraphNode | None]:
        slots = {slot.value: None for slot in GRAPH_NODE_SLOTS}
        for node in self.graph_nodes:
            slots[node.node_type] = node
        return slots

    @property
    def people_page(self) -> GraphNode | None:
        return self.nodes_by_type.get(NodeCategory.PEOPLE_PAGE.value)

    @property
    def lab_page(self) -> GraphNode | None:
        return self.nodes_by_type.get(NodeCategory.LAB_PAGE.value)

    @property
    def projects_page(self) -> GraphNode | None:
        return self.nodes_by_type.get(NodeCategory.PROJECTS_PAGE.value)

    @property
    def publications_page(self) -> GraphNode | None:
        return self.nodes_by_type.get(NodeCategory.PUBLICATIONS_PAGE.value)

    @property
    def software_page(self) -> GraphNode | None:
        return self.nodes_by_type.get(NodeCategory.SOFTWARE_PAGE.value)

    @property
    def teaching_page(self) -> GraphNode | None:
        return self.nodes_by_type.get(NodeCategory.TEACHING_PAGE.value)

    @property
    def news_page(self) -> GraphNode | None:
        return self.nodes_by_type.get(NodeCategory.NEWS_PAGE.value)

    @property
    def contact_page(self) -> GraphNode | None:
        return self.nodes_by_type.get(NodeCategory.CONTACT_PAGE.value)

    def get_node(self, node_type: NodeCategory | str) -> GraphNode | None:
        key = node_type.value if isinstance(node_type, NodeCategory) else node_type
        return self.nodes_by_type.get(key)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "pipeline_version": self.pipeline_version,
            "professor_name": self.professor_name,
            "homepage_url": self.homepage_url,
            "original_homepage": self.original_homepage or self.homepage_url,
            "canonical_homepage": self.canonical_homepage or self.homepage_url,
            "homepage_resolution_method": self.homepage_resolution_method,
            "homepage_resolution_confidence": round(self.homepage_resolution_confidence, 3),
            "homepage_status": self.homepage_status,
            "fetch_status": self.fetch_status.value,
            "provider": self.provider,
            "link_count": self.link_count,
            "errors": self.errors,
            "graph_nodes": [node.to_dict() for node in self.graph_nodes],
            "nodes": {
                slot.value: (
                    self.nodes_by_type[slot.value].to_legacy_dict()
                    if self.nodes_by_type[slot.value]
                    else None
                )
                for slot in GRAPH_NODE_SLOTS
            },
        }

    @classmethod
    def empty_slots(cls) -> dict[str, None]:
        return {slot.value: None for slot in GRAPH_NODE_SLOTS}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HomepageGraph:
        """Reconstruct a HomepageGraph from serialized JSON."""
        graph_nodes: list[GraphNode] = []
        for node_data in data.get("graph_nodes", []):
            detail = node_data.get("confidence_detail", {})
            confidence = ConfidenceScore(
                keyword_score=detail.get("keyword_score", node_data.get("confidence", 0.0)),
                structure_score=detail.get("structure_score", 0.0),
                provider_score=detail.get("provider_score", node_data.get("confidence", 0.0)),
                final_score=node_data.get("confidence", 0.0),
            )
            graph_nodes.append(
                GraphNode(
                    node_type=node_data["node_type"],
                    url=node_data["url"],
                    confidence=confidence,
                    discovery_method=node_data.get("discovery_method", "unknown"),
                    title=node_data.get("title"),
                    anchor_text=node_data.get("anchor_text"),
                    metadata=node_data.get("metadata", {}),
                )
            )

        graph = cls(
            professor_name=data["professor_name"],
            homepage_url=data.get("homepage_url", ""),
            fetch_status=FetchStatus(data.get("fetch_status", FetchStatus.SUCCESS.value)),
            graph_nodes=graph_nodes,
            provider=data.get("provider", "heuristic"),
            link_count=data.get("link_count", 0),
            errors=data.get("errors", []),
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            generated_at=data.get("generated_at", datetime.now(timezone.utc).isoformat()),
            pipeline_version=data.get("pipeline_version", PIPELINE_VERSION),
            original_homepage=data.get("original_homepage"),
            canonical_homepage=data.get("canonical_homepage"),
            homepage_resolution_method=data.get("homepage_resolution_method"),
            homepage_resolution_confidence=data.get("homepage_resolution_confidence", 0.0),
        )
        if graph.original_homepage is None:
            graph.original_homepage = graph.homepage_url
        if graph.canonical_homepage is None:
            graph.canonical_homepage = graph.homepage_url
        return graph
