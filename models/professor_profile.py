from dataclasses import dataclass, field

from models.author_profile import AuthorProfile
from models.professor_intelligence import ProfessorIntelligence
from models.research_summary import ResearchSummary

# Avoid circular import at runtime — only used for type annotation.
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homepage_agent.models import HomepageGraph
    from research_group_agent.models import ResearchGroupGraph


@dataclass
class ProfessorProfile:

    """
    Lightweight wrapper around author profile and intelligence.

    Publication and ranking state is stored in ProfessorIntelligence,
    so ProfessorProfile does not duplicate those values.
    """

    author_profile: AuthorProfile

    affiliation: str | None = None
    homepage: str | None = None
    scholar_url: str | None = None
    email: str | None = None

    intelligence: ProfessorIntelligence = field(
        default_factory=ProfessorIntelligence
    )

    lab: str | None = None

    # ==================================================
    # PR10: US affiliation resolution (AffiliationResolver)
    # ==================================================

    university: str | None = None

    country: str | None = None

    is_us: bool = False

    affiliation_confidence: float = 0.0

    # PR11: populated only for the final US Top100 export slice
    research_summary: ResearchSummary | None = None

    # PR12: homepage navigation graph (Top100 only)
    homepage_graph: "HomepageGraph | None" = None

    # PR13: research group graph (Top N only)
    research_group_graph: "ResearchGroupGraph | None" = None