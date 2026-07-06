from models.research_summary import ResearchSummary
from models.professor_profile import ProfessorProfile
from summaries.prompt_builder import select_recent_papers
from summaries.providers.base import LLMProvider


class ResearchSummaryPipeline:
    """
    Generate recruiter-facing research summaries for a bounded professor list.

    Only invoked for the final US Top100 — never the full 79k universe.
    """

    def __init__(self, provider: LLMProvider):
        self.provider = provider

    def generate(self, professor: ProfessorProfile) -> ResearchSummary:
        from summaries.prompt_builder import build_research_summary_prompt

        recent_papers = select_recent_papers(professor)
        prompt = build_research_summary_prompt(professor, recent_papers)
        summary = self.provider.generate_summary(prompt, professor)
        summary.provider = self.provider.provider_name
        summary.prompt_preview = prompt[:500]
        return summary

    def generate_many(
        self,
        professors: list[ProfessorProfile],
    ) -> list[ResearchSummary]:
        summaries = []
        for professor in professors:
            summary = self.generate(professor)
            professor.research_summary = summary
            summaries.append(summary)
        return summaries
