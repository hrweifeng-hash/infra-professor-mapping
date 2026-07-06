from dataclasses import dataclass


@dataclass
class ProfessorIdentity:
    name: str
    dblp_pid: str
    university: str | None = None
    university_raw: str | None = None
    country: str | None = None
    homepage: str | None = None
    faculty_page: str | None = None
    department: str | None = None
    lab: str | None = None
    scholar_url: str | None = None
    orcid: str | None = None
    email: str | None = None
    confidence: float | None = None
