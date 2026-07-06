from models.professor_profile import ProfessorProfile


class ProfessorRegistry:
    """
    Merge professors across conferences and years.
    """

    def __init__(self):

        self._professors: dict[str, ProfessorProfile] = {}

    def add(
        self,
        professor: ProfessorProfile,
    ):

        author = professor.author_profile.author

        key = (
            author.pid
            or author.name.strip().lower()
        )

        if key not in self._professors:

            self._professors[key] = professor
            return

        existing = self._professors[key]

        # --------------------------------------------------
        # Merge papers and author profile aggregates
        # --------------------------------------------------

        existing.author_profile.papers.extend(
            professor.author_profile.papers
        )

        existing.author_profile.conferences.update(
            professor.author_profile.conferences
        )

        existing.author_profile.active_years.update(
            professor.author_profile.active_years
        )

        unique = {}

        for paper in existing.author_profile.papers:

            paper_key = paper.dblp_key or paper.title

            unique[paper_key] = paper

        existing.author_profile.papers = list(
            unique.values()
        )

    def build(self) -> dict[str, ProfessorProfile]:

        return self._professors

    def values(self):

        return self._professors.values()

    def __len__(self):

        return len(self._professors)