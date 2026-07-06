from models.paper import Paper
from models.professor_profile import ProfessorProfile


RECENT_PAPER_LIMIT = 8


def select_recent_papers(professor: ProfessorProfile) -> list[Paper]:
    papers = professor.author_profile.papers
    return sorted(papers, key=lambda paper: paper.year, reverse=True)[
        :RECENT_PAPER_LIMIT
    ]


def build_research_summary_prompt(
    professor: ProfessorProfile,
    recent_papers: list[Paper] | None = None,
) -> str:
    """
    Build the prompt sent to an LLM provider.

    Separated from provider logic so prompts can be reviewed, versioned, and
    reused across OpenAI / Claude / local models later.
    """
    author = professor.author_profile.author
    intelligence = professor.intelligence
    papers = recent_papers or select_recent_papers(professor)

    paper_lines = []
    for paper in papers:
        paper_lines.append(
            f"- [{paper.year}] {paper.venue}: {paper.title}"
        )

    areas = ", ".join(intelligence.research_areas[:5]) or "N/A"
    venues = ", ".join(
        venue
        for venue, _ in sorted(
            intelligence.venue_distribution.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:5]
    ) or "N/A"

    affiliation = professor.university or professor.affiliation or "Unknown"

    return (
        "You are helping a technical recruiter understand an infrastructure "
        "researcher's work.\n\n"
        f"Professor: {author.name}\n"
        f"Affiliation: {affiliation}\n"
        f"Research areas (from publications): {areas}\n"
        f"Top venues: {venues}\n"
        f"Infrastructure affinity: {intelligence.infrastructure_affinity:.0%}\n"
        f"Publication count (tracked conferences): {intelligence.publication_count}\n\n"
        "Recent papers:\n"
        f"{chr(10).join(paper_lines) if paper_lines else '- (none)'}\n\n"
        "Respond with:\n"
        "1. One-sentence Research Summary (plain English, recruiter-friendly)\n"
        "2. Primary Research Area\n"
        "3. Secondary Research Area\n"
        "4. 3-5 Research Tags (short phrases)\n"
    )
