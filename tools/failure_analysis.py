#!/usr/bin/env python3
"""
tools/failure_analysis.py — PR21 Failure Analysis

Consumes PR21 research-group-graph output and produces a human-review dataset.
Does NOT classify failures automatically — every record leaves Root Cause as
UNKNOWN for manual annotation.

Reads:
    data/output/pr21_research_group_graph.json  (falls back to research_group_graph.json)
    data/cache/research_groups/                 (cached HTML for heading-card re-analysis)

Writes:
    data/output/FAILURE_ANALYSIS.md
    data/output/FAILURE_ANALYSIS.json

Usage:
    python3.11 tools/failure_analysis.py [--graph PATH] [--no-reparse]

Flags:
    --graph PATH     Path to research group graph JSON (default: pr21 → canonical fallback)
    --no-reparse     Skip re-parsing cached HTML; heading_card_count will be null

Design:
    This module is intentionally independent of the production pipeline.
    It imports MemberPageParser only for the optional heading-card re-parse step.
    All data loading, sorting, stats, and rendering are self-contained functions
    so that future tools (PR22/23/24) can import and reuse them.
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Paths ─────────────────────────────────────────────────────────────────────

OUTPUT_DIR = Path("data/output")
CACHE_DIR = Path("data/cache/research_groups")

_GRAPH_SEARCH_ORDER = [
    OUTPUT_DIR / "pr21_research_group_graph.json",
    OUTPUT_DIR / "research_group_graph.json",
]

FAILURE_ANALYSIS_MD = OUTPUT_DIR / "FAILURE_ANALYSIS.md"
FAILURE_ANALYSIS_JSON = OUTPUT_DIR / "FAILURE_ANALYSIS.json"

# ── Manual-review categories (displayed as checklist, never auto-assigned) ────

REVIEW_CATEGORIES: tuple[str, ...] = (
    "Navigation failure",
    "Wrong page",
    "No people page",
    "JS-rendered page",
    "Card/Grid layout",
    "Faculty directory",
    "Alumni only",
    "Parser bug",
    "No students",
    "Other",
)

ROOT_CAUSE_PLACEHOLDER = "UNKNOWN"


# ── Data record ───────────────────────────────────────────────────────────────


@dataclass
class ProfessorRecord:
    """All debugging information for one professor, gathered into a single record."""

    professor_name: str
    homepage_url: str
    candidate_pages: int
    navigation_success: bool
    group_page_url: str | None
    group_page_type: str | None
    fetch_status: str
    pages_parsed: int
    pages_successful: int
    pages_failed: int
    current_members: int
    former_members: int
    # Computed by re-parsing cached HTML; None when --no-reparse is used
    heading_card_count: int | None
    parser_used: str
    errors: list[str] = field(default_factory=list)
    parsed_page_urls: list[str] = field(default_factory=list)
    second_hop_discovered: int = 0
    second_hop_successful: int = 0
    pipeline_version: str = ""
    # Left blank for manual annotation
    root_cause: str = ROOT_CAUSE_PLACEHOLDER

    @property
    def total_members(self) -> int:
        return self.current_members + self.former_members

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["total_members"] = self.total_members
        return d


# ── Sorting ───────────────────────────────────────────────────────────────────


def sort_for_review(records: list[ProfessorRecord]) -> list[ProfessorRecord]:
    """Sort records so the most informative failure cases appear first.

    Priority order (ascending sort key):
      1. Navigation failures before successes (False < True → failures first)
      2. Zero-member professors before those with members
      3. Ascending current member count (fewest first)
      4. Alphabetical professor name
    """
    def _key(r: ProfessorRecord) -> tuple:
        return (
            r.navigation_success,    # False (0) before True (1)
            r.current_members > 0,   # False (0) before True (1)
            r.current_members,
            r.professor_name.lower(),
        )

    return sorted(records, key=_key)


# ── Statistics ────────────────────────────────────────────────────────────────


def compute_stats(records: list[ProfessorRecord]) -> dict[str, Any]:
    """Compute aggregate statistics for the summary header."""
    total = len(records)
    nav_success = sum(1 for r in records if r.navigation_success)
    zero_members = sum(1 for r in records if r.current_members == 0)
    one_to_five = sum(1 for r in records if 1 <= r.current_members <= 5)
    more_than_five = sum(1 for r in records if r.current_members > 5)
    total_current = sum(r.current_members for r in records)
    total_former = sum(r.former_members for r in records)
    total_members = total_current + total_former
    avg_members = round(total_current / total, 2) if total else 0.0

    hc_records = [r for r in records if r.heading_card_count is not None]
    total_hc = sum(r.heading_card_count for r in hc_records if r.heading_card_count)

    fetch_dist: dict[str, int] = {}
    for r in records:
        fetch_dist[r.fetch_status] = fetch_dist.get(r.fetch_status, 0) + 1

    return {
        "total_professors": total,
        "navigation_success_count": nav_success,
        "navigation_failure_count": total - nav_success,
        "professors_zero_members": zero_members,
        "professors_one_to_five_members": one_to_five,
        "professors_more_than_five_members": more_than_five,
        "average_current_members": avg_members,
        "total_current_members": total_current,
        "total_former_members": total_former,
        "total_members": total_members,
        "total_heading_card_entries": total_hc,
        "heading_card_reparsed": len(hc_records),
        "fetch_status_distribution": fetch_dist,
    }


# ── Cache helpers ─────────────────────────────────────────────────────────────


def _cache_key(url: str) -> str:
    """SHA-256 hex digest of URL, first 16 chars (matches HomepageFetcher)."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def _read_cached_html(url: str, cache_dir: Path) -> str | None:
    """Return cached HTML for url, or None if not in cache."""
    path = cache_dir / f"{_cache_key(url)}.html"
    if path.exists():
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
    return None


