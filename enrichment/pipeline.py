from typing import Dict

from models.professor_profile import ProfessorProfile

from enrichment.base_enricher import BaseEnricher


class EnrichmentPipeline:
    """
    Sequential enrichment pipeline.
    """

    def __init__(
        self,
        enrichers: list[BaseEnricher],
    ):

        self.enrichers = enrichers

    def run(
        self,
        professors: Dict[str, ProfessorProfile],
    ) -> Dict[str, ProfessorProfile]:

        for professor in professors.values():

            for enricher in self.enrichers:

                professor = enricher.enrich(
                    professor
                )

        return professors