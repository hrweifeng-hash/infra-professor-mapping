from dataclasses import dataclass


@dataclass
class Author:
    """
    One DBLP author.
    """

    pid: str | None
    name: str