#!/usr/bin/env python3
"""
Run the Homepage Intelligence Agent against existing Top100 export data.

Useful when the full DBLP dataset is unavailable. For production, run
`python main.py` — graphs and report are written automatically to data/output/.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from homepage_agent.pipeline import HomepagePipeline
from homepage_agent.providers.stub import StubNavigatorProvider
from homepage_agent.report import HomepageAgentReport
from models.author import Author
from models.author_profile import AuthorProfile
from models.professor_profile import ProfessorProfile


def _professor_from_row(row: dict) -> ProfessorProfile:
    name = row["Name"]
    profile = AuthorProfile(author=Author(pid=None, name=name), papers=[])
    return ProfessorProfile(
        author_profile=profile,
        university=row.get("University"),
        homepage=row.get("Homepage") or None,
        is_us=True,
    )


def main() -> int:
    input_path = Path("data/output/top100_us_professors.json")
    if not input_path.exists():
        print(f"Missing input file: {input_path}", file=sys.stderr)
        return 1

    rows = json.loads(input_path.read_text(encoding="utf-8"))
    professors = [_professor_from_row(row) for row in rows]

    pipeline = HomepagePipeline(provider=StubNavigatorProvider())
    graphs = pipeline.analyze_many(professors)
    json_path, md_path = HomepageAgentReport.write(graphs)

    print(f"Graphs written to {json_path}")
    print(f"Report written to {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
