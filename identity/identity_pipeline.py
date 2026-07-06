from models.professor_profile import ProfessorProfile

from .identity_resolver import IdentityResolver
from .professor_identity import ProfessorIdentity


class IdentityPipeline:
    """Build professor identity records from ranked ProfessorProfile objects."""

    def __init__(self, resolver: IdentityResolver, top_n: int = 300) -> None:
        self.resolver = resolver
        self.top_n = top_n

    def run(self, professors: list[ProfessorProfile]) -> list[ProfessorIdentity]:
        top_n = min(self.top_n, len(professors))
        identities: list[ProfessorIdentity] = []

        for index, professor in enumerate(professors[:top_n], start=1):
            identity = self.resolver.resolve(professor)
            identities.append(identity)

            if index % 10 == 0 or index == top_n:
                print(f"[Identity] {index}/{top_n}")

        if hasattr(self.resolver, "report"):
            self.resolver.report()

        return identities
