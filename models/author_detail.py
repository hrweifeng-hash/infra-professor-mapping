from dataclasses import dataclass


@dataclass
class AuthorDetail:

    pid: str

    name: str

    homepage: str | None = None

    affiliation: str | None = None

    orcid: str | None = None