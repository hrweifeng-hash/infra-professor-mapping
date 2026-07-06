from collections import Counter

from intelligence.analyzers.base_analyzers import BaseAnalyzer


class StatisticsAnalyzer(BaseAnalyzer):
    """
    Analyze publication timeline.
    """

    def analyze(self, professor):

        author_profile = professor.author_profile
        intelligence = professor.intelligence

        papers = author_profile.papers

        if not papers:
            return professor

        years = []

        counter = Counter()

        for paper in papers:

            if paper.year:

                years.append(paper.year)

                counter[paper.year] += 1

        if years:

            intelligence.first_publication_year = min(years)

            intelligence.latest_publication_year = max(years)

            intelligence.active_years = (
                intelligence.latest_publication_year
                - intelligence.first_publication_year
                + 1
            )

            intelligence.yearly_publications = dict(
                sorted(counter.items())
            )

        return professor