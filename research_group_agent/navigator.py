"""ResearchGroupNavigator — orchestration layer for group page discovery."""

from __future__ import annotations

from homepage_agent.models import FetchStatus, HomepageGraph, NodeCategory

from research_group_agent.models import (
    GroupPageCandidate,
    GroupPageSelection,
    MultiPageSelection,
    ResearchGroupNavigationDecision,
)
from research_group_agent.navigation_prompt_builder import NavigationPromptBuilder
from research_group_agent.providers.navigator_base import ResearchGroupNavigatorProvider

_CANDIDATE_NODE_TYPES: tuple[NodeCategory, ...] = (
    NodeCategory.LAB_PAGE,
    NodeCategory.RESEARCH_GROUP_PAGE,
    NodeCategory.PEOPLE_PAGE,
)

_MIN_SELECTION_SCORE = 0.35

# Human-readable labels for the navigation path
_NODE_TYPE_LABELS: dict[str, str] = {
    NodeCategory.LAB_PAGE.value: "Lab Page",
    NodeCategory.RESEARCH_GROUP_PAGE.value: "Research Group Page",
    NodeCategory.PEOPLE_PAGE.value: "Group Members Page",
    NodeCategory.HOMEPAGE.value: "Personal Homepage",
    NodeCategory.PUBLICATIONS_PAGE.value: "Publications Page",
    "university_faculty": "University Faculty Profile",
    "department_profile": "Department Profile",
}


