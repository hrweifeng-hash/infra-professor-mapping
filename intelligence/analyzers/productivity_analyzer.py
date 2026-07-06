from intelligence.analyzers.base_analyzers import BaseAnalyzer


class ProductivityAnalyzer(BaseAnalyzer):
    """
    Estimate publication productivity.
    """

    def analyze(self, professor):

        author_profile = professor.author_profile
        intelligence = professor.intelligence

        if intelligence.active_years == 0:

            return professor

        publications_per_year = (

            intelligence.publication_count

            / intelligence.active_years

        )

        intelligence.productivity_score = min(

            publications_per_year,

            5,

        ) * 4

        return professor