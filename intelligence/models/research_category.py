from dataclasses import dataclass, field


@dataclass
class ResearchCategory:
    """
    Research taxonomy node.
    """

    # e.g. Operating Systems
    name: str

    # e.g. Infrastructure
    parent: str | None = None

    # Keywords describing this area
    keywords: list[str] = field(default_factory=list)

    # Representative conferences
    venues: list[str] = field(default_factory=list)

    # Child categories
    children: list[str] = field(default_factory=list)