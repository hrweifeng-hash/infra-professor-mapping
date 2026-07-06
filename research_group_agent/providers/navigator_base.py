from abc import ABC, abstractmethod

from homepage_agent.models import HomepageGraph

from research_group_agent.models import GroupPageCandidate, ResearchGroupNavigationDecision


class ResearchGroupNavigatorProvider(ABC):
    """
    Pluggable backend for research group page navigation decisions.

    Implementations: StubResearchGroupNavigatorProvider (heuristic, no network),
    future OpenAI/Claude/Gemini providers.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...

    @abstractmethod
    def classify_candidates(
        self,
        prompt: str,
        professor_name: str,
        canonical_homepage: str,
        candidates: list[GroupPageCandidate],
        homepage_graph: HomepageGraph,
    ) -> list[ResearchGroupNavigationDecision]:
        ...
