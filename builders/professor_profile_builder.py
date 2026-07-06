from typing import Dict

from models.author_profile import AuthorProfile
from models.professor_profile import ProfessorProfile


class ProfessorProfileBuilder:
    """
    Convert AuthorProfile into ProfessorProfile.

    The builder creates a lightweight envelope and does not duplicate
    publication or ranking state already stored in ProfessorIntelligence.
    """

    def build(
        self,
        author_profiles: Dict[str, AuthorProfile],
    ) -> Dict[str, ProfessorProfile]:

        professors = {}

        for pid, profile in author_profiles.items():

            professors[pid] = ProfessorProfile(
                author_profile=profile
            )

        return professors