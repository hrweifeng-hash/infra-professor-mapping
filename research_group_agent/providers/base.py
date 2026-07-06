from abc import ABC, abstractmethod

from research_group_agent.models import (
    ExtractedMember,
    IdentityResolutionResult,
    MemberExtractionResult,
)
from research_group_agent.parser import ParsedMemberPage


class ResearchGroupProvider(ABC):
    """
    Pluggable backend for member extraction and identity resolution.

    Implementations: StubResearchGroupProvider (heuristic, no network),
    future OpenAI/Claude/Gemini providers.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...

    @abstractmethod
    def extract_members(
        self,
        prompt: str,
        parsed: ParsedMemberPage,
        professor_name: str,
    ) -> MemberExtractionResult:
        ...

    @abstractmethod
    def resolve_identities(
        self,
        prompt: str,
        member: ExtractedMember,
        page_links: list,
        professor_name: str,
    ) -> IdentityResolutionResult:
        ...
