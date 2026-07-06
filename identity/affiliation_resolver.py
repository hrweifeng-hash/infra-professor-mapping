from collections import Counter
from pathlib import Path

from models.professor_profile import ProfessorProfile
from identity.us_university_matcher import USUniversityMatcher


class AffiliationResolver:
    """
    Resolve professor.affiliation (raw DBLP text) into structured
    university / country / is_us / affiliation_confidence fields on
    ProfessorProfile.

    No Geo API. No hardcoded logic in RankingEngine — this runs as an
    independent stage after ranking (see pipeline/mapping_pipeline.py) and
    never touches intelligence/ranking fields.
    """

    def __init__(self, matcher: USUniversityMatcher | None = None):
        self.matcher = matcher or USUniversityMatcher()
        self._unmatched: Counter = Counter()

    def resolve(self, professor: ProfessorProfile) -> ProfessorProfile:
        result = self.matcher.match(professor.affiliation)

        professor.university = result.canonical
        professor.country = result.country
        professor.is_us = result.canonical is not None
        professor.affiliation_confidence = result.confidence

        if result.canonical is None and professor.affiliation:
            self._unmatched[professor.affiliation.strip()] += 1

        return professor

    def resolve_many(self, professors: list[ProfessorProfile]) -> list[ProfessorProfile]:
        for professor in professors:
            self.resolve(professor)

        self.report()

        return professors

    def report(self) -> None:
        print()
        print("=" * 60)
        print("US Affiliation Resolution Report")
        print("=" * 60)
        print(f"Unmatched affiliation strings (distinct): {len(self._unmatched)}")
        print()

    def write_unmatched_report(
        self,
        output_path: str = "data/output/unmatched_affiliations.txt",
    ) -> None:
        """
        Dump every raw affiliation string that failed to match a known US
        university, most-common first. This is the maintenance loop for
        growing resources/us_universities.json over time — see
        docs/HANDOFF.md "Maintaining resources/us_universities.json".
        """

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            for affiliation, count in self._unmatched.most_common():
                f.write(f"{count}\t{affiliation}\n")

        print(f"[AffiliationResolver] wrote {len(self._unmatched)} unmatched affiliations to {path}")