# ── Heading-card re-parse ─────────────────────────────────────────────────────


def compute_heading_card_count(
    parsed_page_urls: list[str],
    cache_dir: Path,
) -> int:
    """Re-parse cached HTML pages and sum heading_card_count across all pages.

    Imports MemberPageParser lazily so this module can be imported without
    the full research_group_agent package when re-parsing is disabled.
    """
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from research_group_agent.parser import MemberPageParser  # noqa: PLC0415
    except ImportError:
        return 0

    parser = MemberPageParser()
    total = 0
    for url in parsed_page_urls:
        html = _read_cached_html(url, cache_dir)
        if html:
            try:
                result = parser.parse(html, base_url=url)
                total += result.heading_card_count
            except Exception:  # noqa: BLE001
                pass
    return total


# ── Record builder ────────────────────────────────────────────────────────────


def build_record(
    graph: dict[str, Any],
    cache_dir: Path,
    reparse: bool = True,
) -> ProfessorRecord:
    """Build a ProfessorRecord from one serialised ResearchGroupGraph dict."""
    group_page = graph.get("group_page")
    parsed_pages: list[str] = graph.get("parsed_pages", [])

    heading_card_count: int | None = None
    if reparse and parsed_pages:
        heading_card_count = compute_heading_card_count(parsed_pages, cache_dir)

    return ProfessorRecord(
        professor_name=graph.get("professor_name", ""),
        homepage_url=graph.get("canonical_homepage") or graph.get("professor_homepage", ""),
        candidate_pages=graph.get("candidate_pages_discovered", 0),
        navigation_success=group_page is not None,
        group_page_url=group_page.get("url") if group_page else None,
        group_page_type=group_page.get("source_node_type") if group_page else None,
        fetch_status=graph.get("fetch_status", "unknown"),
        pages_parsed=len(parsed_pages),
        pages_successful=len(graph.get("successful_pages", [])),
        pages_failed=len(graph.get("failed_pages", [])),
        current_members=graph.get("current_member_count", graph.get("member_count", 0)),
        former_members=graph.get("former_member_count", 0),
        heading_card_count=heading_card_count,
        parser_used=graph.get("provider", "heuristic"),
        errors=graph.get("errors", []),
        parsed_page_urls=parsed_pages,
        second_hop_discovered=graph.get("second_hop_pages_discovered", 0),
        second_hop_successful=graph.get("second_hop_pages_successful", 0),
        pipeline_version=graph.get("pipeline_version", ""),
        root_cause=ROOT_CAUSE_PLACEHOLDER,
    )


# ── Graph loader ──────────────────────────────────────────────────────────────


