"""
NavigationPromptBuilder — builds structured prompts for ResearchGroupNavigatorProvider.

Optimized for low token usage: the provider receives a structured JSON graph
representation rather than raw HTML, keeping prompts small and deterministic.
"""

from __future__ import annotations

import json

from homepage_agent.models import HomepageGraph

from research_group_agent.models import GroupPageCandidate

_CANDIDATE_PREVIEW_LIMIT = 20
_NODE_PREVIEW_LIMIT = 30


class NavigationPromptBuilder:
    """
    Build structured prompts for research group page navigation.

    The prompt contains a JSON graph snapshot — not webpage text — so any
    provider (heuristic, LLM, or local model) reasons over the same compact
    representation.
    """

    def build(
        self,
        professor_name: str,
        canonical_homepage: str,
        candidates: list[GroupPageCandidate],
        homepage_graph: HomepageGraph,
    ) -> str:
        graph_repr = self.build_graph_repr(
            professor_name=professor_name,
            canonical_homepage=canonical_homepage,
            candidates=candidates,
            homepage_graph=homepage_graph,
        )
        graph_json = json.dumps(graph_repr, ensure_ascii=False, indent=2)

        return (
            "You are a research group navigation agent.\n"
            "Given a professor's homepage graph, select the best page for "
            "discovering current research group members.\n\n"
            "Rules:\n"
            "- Only choose from the candidate_pages listed below.\n"
            "- Prefer lab/students/team pages over department directories.\n"
            "- Reject admissions, faculty listings, and unrelated pages.\n"
            "- Return a ranked list of decisions with confidence 0.0–1.0.\n\n"
            f"Homepage Graph:\n{graph_json}\n\n"
            "For each viable candidate return:\n"
            "  candidate_url, candidate_type, confidence (0–1), reason, "
            "evidence (list), rejected_candidates (list with reason).\n"
            "Rejected candidates should explain why they were not selected."
        )

    @staticmethod
    def build_graph_repr(
        professor_name: str,
        canonical_homepage: str,
        candidates: list[GroupPageCandidate],
        homepage_graph: HomepageGraph,
    ) -> dict:
        """
        Build the structured JSON graph representation sent to the provider.

        Format is intentionally compact — no page HTML, no surrounding text.
        """
        original = homepage_graph.original_homepage or canonical_homepage
        resolution_method = homepage_graph.homepage_resolution_method or "none"

        all_nodes = [
            {
                "url": node.url,
                "node_type": node.node_type,
                "anchor": node.anchor_text or "",
                "title": node.title or "",
                "confidence": round(node.confidence_value, 3),
            }
            for node in homepage_graph.graph_nodes[:_NODE_PREVIEW_LIMIT]
        ]

        candidate_list = [
            {
                "url": candidate.url,
                "node_type": candidate.node_type,
                "anchor": candidate.anchor_text or "",
                "title": candidate.title or "",
                "graph_confidence": round(candidate.graph_confidence, 3),
            }
            for candidate in candidates[:_CANDIDATE_PREVIEW_LIMIT]
        ]

        return {
            "professor": professor_name,
            "homepage": canonical_homepage,
            "original_homepage": original,
            "homepage_resolution": resolution_method,
            "node_count": len(homepage_graph.graph_nodes),
            "candidate_pages": candidate_list,
            "all_nodes_preview": all_nodes,
        }
