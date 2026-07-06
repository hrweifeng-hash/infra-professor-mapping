"""GraphBuilder — constructs HomepageGraph from NavigationDecision objects."""

from __future__ import annotations

from homepage_agent.models import (
    ConfidenceScore,
    FetchStatus,
    GraphNode,
    HomepageDocument,
    HomepageGraph,
    NavigationDecision,
    NodeCategory,
    PIPELINE_VERSION,
    SCHEMA_VERSION,
)


class GraphBuilder:
    """
    Build a HomepageGraph from navigator decisions.

    Separates decision-making (Navigator/Provider) from graph construction so
    Stub, GPT, Claude, and Gemini navigators share the same downstream path.
    """

    def build(
        self,
        professor_name: str,
        homepage_url: str,
        fetch_status: FetchStatus,
        decisions: list[NavigationDecision],
        provider: str,
        document: HomepageDocument | None = None,
        link_count: int = 0,
        errors: list[str] | None = None,
    ) -> HomepageGraph:
        graph_nodes = self._decisions_to_nodes(decisions, provider=provider)

        if document and fetch_status == FetchStatus.SUCCESS:
            homepage_node = self._build_homepage_node(document)
            graph_nodes = self._merge_homepage_node(graph_nodes, homepage_node)

        return HomepageGraph(
            professor_name=professor_name,
            homepage_url=homepage_url,
            fetch_status=fetch_status,
            graph_nodes=graph_nodes,
            provider=provider,
            link_count=link_count,
            errors=list(errors or []),
            schema_version=SCHEMA_VERSION,
            pipeline_version=PIPELINE_VERSION,
            original_homepage=homepage_url,
            canonical_homepage=homepage_url,
        )

    def build_failure(
        self,
        professor_name: str,
        homepage_url: str,
        fetch_status: FetchStatus,
        provider: str,
        errors: list[str] | None = None,
    ) -> HomepageGraph:
        return self.build(
            professor_name=professor_name,
            homepage_url=homepage_url,
            fetch_status=fetch_status,
            decisions=[],
            provider=provider,
            errors=errors,
        )

    @staticmethod
    def _build_homepage_node(document: HomepageDocument) -> GraphNode:
        return GraphNode(
            node_type=NodeCategory.HOMEPAGE.value,
            url=document.final_url or document.url,
            title=document.title or None,
            confidence=ConfidenceScore.certain(),
            discovery_method="fetch",
        )

    @staticmethod
    def _decisions_to_nodes(
        decisions: list[NavigationDecision],
        provider: str,
    ) -> list[GraphNode]:
        nodes: list[GraphNode] = []
        for decision in decisions:
            if decision.candidate_type == NodeCategory.HOMEPAGE:
                continue
            nodes.append(
                GraphNode(
                    node_type=decision.candidate_type.value,
                    url=decision.candidate_url,
                    title=decision.title,
                    confidence=decision.confidence,
                    discovery_method=provider,
                    anchor_text=decision.anchor_text,
                    metadata={"reason": decision.reason},
                )
            )
        return nodes

    @staticmethod
    def _merge_homepage_node(
        nodes: list[GraphNode],
        homepage_node: GraphNode,
    ) -> list[GraphNode]:
        without_homepage = [
            node for node in nodes if node.node_type != NodeCategory.HOMEPAGE.value
        ]
        return [homepage_node, *without_homepage]
