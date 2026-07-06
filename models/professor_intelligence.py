from dataclasses import dataclass, field


@dataclass
class ProfessorIntelligence:
    """
    Intelligence generated from publication analysis.

    This object is the single source of truth for all analyzed
    publication, venue, research, and ranking data.
    No crawler or parser state belongs here.
    """

    # ==================================================
    # Publication Statistics
    # ==================================================

    publication_count: int = 0

    conference_distribution: dict[str, int] = field(
        default_factory=dict
    )

    venue_distribution: dict[str, int] = field(
        default_factory=dict
    )

    yearly_publications: dict[int, int] = field(
        default_factory=dict
    )

    first_publication_year: int | None = None

    latest_publication_year: int | None = None

    active_years: int = 0

    # ==================================================
    # Research Intelligence
    # ==================================================

    research_dna: dict[str, float] = field(
        default_factory=dict
    )

    research_areas: list[str] = field(
        default_factory=list
    )

    keywords: list[str] = field(
        default_factory=list
    )

    # ==================================================
    # Ranking
    # ==================================================

    publication_score: float = 0.0

    venue_score: float = 0.0

    research_score: float = 0.0

    productivity_score: float = 0.0

    impact_score: float = 0.0

    # PR11: interpretable infrastructure alignment (0.0 – 1.0)
    infrastructure_affinity: float = 0.0

    infrastructure_affinity_score: float = 0.0

    infra_paper_count: int = 0

    primary_infra_venues: list[str] = field(default_factory=list)

    # Pre-PR11 formula preserved for validation comparisons
    legacy_overall_score: float = 0.0

    hm_scores: dict[str, float] = field(
        default_factory=dict
    )

    overall_score: float = 0.0

    priority: str = "P3"

    confidence: float = 0.0