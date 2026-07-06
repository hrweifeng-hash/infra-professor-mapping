from .professor_identity import ProfessorIdentity


class CountryResolver:
    """Resolve country information for a ProfessorIdentity."""

    def resolve(self, identity: ProfessorIdentity) -> ProfessorIdentity:
        return identity
