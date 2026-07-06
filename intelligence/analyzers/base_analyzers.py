from abc import ABC, abstractmethod


class BaseAnalyzer(ABC):
    """
    Base class for all Intelligence analyzers.
    """

    @abstractmethod
    def analyze(self, professor):
        """
        Analyze one professor.

        Returns:
            ProfessorProfile
        """
        pass