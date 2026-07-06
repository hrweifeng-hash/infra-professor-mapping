from intelligence.models.evidence import Evidence
from intelligence.models.research_dna import ResearchDNA


class EvidenceScorer:
    """
    Merge all evidences into a ResearchDNA.
    """

    def score(
        self,
        evidences: list[Evidence],
    ) -> ResearchDNA:

        dna = ResearchDNA()

        for evidence in evidences:

            dna.add_score(
                evidence.category,
                evidence.weight,
            )

        dna.normalize()

        return dna