from models.research_summary import ResearchSummary
from summaries.prompt_builder import select_recent_papers
from summaries.providers.base import LLMProvider


class StubLLMProvider(LLMProvider):
    """
    Heuristic summary provider — no external API calls.

    Uses publication metadata until a real LLM provider is configured.
    """

    @property
    def provider_name(self) -> str:
        return "stub"

    def generate_summary(self, prompt: str, professor) -> ResearchSummary:
        intelligence = professor.intelligence
        areas = intelligence.research_areas

        primary = areas[0] if areas else "Infrastructure Systems"
        secondary = areas[1] if len(areas) > 1 else "Systems Research"

        recent = select_recent_papers(professor)
        recent_titles = [paper.title for paper in recent[:3]]

        venue_focus = ", ".join(
            venue
            for venue, _ in sorted(
                intelligence.venue_distribution.items(),
                key=lambda item: item[1],
                reverse=True,
            )[:2]
        )

        if recent_titles:
            focus = recent_titles[0]
            if len(focus) > 80:
                focus = focus[:77] + "..."
            one_liner = (
                f"Researches {primary.lower()} with recent work on "
                f"\"{focus}\", publishing primarily at {venue_focus or 'top systems venues'}."
            )
        else:
            one_liner = (
                f"Researches {primary.lower()} with a focus on "
                f"{secondary.lower()} across {intelligence.publication_count} tracked publications."
            )

        tags = list(dict.fromkeys(areas[:5]))
        if intelligence.primary_infra_venues:
            tags.append(intelligence.primary_infra_venues[0])

        tags = tags[:5]
        while len(tags) < 3:
            tags.append("Systems")

        return ResearchSummary(
            one_sentence_summary=one_liner,
            primary_research_area=primary,
            secondary_research_area=secondary,
            research_tags=tags,
            provider=self.provider_name,
            prompt_preview=prompt[:500],
        )
