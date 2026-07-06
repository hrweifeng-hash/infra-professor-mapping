#!/usr/bin/env python3
"""
Run Research Group Intelligence against existing HomepageGraph export data.

Reads data/output/homepage_graph.json and processes the top N professors
(default 10). For production, run `python main.py` — output is written
automatically to data/output/.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from homepage_agent.models import HomepageGraph
from models.author import Author
from models.author_profile import AuthorProfile
from models.professor_profile import ProfessorProfile
from research_group_agent.debug_writer import NavigationDebugWriter
from research_group_agent.models import DEFAULT_TOP_N
from research_group_agent.pipeline import ResearchGroupPipeline
from research_group_agent.providers.stub import StubResearchGroupProvider
from research_group_agent.report import ResearchGroupReport


def main() -> int:
    input_path = Path("data/output/homepage_graph.json")
    if not input_path.exists():
        print(f"Missing input file: {input_path}", file=sys.stderr)
        print("Run tools/homepage_agent_run.py first.", file=sys.stderr)
        return 1

    homepage_graphs = [
        HomepageGraph.from_dict(item)
        for item in json.loads(input_path.read_text(encoding="utf-8"))
    ]

    from homepage_agent.homepage_resolver import CanonicalHomepageResolver
    from homepage_agent.pipeline import HomepagePipeline
    from homepage_agent.providers.stub import StubNavigatorProvider

    homepage_pipeline = HomepagePipeline(provider=StubNavigatorProvider())
    homepage_graphs = CanonicalHomepageResolver(
        homepage_pipeline=homepage_pipeline
    ).resolve_many(homepage_graphs[:DEFAULT_TOP_N])

    professors: list[ProfessorProfile] = []
    for graph in homepage_graphs:
        profile = AuthorProfile(
            author=Author(pid=None, name=graph.professor_name),
            papers=[],
        )
        professor = ProfessorProfile(
            author_profile=profile,
            homepage=graph.homepage_url,
            homepage_graph=graph,
            is_us=True,
        )
        professors.append(professor)

    pipeline = ResearchGroupPipeline(provider=StubResearchGroupProvider())
    graphs = pipeline.analyze_many(professors)
    json_path, md_path = ResearchGroupReport.write(graphs, metrics=pipeline.last_metrics)
    NavigationDebugWriter.from_graphs(graphs)

    print(f"Graphs written to {json_path}")
    print(f"Report written to {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
