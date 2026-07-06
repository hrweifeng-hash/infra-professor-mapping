from models.professor_profile import ProfessorProfile

from .identity_resolver import IdentityResolver
from .professor_identity import ProfessorIdentity


class DBLPResolver(IdentityResolver):
    """Resolve identity metadata from existing DBLP-derived ProfessorProfile fields."""

    def __init__(self) -> None:
        self.processed = 0
        self.homepage_found = 0
        self.orcid_found = 0
        self.email_found = 0
        self.affiliation_found = 0
        self.faculty_page_found = 0

    def resolve(self, professor: ProfessorProfile) -> ProfessorIdentity:
        homepage = professor.homepage
        orcid = None
        email = professor.email
        affiliation = professor.affiliation
        faculty_page = self._resolve_faculty_page(professor)

        self.processed += 1
        self.homepage_found += 1 if homepage else 0
        self.orcid_found += 1 if orcid else 0
        self.email_found += 1 if email else 0
        self.affiliation_found += 1 if affiliation else 0
        self.faculty_page_found += 1 if faculty_page else 0

        print(f"Resolved DBLP identity for: {professor.author_profile.author.name}")
        print("Fields found:")
        print(f"- homepage: {'yes' if homepage else 'no'}")
        print(f"- orcid: {'yes' if orcid else 'no'}")
        print(f"- email: {'yes' if email else 'no'}")
        print(f"- affiliation: {'yes' if affiliation else 'no'}")

        return ProfessorIdentity(
            name=professor.author_profile.author.name,
            dblp_pid=professor.author_profile.author.pid or "",
            homepage=homepage,
            orcid=orcid,
            email=email,
            university_raw=affiliation,
            faculty_page=faculty_page,
        )

    def report(self) -> None:
        print()
        print("=" * 40)
        print("DBLP Identity Resolver Summary")
        print("=" * 40)
        print()
        print(f"Processed profiles: {self.processed}")
        print()
        print(f"Homepage found: {self.homepage_found}")
        print(f"ORCID found: {self.orcid_found}")
        print(f"Email found: {self.email_found}")
        print(f"Affiliation found: {self.affiliation_found}")
        print(f"Faculty page found: {self.faculty_page_found}")
        print()
        print("Missing fields remain unfilled (expected):")
        print("- university")
        print("- country")
        print("- department")

    def _resolve_faculty_page(self, professor: ProfessorProfile) -> str | None:
        for paper in professor.author_profile.papers:
            if getattr(paper, "ee_url", None):
                return paper.ee_url

        for paper in professor.author_profile.papers:
            if getattr(paper, "dblp_url", None):
                return paper.dblp_url

        return None
