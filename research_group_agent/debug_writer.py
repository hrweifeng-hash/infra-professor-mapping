"""
NavigationDebugWriter — persists all navigation decisions as NAVIGATION_DEBUG.json.

Every navigation decision — including rejected candidates, evidence, and
NavigationScore breakdown — is recorded so any routing choice can be fully
explained after the fact.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from homepage_agent.models import HomepageGraph

from research_group_agent.models import (
    PIPELINE_VERSION,
    ResearchGroupGraph,
    ResearchGroupNavigationDecision,
)


class NavigationDebugWriter:
    """
    Write NAVIGATION_DEBUG.json with every navigation decision made during a run.

    Usage::

        writer = NavigationDebugWriter()
        writer.record(
            professor_name="Ravi Netravali",
            homepage_graph=graph,
            decisions=all_decisions,
        )
        ...
        writer.write()
    """

    def __init__(self) -> None:
        self._entries: list[dict] = []

    def record(
        self,
        professor_name: str,
        homepage_graph: HomepageGraph,
        decisions: list[ResearchGroupNavigationDecision],
        selected_url: str | None = None,
    ) -> None:
        canonical = (
            homepage_graph.canonical_homepage
            or homepage_graph.effective_homepage
            or homepage_graph.homepage_url
        )
        original = homepage_graph.original_homepage or canonical

        selected_decision = None
        if selected_url:
            matched = [d for d in decisions if d.candidate_url == selected_url]
            selected_decision = matched[0].to_dict() if matched else None

        self._entries.append(
            {
                "professor_name": professor_name,
                "canonical_homepage": canonical,
                "original_homepage": original,
                "navigation_provider": (
                    decisions[0].navigation_score.provider_score > 0
                    and "provider"
                    or "heuristic"
                ),
                "selected": selected_decision,
                "all_decisions": [d.to_dict() for d in decisions],
                "rejected_count": sum(
                    len(d.rejected_candidates) for d in decisions
                ),
            }
        )

    def record_from_graphs(
        self,
        graphs: list[ResearchGroupGraph],
    ) -> None:
        """Populate entries from already-built ResearchGroupGraph objects."""
        for graph in graphs:
            gp = graph.group_page
            entry: dict = {
                "professor_name": graph.professor_name,
                "canonical_homepage": graph.canonical_homepage or graph.professor_homepage,
                "original_homepage": graph.original_homepage or graph.professor_homepage,
                "navigation_provider": graph.navigation_provider,
                "navigation_path": graph.navigation_path,
                "selected": (
                    {
                        "url": gp.url,
                        "source_node_type": gp.source_node_type,
                        "confidence": gp.confidence,
                        "reason": gp.reason,
                        "evidence": gp.evidence,
                        "navigation_score": (
                            gp.navigation_score.to_dict()
                            if gp.navigation_score
                            else None
                        ),
                    }
                    if gp
                    else None
                ),
                "fetch_status": graph.fetch_status,
                "member_count": graph.member_count,
                "errors": graph.errors,
            }
            self._entries.append(entry)

    def write(
        self,
        output_dir: str = "data/output",
        filename: str = "NAVIGATION_DEBUG.json",
    ) -> Path:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / filename

        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "pipeline_version": PIPELINE_VERSION,
            "total_professors": len(self._entries),
            "entries": self._entries,
        }
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)

        return path

    @classmethod
    def from_graphs(
        cls,
        graphs: list[ResearchGroupGraph],
        output_dir: str = "data/output",
    ) -> Path:
        """Convenience: build from finished graphs and write in one call."""
        writer = cls()
        writer.record_from_graphs(graphs)
        path = writer.write(output_dir=output_dir)
        print(f"[PR15] Navigation debug written to {path}", flush=True)
        return path
