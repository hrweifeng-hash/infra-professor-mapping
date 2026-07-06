from collections import Counter

from intelligence.analyzers.base_analyzers import BaseAnalyzer


class PublicationAnalyzer(BaseAnalyzer):
    """
    Analyze publication statistics.
    """

    def analyze(self, professor):

        author_profile = professor.author_profile
        intelligence = professor.intelligence

        papers = author_profile.papers

        intelligence.publication_count = len(papers)

        conference_counter = Counter()
        venue_counter = Counter()

        for paper in papers:

            conference_counter[paper.venue] += 1
            venue_counter[paper.venue] += 1

        intelligence.conference_distribution = dict(
            sorted(
                conference_counter.items(),
                key=lambda x: x[1],
                reverse=True,
            )
        )

        intelligence.venue_distribution = dict(
            sorted(
                venue_counter.items(),
                key=lambda x: x[1],
                reverse=True,
            )
        )

        return professor