def load_graphs(graph_path: Path | None = None) -> tuple[list[dict], Path]:
    """Load research group graphs from disk.

    Returns (graphs, resolved_path).
    Raises FileNotFoundError when no candidate file exists.
    """
    candidates = [graph_path] if graph_path else _GRAPH_SEARCH_ORDER
    for path in candidates:
        if path and Path(path).exists():
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            return data, Path(path)
    searched = [str(p) for p in (candidates if graph_path else _GRAPH_SEARCH_ORDER)]
    raise FileNotFoundError(
        f"No graph file found. Searched: {searched}\n"
        "Run `python3.11 tools/pr21_validation.py` first."
    )


# ── Markdown renderer ─────────────────────────────────────────────────────────


def _hc(value: int | None) -> str:
    return str(value) if value is not None else "N/A"


def render_markdown(
    records: list[ProfessorRecord],
    stats: dict[str, Any],
    source_path: Path,
) -> str:
    lines: list[str] = []
    now = datetime.now(timezone.utc).isoformat()

    # ── Header ────────────────────────────────────────────────────────────────
    lines += [
        "# PR21 Failure Analysis — Human Review Dataset",
        "",
        f"Generated: {now}",
        f"Source:    {source_path}",
        "",
        "This report is intentionally **unclassified** — Root Cause is left as",
        "`UNKNOWN` for manual annotation.",
        "",
        "---",
        "",
    ]

    # ── Statistics ────────────────────────────────────────────────────────────
    lines += [
        "## Summary Statistics",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total professors | **{stats['total_professors']}** |",
        f"| Navigation successes | **{stats['navigation_success_count']}** |",
        f"| Navigation failures | **{stats['navigation_failure_count']}** |",
        f"| Professors with zero members | **{stats['professors_zero_members']}** |",
        f"| Professors with 1–5 members | **{stats['professors_one_to_five_members']}** |",
        f"| Professors with >5 members | **{stats['professors_more_than_five_members']}** |",
        f"| Average current members | **{stats['average_current_members']}** |",
        f"| Total current members | **{stats['total_current_members']}** |",
        f"| Total former members | **{stats['total_former_members']}** |",
        f"| Total heading-card entries (re-parsed) | **{stats['total_heading_card_entries']}** |",
        "",
        "### Fetch Status Distribution",
        "",
    ]
    for status, count in sorted(stats["fetch_status_distribution"].items()):
        lines.append(f"- `{status}`: **{count}**")
    lines += ["", "---", ""]

    # ── Manual review categories ───────────────────────────────────────────────
    lines += [
        "## Root Cause Categories (Manual Checklist)",
        "",
        "Use the checklist below when annotating each professor record.",
        "Do NOT assign these automatically.",
        "",
    ]
    for cat in REVIEW_CATEGORIES:
        lines.append(f"- [ ] {cat}")
    lines += ["", "---", ""]

    # ── Per-professor records ─────────────────────────────────────────────────
    lines += [
        "## Professor Records",
        "",
        "Sorted by: navigation failure → zero members → lowest count → alphabetical.",
        "",
    ]

    # Partition into failure bands for readability
    nav_failures = [r for r in records if not r.navigation_success]
    nav_success_zero = [r for r in records if r.navigation_success and r.current_members == 0]
    nav_success_few = [r for r in records if r.navigation_success and 1 <= r.current_members <= 5]
    nav_success_ok = [r for r in records if r.navigation_success and r.current_members > 5]

    def _section(title: str, recs: list[ProfessorRecord]) -> None:
        if not recs:
            return
        lines.append(f"### {title} ({len(recs)})")
        lines.append("")
        for r in recs:
            _record_block(r)

    def _record_block(r: ProfessorRecord) -> None:
        nav_str = "✅ Yes" if r.navigation_success else "❌ No"
        lines.extend([
            f"#### {r.professor_name}",
            "",
            "| Field | Value |",
            "|-------|-------|",
            f"| Professor Name | {r.professor_name} |",
            f"| Homepage URL | {r.homepage_url} |",
            f"| Candidate Pages | {r.candidate_pages} |",
            f"| Navigation Success | {nav_str} |",
        ])
        if r.group_page_url:
            lines.append(f"| Group Page URL | {r.group_page_url} |")
            lines.append(f"| Group Page Type | {r.group_page_type or '—'} |")
        lines.extend([
            f"| Fetch Status | `{r.fetch_status}` |",
            f"| Pages Parsed | {r.pages_parsed} |",
            f"| Pages Successful | {r.pages_successful} |",
            f"| Pages Failed | {r.pages_failed} |",
            f"| Current Members | {r.current_members} |",
            f"| Former Members | {r.former_members} |",
            f"| Heading Card Count | {_hc(r.heading_card_count)} |",
            f"| Parser Used | {r.parser_used} |",
            f"| Second-hop Pages | {r.second_hop_discovered} discovered / {r.second_hop_successful} successful |",
        ])

        if r.errors:
            lines.append(f"| Errors | {'; '.join(r.errors)} |")

        if r.parsed_page_urls:
            lines.append("")
            lines.append("**Parsed Pages:**")
            for url in r.parsed_page_urls:
                lines.append(f"- {url}")

        lines.extend([
            "",
            "**Root Cause:**",
            "",
            f"> {r.root_cause}",
            "",
            "**Manual Classification Checklist:**",
            "",
        ])
        for cat in REVIEW_CATEGORIES:
            lines.append(f"- [ ] {cat}")
        lines.extend(["", "---", ""])

    _section("Navigation Failures — No Group Page Found", nav_failures)
    _section("Navigation Success — Zero Members Extracted", nav_success_zero)
    _section("Navigation Success — 1–5 Members", nav_success_few)
    _section("Navigation Success — >5 Members (reference)", nav_success_ok)

    return "\n".join(lines)


