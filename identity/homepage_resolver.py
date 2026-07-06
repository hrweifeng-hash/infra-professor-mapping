from models.professor_profile import ProfessorProfile


class HomepageResolver:
    """
    Resolve a professor's homepage.

    Currently DBLP-only: professor.homepage is already populated by
    DBLPWWWEnrichmentBuilder (bulk <www> record join) before this runs.
    OpenAlex / university faculty-directory sources are intentionally
    deferred to a future PR (see docs/HANDOFF.md TODOs) — add them here
    (e.g. as a priority-ordered list of sources) only once actually
    implemented, rather than guessing at the abstraction now.
    """

    def resolve(self, professor: ProfessorProfile) -> str | None:
        return professor.homepage or None
