from intelligence.models.evidence import Evidence
from intelligence.taxonomy import INFRASTRUCTURE_TAXONOMY


class KeywordEngine:
    """
    Generate Evidence objects from paper titles.
    """

    def __init__(self, taxonomy=None):

        self.taxonomy = taxonomy or INFRASTRUCTURE_TAXONOMY

    def analyze(self, paper):

        evidences = []

        title = paper.title.lower()

        for category in self.taxonomy:

            for keyword in category.keywords:

                if keyword.lower() in title:

                    evidences.append(
                        Evidence(
                            paper=paper,
                            source="Title",
                            matched_text=keyword,
                            category=category.name,
                            weight=3.0,
                            reason="Keyword Match",
                        )
                    )

        return evidences