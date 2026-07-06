from dataclasses import dataclass, field
from typing import List

from models.paper import Paper


@dataclass
class Proceedings:
    """
    One conference proceedings.
    """

    conference: str

    year: int

    title: str

    papers: List[Paper] = field(default_factory=list)