class ResearchGroupNavigator:
    """
    Decide which HomepageGraph nodes represent a research group page.

    Responsibilities:
    - Collect graph candidates.
    - Build a structured prompt via NavigationPromptBuilder.
    - Delegate classification to the provider.
    - Validate and sort returned decisions.
    - Construct navigation_path from graph metadata.
    - Select the best GroupPageSelection above threshold.

    The provider performs only reasoning; the navigator is the
    orchestration layer that any future provider is plugged into.
    """

    def __init__(
        self,
        provider: ResearchGroupNavigatorProvider,
        prompt_builder: NavigationPromptBuilder | None = None,
    ):
        self.provider = provider
        self._prompt_builder = prompt_builder or NavigationPromptBuilder()

    @property
    def provider_name(self) -> str:
        return self.provider.provider_name

    def navigate(
        self,
        professor_name: str,
        homepage_graph: HomepageGraph,
    ) -> list[ResearchGroupNavigationDecision]:
        """
        Return a ranked list of navigation decisions for the given graph.

        Decisions include evidence, NavigationScore breakdown, and — after
        select() is called — navigation_path.
        """
        if homepage_graph.fetch_status != FetchStatus.SUCCESS:
            return []

        candidates = self._collect_candidates(homepage_graph)
        if not candidates:
            return []

        canonical = homepage_graph.canonical_homepage or homepage_graph.effective_homepage
        prompt = self._prompt_builder.build(
            professor_name=professor_name,
            canonical_homepage=canonical,
            candidates=candidates,
            homepage_graph=homepage_graph,
        )
        decisions = self.provider.classify_candidates(
            prompt=prompt,
            professor_name=professor_name,
            canonical_homepage=canonical,
            candidates=candidates,
            homepage_graph=homepage_graph,
        )
        return sorted(decisions, key=lambda d: d.confidence, reverse=True)

    def select(
        self,
        decisions: list[ResearchGroupNavigationDecision],
        homepage_graph: HomepageGraph | None = None,
    ) -> GroupPageSelection | None:
        """
        Backward-compatible single-selection wrapper over select_top_candidates().

        Returns the highest-confidence GroupPageSelection above threshold,
        or None when no candidate meets the threshold.
        """
        multi = self.select_top_candidates(
            decisions, homepage_graph=homepage_graph, max_candidates=1
        )
        if not multi.selected_pages:
            return None
        return multi.selected_pages[0]

    def select_top_candidates(
        self,
        decisions: list[ResearchGroupNavigationDecision],
        homepage_graph: HomepageGraph | None = None,
        max_candidates: int = 3,
        min_confidence: float = _MIN_SELECTION_SCORE,
    ) -> MultiPageSelection:
        """
        Return up to *max_candidates* GroupPageSelections above *min_confidence*,
        sorted by confidence descending.

        Guarantees:
          - Sorted by confidence (highest first).
          - No duplicate URLs.
          - Configurable threshold and maximum count.
        """
        eligible = [d for d in decisions if d.confidence >= min_confidence]
        seen_urls: set[str] = set()
        selected: list[GroupPageSelection] = []

        for decision in eligible:
            if len(selected) >= max_candidates:
                break
            url = decision.candidate_url
            if url in seen_urls:
                continue
            seen_urls.add(url)

            navigation_path = (
                self._build_navigation_path(homepage_graph, url)
                if homepage_graph is not None
                else list(decision.navigation_path)
            )
            selected.append(
                GroupPageSelection(
                    url=url,
                    source_node_type=decision.candidate_type,
                    confidence=round(decision.confidence, 3),
                    reason=decision.reason,
                    navigation_path=navigation_path,
                    evidence=list(decision.evidence),
                    navigation_score=decision.navigation_score,
                    navigation_provider=self.provider_name,
                )
            )

        reason = (
            f"Selected {len(selected)} of {len(eligible)} eligible candidates "
            f"(threshold={min_confidence}, max={max_candidates})"
        )
        return MultiPageSelection(
            selected_pages=selected,
            selection_strategy="top_candidates",
            selection_reason=reason,
        )

    def navigate_and_select(
        self,
        professor_name: str,
        homepage_graph: HomepageGraph,
    ) -> GroupPageSelection | None:
        """Convenience method: navigate + select the single best page."""
        decisions = self.navigate(professor_name, homepage_graph)
        return self.select(decisions, homepage_graph)

    def navigate_and_select_top(
        self,
        professor_name: str,
        homepage_graph: HomepageGraph,
        max_candidates: int = 3,
        min_confidence: float = _MIN_SELECTION_SCORE,
    ) -> MultiPageSelection:
        """Convenience method: navigate + select top N candidate pages."""
        decisions = self.navigate(professor_name, homepage_graph)
        return self.select_top_candidates(
            decisions,
            homepage_graph=homepage_graph,
            max_candidates=max_candidates,
            min_confidence=min_confidence,
        )

    def all_decisions(
        self,
        professor_name: str,
        homepage_graph: HomepageGraph,
    ) -> list[ResearchGroupNavigationDecision]:
        """
        Return all decisions including rejected ones for debug purposes.

        Attaches navigation_path to the top decision.
        """
        decisions = self.navigate(professor_name, homepage_graph)
        if decisions and homepage_graph:
            decisions[0].navigation_path = self._build_navigation_path(
                homepage_graph, decisions[0].candidate_url
            )
        return decisions

    # ──────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _collect_candidates(homepage_graph: HomepageGraph) -> list[GroupPageCandidate]:
        candidates: list[GroupPageCandidate] = []
        for node_type in _CANDIDATE_NODE_TYPES:
            node = homepage_graph.get_node(node_type)
            if node is None:
                continue
            candidates.append(
                GroupPageCandidate(
                    url=node.url,
                    node_type=node.node_type,
                    anchor_text=node.anchor_text,
                    title=node.title,
                    graph_confidence=node.confidence_value,
                )
            )
        return candidates

    @staticmethod
    def _build_navigation_path(
        homepage_graph: HomepageGraph,
        selected_url: str,
    ) -> list[str]:
        path: list[str] = []
        original = homepage_graph.original_homepage
        canonical = (
            homepage_graph.canonical_homepage or homepage_graph.effective_homepage
        )

        if original and canonical:
            if original.rstrip("/") != canonical.rstrip("/"):
                path.append(original)
                path.append(canonical)
            else:
                path.append(canonical)
        elif canonical:
            path.append(canonical)
        elif homepage_graph.homepage_url:
            path.append(homepage_graph.homepage_url)

        if selected_url and (not path or selected_url.rstrip("/") != path[-1].rstrip("/")):
            path.append(selected_url)

        return path
