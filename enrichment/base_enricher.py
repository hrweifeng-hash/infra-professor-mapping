from abc import ABC, abstractmethod

from models.professor_profile import ProfessorProfile


class BaseEnricher(ABC):
    """
    Base class for all enrichers.

    Every enricher updates ProfessorProfile in-place and
    returns the same object.
    """

    @abstractmethod
    def enrich(
        self,
        professor: ProfessorProfile,
    ) -> ProfessorProfile:
        """
        Enrich one professor.

        Returns
        -------
        ProfessorProfile
        """
        raise NotImplementedError