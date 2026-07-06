from dataclasses import dataclass, field


@dataclass
class ResearchDNA:
    """
    Numerical representation of a professor's research profile.
    """

    scores: dict[str, float] = field(default_factory=dict)

    def add_score(
        self,
        category: str,
        score: float,
    ):

        self.scores[category] = (
            self.scores.get(category, 0.0)
            + score
        )

    def normalize(self):

        if not self.scores:
            return

        maximum = max(self.scores.values())

        if maximum <= 0:
            return

        for category in self.scores:

            self.scores[category] /= maximum

    def top(
        self,
        k: int = 5,
    ):

        return sorted(
            self.scores.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:k]

    def similarity(
        self,
        other: "ResearchDNA",
    ) -> float:
        """
        Placeholder.

        Sprint 3 will implement cosine similarity.
        """
        raise NotImplementedError

    def to_dict(self):

        return dict(self.scores)