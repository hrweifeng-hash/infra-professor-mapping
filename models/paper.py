from dataclasses import dataclass
from typing import List

from models.author import Author


@dataclass
class Paper:
    """
    One conference paper parsed from DBLP XML.
    """

    title: str

    authors: List[Author]

    venue: str

    year: int

    pages: str | None = None

    dblp_key: str | None = None

    ee_url: str | None = None

    dblp_url: str | None = None