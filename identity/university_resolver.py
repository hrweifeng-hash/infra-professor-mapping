from .professor_identity import ProfessorIdentity


class UniversityResolver:
    """Resolve university information for a ProfessorIdentity."""

    def resolve(self, identity: ProfessorIdentity) -> ProfessorIdentity:
        return identity
