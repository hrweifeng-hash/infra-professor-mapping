"""Member extraction — delegates to ResearchGroupProvider."""

from __future__ import annotations

from research_group_agent.models import GroupPageSelection, MemberExtractionResult
from research_group_agent.parser import ParsedMemberPage
from research_group_agent.prompt_builder import build_member_extraction_prompt
from research_group_agent.providers.base import ResearchGroupProvider


class MemberExtractor:
    """Extract research group members from a parsed group page."""

    def __init__(self, provider: ResearchGroupProvider):
        self.provider = provider

    def extract(
        self,
        professor_name: str,
        group_page: GroupPageSelection,
        parsed: ParsedMemberPage,
    ) -> MemberExtractionResult:
        prompt = build_member_extraction_prompt(
            professor_name=professor_name,
            group_page=group_page,
            parsed=parsed,
        )
        result = self.provider.extract_members(
            prompt=prompt,
            parsed=parsed,
            professor_name=professor_name,
        )
        result.page_url = group_page.url
        return result
