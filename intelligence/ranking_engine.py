from models.professor_profile import ProfessorProfile
from intelligence.venue_weights import VENUE_WEIGHTS
from intelligence.infrastructure_affinity import compute_infrastructure_affinity
from utils.observability import stage_start, stage_end


class RankingEngine:
    """
    Rank professors using academic signals.

    PR11 Score (recruiter-facing, infra-aware):
        30% Publication volume
        25% Venue quality
        15% Research breadth
        30% Infrastructure Affinity

    legacy_overall_score preserves the pre-PR11 formula for validation:
        40% Publication + 30% Venue + 30% Research breadth
    """

    PUBLICATION_CAP = 20
    VENUE_RAW_CAP = 30

    def rank(
        self,
        professors: dict[str, ProfessorProfile],
    ) -> list[ProfessorProfile]:

        start = stage_start("RankingEngine:compute")

        ranked = []

        for professor in professors.values():

            intelligence = professor.intelligence

            publication_score = self._publication_score(
                intelligence.publication_count
            )
            venue_score = self._venue_score(intelligence.venue_distribution)
            research_score = self._research_score(intelligence.research_areas)

            affinity_result = compute_infrastructure_affinity(
                intelligence.venue_distribution
            )
            infrastructure_affinity_score = affinity_result.affinity * 30

            intelligence.publication_score = publication_score
            intelligence.venue_score = venue_score
            intelligence.research_score = research_score
            intelligence.infrastructure_affinity = affinity_result.affinity
            intelligence.infrastructure_affinity_score = (
                infrastructure_affinity_score
            )
            intelligence.infra_paper_count = affinity_result.infra_paper_count
            intelligence.primary_infra_venues = list(
                affinity_result.primary_infra_venues
            )

            intelligence.legacy_overall_score = (
                self._legacy_publication_score(intelligence.publication_count)
                + self._legacy_venue_score(intelligence.venue_distribution)
                + self._legacy_research_score(intelligence.research_areas)
            )

            intelligence.overall_score = (
                publication_score
                + venue_score
                + research_score
                + infrastructure_affinity_score
            )

            intelligence.priority = self._priority(intelligence.overall_score)

            ranked.append(professor)

        ranked.sort(
            key=lambda p: p.intelligence.overall_score,
            reverse=True,
        )

        stage_end("RankingEngine:compute", start)

        return ranked

    def _publication_score(self, publication_count: int) -> float:
        return (min(publication_count, self.PUBLICATION_CAP) / self.PUBLICATION_CAP) * 30

    def _legacy_publication_score(self, publication_count: int) -> float:
        return (min(publication_count, self.PUBLICATION_CAP) / self.PUBLICATION_CAP) * 40

    def _venue_score(self, venue_distribution: dict[str, int]) -> float:
        raw = sum(
            VENUE_WEIGHTS.get(venue, 1.0) * count
            for venue, count in venue_distribution.items()
        )
        return min(raw, 25)

    def _legacy_venue_score(self, venue_distribution: dict[str, int]) -> float:
        raw = sum(
            VENUE_WEIGHTS.get(venue, 1.0) * count
            for venue, count in venue_distribution.items()
        )
        return min(raw, 30)

    def _research_score(self, research_areas: list[str]) -> float:
        return (min(len(research_areas), 5) / 5) * 15

    def _legacy_research_score(self, research_areas: list[str]) -> float:
        return (min(len(research_areas), 5) / 5) * 30

    def _priority(self, overall_score: float) -> str:
        if overall_score >= 80:
            return "P0"
        if overall_score >= 60:
            return "P1"
        if overall_score >= 40:
            return "P2"
        return "P3"
