from dataclasses import dataclass, field


@dataclass
class PersonRecord:
    """
    One DBLP <www key="homepages/..."> person record.

    Classification (which url is the personal homepage vs. an aggregator
    profile link like ORCID/Google Scholar) happens once in
    WWWRecordParser, not here — this is a plain data holder.
    """

    name: str

    urls: list[str] = field(default_factory=list)

    affiliation_notes: list[str] = field(default_factory=list)

    homepage: str | None = None

    orcid: str | None = None
