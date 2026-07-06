import unittest

from models.author import Author
from models.author_profile import AuthorProfile
from models.paper import Paper
from models.professor_intelligence import ProfessorIntelligence
from models.professor_profile import ProfessorProfile
from intelligence.ranking_engine import RankingEngine


def _professor(name: str, venues: dict[str, int], areas: list[str]) -> ProfessorProfile:
    papers = []
    for venue, count in venues.items():
        for i in range(count):
            papers.append(
                Paper(
                    title=f"{venue} paper {i}",
                    authors=[Author(pid=None, name=name)],
                    venue=venue,
                    year=2024,
                )
            )

    profile = AuthorProfile(author=Author(pid=None, name=name), papers=papers)
    intelligence = ProfessorIntelligence(
        publication_count=len(papers),
        venue_distribution=venues,
        research_areas=areas,
    )
    return ProfessorProfile(author_profile=profile, intelligence=intelligence)


class TestRankingEnginePR11(unittest.TestCase):
    def setUp(self):
        self.engine = RankingEngine()

    def test_infra_professor_ranks_above_ml_professor(self):
        infra = _professor(
            "Infra Researcher",
            {"OSDI": 5, "NSDI": 5, "SOSP": 4},
            ["Operating Systems", "Distributed Systems", "Networking"],
        )
        ml = _professor(
            "ML Researcher",
            {"NeurIPS": 8, "ICML": 7, "ICLR": 5},
            ["ML Systems", "Operating Systems", "Networking"],
        )

        ranked = self.engine.rank({"infra": infra, "ml": ml})

        self.assertEqual(ranked[0].author_profile.author.name, "Infra Researcher")
        self.assertGreater(
            infra.intelligence.infrastructure_affinity,
            ml.intelligence.infrastructure_affinity,
        )
        self.assertGreater(
            infra.intelligence.overall_score,
            ml.intelligence.overall_score,
        )

    def test_legacy_score_preserved_for_comparison(self):
        professor = _professor(
            "Mixed",
            {"OSDI": 3, "ICML": 3},
            ["ML Systems", "Operating Systems"],
        )
        self.engine.rank({"mixed": professor})

        self.assertGreater(professor.intelligence.legacy_overall_score, 0)
        self.assertGreater(professor.intelligence.infrastructure_affinity_score, 0)
        self.assertAlmostEqual(
            professor.intelligence.infrastructure_affinity,
            0.5,
        )

    def test_overall_score_components_sum(self):
        professor = _professor(
            "Test",
            {"NSDI": 10},
            ["Networking", "Distributed Systems", "Operating Systems"],
        )
        self.engine.rank({"test": professor})
        intel = professor.intelligence

        total = (
            intel.publication_score
            + intel.venue_score
            + intel.research_score
            + intel.infrastructure_affinity_score
        )
        self.assertAlmostEqual(intel.overall_score, total)


if __name__ == "__main__":
    unittest.main()
