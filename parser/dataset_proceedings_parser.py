from collections.abc import Iterable

from models.proceedings import Proceedings
from models.paper import Paper


class DatasetProceedingsParser:
    """
    Wrap dataset papers into Proceedings.
    """

    def parse(self, papers: Iterable[Paper]) -> Proceedings | None:

        papers = list(papers)

        if not papers:
            return None

        first = papers[0]

        return Proceedings(
            conference=first.venue,
            year=first.year,
            title=f"{first.venue} {first.year}",
            papers=papers,
        )