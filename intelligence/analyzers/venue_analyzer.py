from intelligence.analyzers.base_analyzers import BaseAnalyzer


class VenueAnalyzer(BaseAnalyzer):
    """
    Compute venue quality score.
    """

    def analyze(self, professor):

        author_profile = professor.author_profile
        intelligence = professor.intelligence

        venue_count = len({
            paper.venue
            for paper in author_profile.papers
        })

        intelligence.venue_score = min(
            venue_count,
            10,
        ) * 3

        return professor