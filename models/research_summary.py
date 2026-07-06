from dataclasses import dataclass, field


@dataclass
class ResearchSummary:
    """
    Recruiter-facing research summary for a single professor.

    Generated only for the final US Top100 slice (PR11).
    """

    one_sentence_summary: str = ""
    primary_research_area: str = ""
    secondary_research_area: str = ""
    research_tags: list[str] = field(default_factory=list)
    provider: str = ""
    prompt_preview: str = ""
