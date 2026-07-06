"""Navigator — intelligence layer that produces NavigationDecision objects."""

from __future__ import annotations

from homepage_agent.models import HomepageDocument, NavigationDecision, ParsedPage
from homepage_agent.prompt_builder import build_navigation_prompt
from homepage_agent.providers.base import NavigatorProvider


class Navigator:
    """
    Decide which homepage links are useful navigation targets.

    Returns NavigationDecision objects — graph construction is delegated to
    GraphBuilder so all providers share the same downstream interface.
    """

    def __init__(self, provider: NavigatorProvider):
        self.provider = provider

    def navigate(
        self,
        professor_name: str,
        document: HomepageDocument,
        parsed: ParsedPage,
    ) -> list[NavigationDecision]:
        prompt = build_navigation_prompt(
            professor_name=professor_name,
            document=document,
            parsed=parsed,
        )
        return self.provider.classify_links(
            prompt=prompt,
            document=document,
            links=parsed.links,
        )
