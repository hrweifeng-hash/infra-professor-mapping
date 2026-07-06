"""Identity resolution — delegates to ResearchGroupProvider."""

from __future__ import annotations

from homepage_agent.models import Hyperlink

from research_group_agent.models import ExtractedMember, IdentityResolutionResult
from research_group_agent.prompt_builder import build_identity_resolution_prompt
from research_group_agent.providers.base import ResearchGroupProvider


class IdentityResolver:
    """Resolve public academic identities for an extracted member."""

    def __init__(self, provider: ResearchGroupProvider):
        self.provider = provider

    def resolve(
        self,
        member: ExtractedMember,
        page_links: list[Hyperlink],
        professor_name: str,
    ) -> IdentityResolutionResult:
        prompt = build_identity_resolution_prompt(
            member=member,
            professor_name=professor_name,
        )
        return self.provider.resolve_identities(
            prompt=prompt,
            member=member,
            page_links=page_links,
            professor_name=professor_name,
        )
