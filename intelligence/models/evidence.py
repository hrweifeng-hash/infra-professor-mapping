from dataclasses import dataclass

from models.paper import Paper


@dataclass
class Evidence:
    """
    One piece of evidence supporting a research category.
    """

    # Which paper generated this evidence
    paper: Paper

    # Title / Venue / Abstract / Citation ...
    source: str

    # Matched keyword or venue name
    matched_text: str

    # Target research category
    category: str

    # Weighted score
    weight: float

    # Human-readable explanation
    reason: str

    def __str__(self):

        return (
            f"[{self.source}] "
            f"{self.category} "
            f"(+{self.weight}) "
            f"{self.reason}"
        )