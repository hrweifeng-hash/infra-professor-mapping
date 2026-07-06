from abc import ABC, abstractmethod

from models.research_summary import ResearchSummary


class LLMProvider(ABC):
    """
    Pluggable LLM backend for research summaries.

    Implementations: StubLLMProvider (heuristic, no network), future OpenAI/Claude.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...

    @abstractmethod
    def generate_summary(self, prompt: str, professor) -> ResearchSummary:
        ...