# ── JSON renderer ─────────────────────────────────────────────────────────────


def render_json(
    records: list[ProfessorRecord],
    stats: dict[str, Any],
    source_path: Path,
) -> str:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": str(source_path),
        "stats": stats,
        "review_categories": list(REVIEW_CATEGORIES),
        "professors": [r.to_dict() for r in records],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


# ── Main ──────────────────────────────────────────────────────────────────────


def run(
    graph_path: Path | None = None,
    reparse: bool = True,
    cache_dir: Path = CACHE_DIR,
    output_dir: Path = OUTPUT_DIR,
) -> tuple[list[ProfessorRecord], dict[str, Any]]:
    """
    Core pipeline for failure analysis.

    Returns (sorted_records, stats) so callers can inspect results without
    touching the filesystem (useful for tests and downstream tools).
    """
    graphs, resolved_path = load_graphs(graph_path)
    print(f"[failure_analysis] Loaded {len(graphs)} graphs from {resolved_path}")

    records: list[ProfessorRecord] = []
    for i, graph in enumerate(graphs, 1):
        name = graph.get("professor_name", f"unknown_{i}")
        record = build_record(graph, cache_dir=cache_dir, reparse=reparse)
        records.append(record)
        if reparse and record.heading_card_count:
            print(
                f"  [{i:3d}/{len(graphs)}] {name}: "
                f"hc={record.heading_card_count} members={record.current_members}"
            )

    sorted_records = sort_for_review(records)
    stats = compute_stats(sorted_records)

    print(
        f"[failure_analysis] Stats: "
        f"{stats['total_professors']} total, "
        f"{stats['navigation_success_count']} nav-ok, "
        f"{stats['professors_zero_members']} zero-members"
    )

    return sorted_records, stats, resolved_path  # type: ignore[return-value]


def main(argv: list[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate PR21 failure analysis dataset for manual review."
    )
    parser.add_argument(
        "--graph",
        type=Path,
        default=None,
        help="Path to research group graph JSON (default: auto-detect pr21 → canonical).",
    )
    parser.add_argument(
        "--no-reparse",
        action="store_true",
        help="Skip re-parsing cached HTML; heading_card_count will be null.",
    )
    args = parser.parse_args(argv)

    reparse = not args.no_reparse
    sorted_records, stats, source_path = run(
        graph_path=args.graph,
        reparse=reparse,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    md = render_markdown(sorted_records, stats, source_path)
    FAILURE_ANALYSIS_MD.write_text(md, encoding="utf-8")
    print(f"[failure_analysis] Markdown → {FAILURE_ANALYSIS_MD}")

    jstr = render_json(sorted_records, stats, source_path)
    FAILURE_ANALYSIS_JSON.write_text(jstr, encoding="utf-8")
    print(f"[failure_analysis] JSON    → {FAILURE_ANALYSIS_JSON}")


if __name__ == "__main__":
    main()
