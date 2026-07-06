#!/usr/bin/env python3
"""
Generate a PR11 validation report from synthetic professor fixtures.

Useful when the full DBLP dataset is unavailable. For production validation,
run `python main.py` — the report is written automatically to data/output/.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.author import Author
from models.author_profile import AuthorProfile
from models.paper import Paper
from models.professor_intelligence import ProfessorIntelligence
from models.professor_profile import ProfessorProfile
from intelligence.ranking_engine import RankingEngine
from validation.pr11_validation_report import PR11ValidationReport


def _build(name: str, venues: dict[str, int], university: str) -> ProfessorProfile:
    papers = []
    for venue, count in venues.items():
        for i in range(count):
            papers.append(
                Paper(
                    title=f"{venue} work {i}",
                    authors=[Author(pid=None, name=name)],
                    venue=venue,
                    year=2024 - (i % 3),
                )
            )

    profile = AuthorProfile(author=Author(pid=None, name=name), papers=papers)
    return ProfessorProfile(
        author_profile=profile,
        intelligence=ProfessorIntelligence(
            publication_count=len(papers),
            venue_distribution=venues,
            research_areas=["Distributed Systems", "Operating Systems"],
        ),
        university=university,
        country="United States",
        is_us=True,
        affiliation_confidence=0.9,
        homepage=f"https://example.edu/~{name.split()[0].lower()}",
    )


def main() -> int:
    fixtures = [
        _build("Ravi Netravali", {"NSDI": 4, "SOSP": 2, "OSDI": 2}, "Princeton University"),
        _build("Michael I. Jordan", {"NeurIPS": 8, "ICML": 6, "ICLR": 4}, "UC Berkeley"),
        _build("Ion Stoica", {"NSDI": 3, "OSDI": 2, "ICML": 4, "NeurIPS": 3}, "UC Berkeley"),
        _build("Mosharaf Chowdhury", {"NSDI": 4, "OSDI": 2, "SIGCOMM": 2}, "University of Michigan"),
        _build("Jure Leskovec", {"NeurIPS": 10, "ICML": 8, "ICLR": 5}, "Stanford University"),
    ]

    engine = RankingEngine()
    professors = {p.author_profile.author.name: p for p in fixtures}
    ranked = engine.rank(professors)

    us_top100 = ranked[:100]

    report = PR11ValidationReport.generate(
        ranked_professors=ranked,
        us_top100=us_top100,
    )
    path = PR11ValidationReport.write(report)

    print(f"Report written to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
