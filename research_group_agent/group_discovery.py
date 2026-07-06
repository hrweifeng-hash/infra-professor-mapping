"""Select the best research group page from a HomepageGraph."""

from __future__ import annotations

from homepage_agent.models import FetchStatus, GraphNode, HomepageGraph

from research_group_agent.models import GroupPageSelection
from research_group_agent.navigator import ResearchGroupNavigator
from research_group_agent.providers.navigator_stub import StubResearchGroupNavigatorProvider


class GroupPageDiscoverer:
    """
    Backward-compatible facade over ResearchGroupNavigator.

    Prefer injecting ResearchGroupNavigator directly in new code.
    """

    def __init__(self, navigator: ResearchGroupNavigator | None = None):
        self.navigator = navigator or ResearchGroupNavigator(
            provider=StubResearchGroupNavigatorProvider()
        )

    def select(self, homepage_graph: HomepageGraph) -> GroupPageSelection | None:
        if homepage_graph.fetch_status != FetchStatus.SUCCESS:
            return None

        decisions = self.navigator.navigate(
            professor_name=homepage_graph.professor_name,
            homepage_graph=homepage_graph,
        )
        return self.navigator.select(decisions, homepage_graph)

    def score_node(self, node: GraphNode) -> tuple[float, str]:
        """Public scoring for tests and future providers."""
        return StubResearchGroupNavigatorProvider.score_node(node)
