import unittest

from models.author import Author
from models.author_profile import AuthorProfile
from models.paper import Paper
from models.professor_intelligence import ProfessorIntelligence
from models.professor_profile import ProfessorProfile
from summaries.pipeline import ResearchSummaryPipeline
from summaries.providers.stub import StubLLMProvider
from summaries.prompt_builder import build_research_summary_prompt


def _professor() -> ProfessorProfile:
    papers = [
        Paper(
            title="Disaggregating the Machine Learning Accelerator",
            authors=[Author(pid=None, name="Ada Lovelace")],
            venue="OSDI",
            year=2024,
        ),
        Paper(
            title="Fast RPC for Edge Systems",
            authors=[Author(pid=None, name="Ada Lovelace")],
            venue="NSDI",
            year=2023,
        ),
    ]
    profile = AuthorProfile(author=Author(pid=None, name="Ada Lovelace"), papers=papers)
    intelligence = ProfessorIntelligence(
        publication_count=2,
        venue_distribution={"OSDI": 1, "NSDI": 1},
        research_areas=[
            "Distributed Systems",
            "Operating Systems",
            "ML Systems",
        ],
        infrastructure_affinity=1.0,
        primary_infra_venues=["OSDI", "NSDI"],
    )
    return ProfessorProfile(
        author_profile=profile,
        intelligence=intelligence,
        university="Example University",
        is_us=True,
    )


class TestResearchSummaryPipeline(unittest.TestCase):
    def test_prompt_contains_recruiter_context(self):
        professor = _professor()
        prompt = build_research_summary_prompt(professor)

        self.assertIn("Ada Lovelace", prompt)
        self.assertIn("Example University", prompt)
        self.assertIn("OSDI", prompt)
        self.assertIn("One-sentence Research Summary", prompt)

    def test_stub_provider_generates_summary(self):
        professor = _professor()
        pipeline = ResearchSummaryPipeline(provider=StubLLMProvider())
        summary = pipeline.generate(professor)

        self.assertTrue(summary.one_sentence_summary)
        self.assertEqual(summary.primary_research_area, "Distributed Systems")
        self.assertGreaterEqual(len(summary.research_tags), 3)
        self.assertEqual(summary.provider, "stub")

    def test_generate_many_attaches_to_professor(self):
        professor = _professor()
        pipeline = ResearchSummaryPipeline(provider=StubLLMProvider())
        pipeline.generate_many([professor])

        self.assertIsNotNone(professor.research_summary)
        self.assertEqual(
            professor.research_summary.primary_research_area,
            "Distributed Systems",
        )


if __name__ == "__main__":
    unittest.main()
