from models.professor_profile import ProfessorProfile

from enrichment.base_enricher import BaseEnricher


class DBLPEnricher(BaseEnricher):
    """
    DBLP enrichment.

    Placeholder implementation.

    Future versions will enrich:

    - homepage
    - ORCID
    - aliases
    - external links
    """

    def enrich(
        self,
        professor: ProfessorProfile,
    ) -> ProfessorProfile:

        return professor