from abc import ABC, abstractmethod

from homepage_agent.models import HomepageDocument, Hyperlink, NavigationDecision


class NavigatorProvider(ABC):
    """
    Pluggable backend for homepage link classification.

    Implementations: StubNavigatorProvider (heuristic, no network),
    future OpenAI/Claude/Gemini providers.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...

    @abstractmethod
    def classify_links(
        self,
        prompt: str,
        document: HomepageDocument,
        links: list[Hyperlink],
    ) -> list[NavigationDecision]:
        ...
