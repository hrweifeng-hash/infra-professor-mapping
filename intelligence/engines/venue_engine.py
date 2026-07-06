from intelligence.models.evidence import Evidence
from intelligence.taxonomy import INFRASTRUCTURE_TAXONOMY


class VenueEngine:
    """
    Generate Evidence objects from publication venues.
    """

    def __init__(self, taxonomy=None):

        self.taxonomy = taxonomy or INFRASTRUCTURE_TAXONOMY

    def analyze(self, paper):

        evidences = []

        venue = ""

        if getattr(paper, "conference", None):
            venue = paper.conference.name.upper()
        elif getattr(paper, "venue", None):
            venue = str(paper.venue).upper()

        for category in self.taxonomy:

            for target_venue in category.venues:

                if target_venue.upper() == venue:

                    evidences.append(
                        Evidence(
                            paper=paper,
                            source="Venue",
                            matched_text=target_venue,
                            category=category.name,
                            weight=2.0,
                            reason="Venue Match",
                        )
                    )

        return evidences