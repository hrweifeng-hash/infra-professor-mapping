from abc import ABC, abstractmethod

from models.professor_profile import ProfessorProfile
from .professor_identity import ProfessorIdentity


class IdentityResolver(ABC):
    """Interface for resolving identity metadata from ProfessorProfile."""

    @abstractmethod
    def resolve(
        self,
        professor: ProfessorProfile,
    ) -> ProfessorIdentity:
        raise NotImplementedError
