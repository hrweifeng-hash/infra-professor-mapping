from dataclasses import dataclass, field
from typing import List, Set

from models.author import Author
from models.paper import Paper


@dataclass
class AuthorProfile:
    """
    Aggregated publication profile of one author.
    """

    author: Author

    papers: List[Paper] = field(default_factory=list)

    conferences: Set[str] = field(default_factory=set)

    active_years: Set[int] = field(default_factory=set)

    @property
    def paper_count(self):

        return len(self.papers)