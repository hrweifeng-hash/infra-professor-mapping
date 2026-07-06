from intelligence.analyzers.base_analyzers import BaseAnalyzer

from intelligence.engines.keyword_engine import KeywordEngine
from intelligence.engines.venue_engine import VenueEngine

from intelligence.scorer import EvidenceScorer


class ResearchAreaAnalyzer(BaseAnalyzer):
    """
    Analyze a professor's research areas from publications.
    """

    def __init__(self):

        self.keyword_engine = KeywordEngine()

        self.venue_engine = VenueEngine()

        self.scorer = EvidenceScorer()

    def analyze(self, professor):

        author_profile = professor.author_profile
        intelligence = professor.intelligence

        evidences = []

        for paper in author_profile.papers:

            evidences.extend(

                self.keyword_engine.analyze(paper)

            )

            evidences.extend(

                self.venue_engine.analyze(paper)

            )

        dna = self.scorer.score(evidences)

        professor.intelligence.research_dna = dna

        professor.intelligence.research_areas = [

            category

            for category, score in dna.top(5)

        ]

        professor.intelligence.keywords = sorted({

            evidence.matched_text

            for evidence in evidences

            if evidence.source == "Title"

        })

        return professor