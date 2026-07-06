import unittest

from models.author import Author
from models.author_profile import AuthorProfile
from models.professor_intelligence import ProfessorIntelligence
from models.professor_profile import ProfessorProfile
from validation.professor_identification import ProfessorRole, classify_professor_role
from validation.pr11_validation_report import PR11ValidationReport


def _us_faculty(name: str = "Faculty Member") -> ProfessorProfile:
    return ProfessorProfile(
        author_profile=AuthorProfile(author=Author(pid=None, name=name)),
        intelligence=ProfessorIntelligence(publication_count=12),
        university="Stanford University",
        is_us=True,
        affiliation_confidence=0.9,
        homepage="https://cs.stanford.edu/~faculty/",
    )


def _industry(name: str = "Industry Researcher") -> ProfessorProfile:
    return ProfessorProfile(
        author_profile=AuthorProfile(author=Author(pid=None, name=name)),
        intelligence=ProfessorIntelligence(publication_count=15),
        affiliation="Google Research, Mountain View, CA, USA",
        homepage="https://research.google/people/example",
    )


class TestProfessorIdentification(unittest.TestCase):
    def test_us_university_classified_as_faculty(self):
        result = classify_professor_role(_us_faculty())
        self.assertEqual(result.role, ProfessorRole.FACULTY)

    def test_google_research_classified_as_industry(self):
        result = classify_professor_role(_industry())
        self.assertEqual(result.role, ProfessorRole.INDUSTRY)


class TestPR11ValidationReport(unittest.TestCase):
    def test_report_compare_legacy_vs_new_top100(self):
        infra = _us_faculty("Infra Lead")
        infra.intelligence.overall_score = 95
        infra.intelligence.legacy_overall_score = 70
        infra.intelligence.infrastructure_affinity = 0.9
        infra.intelligence.venue_distribution = {"OSDI": 5, "NSDI": 3}
        infra.intelligence.primary_infra_venues = ["OSDI", "NSDI"]

        ml = _us_faculty("ML Lead")
        ml.intelligence.overall_score = 60
        ml.intelligence.legacy_overall_score = 95
        ml.intelligence.infrastructure_affinity = 0.1
        ml.intelligence.venue_distribution = {"NeurIPS": 10}
        ml.intelligence.primary_infra_venues = []

        ranked = [infra, ml]
        us_top100 = [infra]

        report = PR11ValidationReport.generate(
            ranked_professors=ranked,
            us_top100=us_top100,
        )

        self.assertIn("ML Lead", report["top100_comparison"]["removed"])
        self.assertIn("Infra Lead", report["top100_comparison"]["new_names"])
        self.assertIn("professor_identification_priority", report["professor_role_estimates"])


if __name__ == "__main__":
    unittest.main()
