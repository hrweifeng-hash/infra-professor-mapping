#!/usr/bin/env python3
"""
PR32 Validation — Homepage Recovery & Lab Discovery

Compares PR30 baseline vs PR32 (+ HomepageRecovery + LabDiscovery +
lab navigation expansion) on the Top-100 US infrastructure professors dataset.

PR31 did not change navigation; PR30@100 is the correct pre-PR32 baseline.

Usage:
    python3.11 tools/pr32_navigation_validation.py [--skip-pipeline]

Flags:
    --skip-pipeline   Re-use existing pr32_research_group_graph.json if present.

Reports:
    Homepage Recovery
      • recovered homepage count
      • moved pages recovered
      • meta refresh recovered
      • canonical recovered

    Lab Discovery
      • professors with lab links
      • labs discovered
      • lab pages visited
      • team pages discovered

    Recall (PR30 → PR32, matched cohort)
      • navigation success (consistent definition on both sides)
      • improved / regressed / unchanged professors
      • per-professor member comparison table (JSON + HTML)
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

OUTPUT_DIR = Path("data/output")
HOMEPAGE_GRAPH_FILE = OUTPUT_DIR / "homepage_graph.json"
BASELINE_GRAPH_FILE = OUTPUT_DIR / "pr30_research_group_graph.json"
PR32_GRAPH_FILE = OUTPUT_DIR / "pr32_research_group_graph.json"
OUT_MD = OUTPUT_DIR / "PR32_NAVIGATION_VALIDATION.md"
OUT_JSON = OUTPUT_DIR / "PR32_NAVIGATION_VALIDATION.json"
OUT_HTML = OUTPUT_DIR / "PR32_NAVIGATION_VALIDATION.html"
OUT_COMPARISON_JSON = OUTPUT_DIR / "PR32_PROFESSOR_COMPARISON.json"

TARGET_N = 100
BASELINE_VERSION = "PR30"
PR32_VERSION = "PR32"

# Navigation success: successful pipeline fetch AND at least one exported member.
# Applied identically to baseline and PR32 graphs.
ComparisonStatus = Literal["improved", "regressed", "unchanged"]


def navigation_success(graph: dict) -> bool:
    return graph.get("fetch_status") == "success" and graph.get("member_count", 0) > 0


def member_count(graph: dict) -> int:
    return graph.get("current_member_count", graph.get("member_count", 0))


def run_pr32_pipeline(skip: bool = False) -> tuple[list[dict], dict[str, float | int] | None]:
    """Run the PR32 pipeline and return serialised graphs plus fetch stats."""
    if skip and PR32_GRAPH_FILE.exists():
        existing = json.loads(PR32_GRAPH_FILE.read_text(encoding="utf-8"))
        if len(existing) >= TARGET_N:
            print(f"[PR32] --skip-pipeline: reusing {len(existing)} existing PR32 graphs.")
            return existing, None

    from homepage_agent.fetcher import FetchStats, HomepageFetcher
    from homepage_agent.homepage_resolver import CanonicalHomepageResolver
    from homepage_agent.models import HomepageGraph
    from homepage_agent.pipeline import HomepagePipeline
    from homepage_agent.providers.stub import StubNavigatorProvider
    from models.author import Author
    from models.author_profile import AuthorProfile
    from models.professor_profile import ProfessorProfile
    from research_group_agent.fetcher import ResearchGroupFetcher
    from research_group_agent.pipeline import ResearchGroupPipeline
    from research_group_agent.providers.stub import StubResearchGroupProvider

    fetch_stats = FetchStats()

    print("[PR32] Loading homepage graphs …")
    hp_raw = json.loads(HOMEPAGE_GRAPH_FILE.read_text(encoding="utf-8"))
    homepage_graphs = [HomepageGraph.from_dict(item) for item in hp_raw]
    print(f"[PR32]   {len(homepage_graphs)} homepage graphs loaded.")

    print("[PR32] Resolving canonical homepages …")
    hp_pipeline = HomepagePipeline(provider=StubNavigatorProvider())
    resolver = CanonicalHomepageResolver(
        homepage_pipeline=hp_pipeline,
        fetcher=HomepageFetcher(stats=fetch_stats),
    )
    resolved_graphs = resolver.resolve_many(homepage_graphs[:TARGET_N])
    print(f"[PR32]   {len(resolved_graphs)} resolved.")

    professors: list[ProfessorProfile] = []
    for graph in resolved_graphs:
        profile = AuthorProfile(
            author=Author(pid=None, name=graph.professor_name),
            papers=[],
        )
        professors.append(
            ProfessorProfile(
                author_profile=profile,
                homepage=graph.homepage_url,
                homepage_graph=graph,
                is_us=True,
            )
        )

    total = len(professors)
    print(f"[PR32] Running research group pipeline on {total} professors …")
    rg_fetcher = ResearchGroupFetcher(
        fetcher=HomepageFetcher(
            cache_dir="data/cache/research_groups",
            stats=fetch_stats,
        )
    )
    rg_pipeline = ResearchGroupPipeline(
        provider=StubResearchGroupProvider(),
        fetcher=rg_fetcher,
    )
    graphs = []
    for index, professor in enumerate(professors, start=1):
        name = professor.author_profile.author.name
        print(f"[PR32] [{index}/{total}] {name}", flush=True)
        if professor.homepage:
            print(f"  Homepage: {professor.homepage}", flush=True)
        graph = rg_pipeline.analyze(professor, professor.homepage_graph)
        graphs.append(graph.to_dict())

    PR32_GRAPH_FILE.write_text(
        json.dumps(graphs, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"[PR32] Wrote {PR32_GRAPH_FILE}")
    return graphs, fetch_stats.to_dict()


def _load_graphs(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def align_cohorts(
    baseline: list[dict],
    pr32: list[dict],
) -> tuple[list[dict], list[dict], list[str], dict[str, Any]]:
    """Return aligned baseline/PR32 graphs for the overlapping professor cohort."""
    baseline_by_name = {g["professor_name"]: g for g in baseline}
    pr32_by_name = {g["professor_name"]: g for g in pr32}
    overlap = sorted(baseline_by_name.keys() & pr32_by_name.keys())

    meta = {
        "baseline_count": len(baseline),
        "pr32_count": len(pr32),
        "overlap_count": len(overlap),
        "baseline_only": sorted(baseline_by_name.keys() - pr32_by_name.keys()),
        "pr32_only": sorted(pr32_by_name.keys() - baseline_by_name.keys()),
    }

    aligned_baseline = [baseline_by_name[name] for name in overlap]
    aligned_pr32 = [pr32_by_name[name] for name in overlap]
    return aligned_baseline, aligned_pr32, overlap, meta


def _comparison_status(delta: int) -> ComparisonStatus:
    if delta > 0:
        return "improved"
    if delta < 0:
        return "regressed"
    return "unchanged"


def _navigation_path(pr32_graph: dict) -> str:
    nd = pr32_graph.get("navigation_discovery") or {}
    hr = nd.get("homepage_recovery") or {}
    path_parts: list[str] = []
    if hr.get("was_recovered"):
        path_parts.append(f"Professor ({hr.get('original_url')})")
        path_parts.append(f"↓ Recovered ({hr.get('recovered_url')})")
    else:
        path_parts.append(f"Professor ({pr32_graph.get('canonical_homepage')})")
    labs = nd.get("labs_discovered") or []
    if labs:
        path_parts.append(f"↓ Lab ({labs[0].get('url')})")
    if nd.get("team_pages_discovered", 0) > 0:
        path_parts.append("↓ Team/People")
    parsed = pr32_graph.get("parsed_pages") or []
    if parsed:
        path_parts.append(f"↓ Members ({parsed[-1]})")
    return "\n".join(path_parts)


def build_professor_comparisons(
    aligned_baseline: list[dict],
    aligned_pr32: list[dict],
    professor_names: list[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, base_graph, pr32_graph in zip(
        professor_names, aligned_baseline, aligned_pr32, strict=True
    ):
        baseline_members = member_count(base_graph)
        pr32_members = member_count(pr32_graph)
        delta = pr32_members - baseline_members
        row: dict[str, Any] = {
            "professor": name,
            "baseline_members": baseline_members,
            "pr32_members": pr32_members,
            "delta": delta,
            "status": _comparison_status(delta),
            "baseline_navigation_success": navigation_success(base_graph),
            "pr32_navigation_success": navigation_success(pr32_graph),
        }
        if delta != 0:
            row["navigation_path"] = _navigation_path(pr32_graph)
        rows.append(row)

    rows.sort(key=lambda row: abs(row["delta"]), reverse=True)
    return rows


def _recovery_stats(graphs: list[dict]) -> dict[str, Any]:
    recovered = 0
    by_method: dict[str, int] = defaultdict(int)
    recovered_profs: list[dict] = []

    for g in graphs:
        nd = g.get("navigation_discovery") or {}
        hr = nd.get("homepage_recovery") or {}
        if hr.get("was_recovered"):
            recovered += 1
            method = hr.get("method") or "unknown"
            by_method[method] += 1
            recovered_profs.append({
                "professor": g.get("professor_name"),
                "original": hr.get("original_url"),
                "recovered": hr.get("recovered_url"),
                "method": method,
            })

    return {
        "recovered_homepage_count": recovered,
        "moved_pages_recovered": by_method.get("moved_page", 0),
        "meta_refresh_recovered": by_method.get("meta_refresh", 0),
        "canonical_recovered": by_method.get("canonical", 0),
        "http_redirect_recovered": by_method.get("http_redirect", 0),
        "recovered_professors": recovered_profs,
    }


def _lab_stats(graphs: list[dict]) -> dict[str, Any]:
    with_lab_links = 0
    total_labs = 0
    total_lab_pages_visited = 0
    total_team_pages = 0
    lab_details: list[dict] = []

    for g in graphs:
        nd = g.get("navigation_discovery") or {}
        labs = nd.get("labs_discovered") or []
        if labs or nd.get("professors_with_lab_links"):
            with_lab_links += 1
        total_labs += len(labs)
        total_lab_pages_visited += nd.get("lab_pages_visited", 0)
        total_team_pages += nd.get("team_pages_discovered", 0)
        if labs:
            lab_details.append({
                "professor": g.get("professor_name"),
                "labs": labs,
                "lab_pages_visited": nd.get("lab_pages_visited", 0),
                "team_pages_discovered": nd.get("team_pages_discovered", 0),
            })

    return {
        "professors_with_lab_links": with_lab_links,
        "labs_discovered": total_labs,
        "lab_pages_visited": total_lab_pages_visited,
        "team_pages_discovered": total_team_pages,
        "lab_details": lab_details,
    }


def recall_comparison(
    baseline: list[dict],
    pr32: list[dict],
) -> dict[str, Any]:
    aligned_baseline, aligned_pr32, professor_names, cohort_meta = align_cohorts(
        baseline, pr32
    )
    professor_comparisons = build_professor_comparisons(
        aligned_baseline,
        aligned_pr32,
        professor_names,
    )

    baseline_nav = sum(1 for g in aligned_baseline if navigation_success(g))
    pr32_nav = sum(1 for g in aligned_pr32 if navigation_success(g))
    baseline_members = sum(member_count(g) for g in aligned_baseline)
    pr32_members = sum(member_count(g) for g in aligned_pr32)

    improved = sum(1 for row in professor_comparisons if row["status"] == "improved")
    regressed = sum(1 for row in professor_comparisons if row["status"] == "regressed")
    unchanged = sum(1 for row in professor_comparisons if row["status"] == "unchanged")

    return {
        "methodology": {
            "baseline_version": BASELINE_VERSION,
            "pr32_version": PR32_VERSION,
            "baseline_note": (
                "PR31 did not change navigation; PR30@100 is the pre-PR32 baseline."
            ),
            "navigation_success_definition": (
                "fetch_status == 'success' AND member_count > 0"
            ),
            "comparison_scope": "matched professors by professor_name",
        },
        "cohort": cohort_meta,
        "baseline_navigation_success": baseline_nav,
        "pr32_navigation_success": pr32_nav,
        "navigation_success_delta": pr32_nav - baseline_nav,
        "baseline_total_members": baseline_members,
        "pr32_total_members": pr32_members,
        "total_members_delta": pr32_members - baseline_members,
        "improved_professors": improved,
        "regressed_professors": regressed,
        "unchanged_professors": unchanged,
        "professor_comparisons": professor_comparisons,
        "top_improvements": [
            row for row in professor_comparisons if row["status"] == "improved"
        ][:20],
        "top_regressions": [
            row for row in professor_comparisons if row["status"] == "regressed"
        ][:20],
    }


def build_report(
    baseline: list[dict],
    pr32: list[dict],
    fetch_summary: dict[str, float | int] | None = None,
) -> dict[str, Any]:
    recall = recall_comparison(baseline, pr32)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline_version": BASELINE_VERSION,
        "pr32_version": PR32_VERSION,
        "total_professors": recall["cohort"]["overlap_count"],
        "homepage_recovery": _recovery_stats(pr32),
        "lab_discovery": _lab_stats(pr32),
        "recall": recall,
        "fetch_summary": fetch_summary,
    }


def render_markdown(report: dict[str, Any]) -> str:
    hr = report["homepage_recovery"]
    ld = report["lab_discovery"]
    rc = report["recall"]

    lines = [
        "# PR32 Navigation Validation Report",
        "",
        f"Generated: {report['generated_at']}",
        "",
        "## Methodology",
        "",
        f"- Baseline: **{rc['methodology']['baseline_version']}** "
        f"({rc['cohort']['baseline_count']} graphs on disk)",
        f"- PR32: **{rc['methodology']['pr32_version']}** "
        f"({rc['cohort']['pr32_count']} graphs on disk)",
        f"- Compared cohort: **{rc['cohort']['overlap_count']}** professors "
        "(matched by `professor_name`)",
        f"- Navigation success: `{rc['methodology']['navigation_success_definition']}`",
        "",
        "## Homepage Recovery",
        "",
        "| Metric | Count |",
        "|--------|------:|",
        f"| Recovered homepages | {hr['recovered_homepage_count']} |",
        f"| Moved pages recovered | {hr['moved_pages_recovered']} |",
        f"| Meta refresh recovered | {hr['meta_refresh_recovered']} |",
        f"| Canonical recovered | {hr['canonical_recovered']} |",
        f"| HTTP redirect recovered | {hr['http_redirect_recovered']} |",
        "",
        "## Lab Discovery",
        "",
        "| Metric | Count |",
        "|--------|------:|",
        f"| Professors with lab links | {ld['professors_with_lab_links']} |",
        f"| Labs discovered | {ld['labs_discovered']} |",
        f"| Lab pages visited | {ld['lab_pages_visited']} |",
        f"| Team pages discovered | {ld['team_pages_discovered']} |",
        "",
        f"## Recall Comparison ({BASELINE_VERSION} → {PR32_VERSION})",
        "",
        f"Matched cohort: **{rc['cohort']['overlap_count']}** professors",
        "",
        "| Outcome | Count |",
        "|---------|------:|",
        f"| Improved professors | {rc['improved_professors']} |",
        f"| Regressed professors | {rc['regressed_professors']} |",
        f"| Unchanged professors | {rc['unchanged_professors']} |",
        "",
        "### Net Deltas (matched cohort)",
        "",
        (
            f"- Navigation success: "
            f"{rc['baseline_navigation_success']} → {rc['pr32_navigation_success']} "
            f"({rc['navigation_success_delta']:+d})"
        ),
        (
            f"- Current members: "
            f"{rc['baseline_total_members']} → {rc['pr32_total_members']} "
            f"({rc['total_members_delta']:+d})"
        ),
        "",
        "See `PR32_PROFESSOR_COMPARISON.json` and "
        "`PR32_NAVIGATION_VALIDATION.html` for the full per-professor table.",
        "",
    ]

    top_improvements = rc.get("top_improvements") or []
    if top_improvements:
        lines += ["## Top Improvements", ""]
        for item in top_improvements[:10]:
            lines += [
                f"### {item['professor']} ({item['delta']:+d} members)",
                "",
            ]
            if item.get("navigation_path"):
                lines += ["```", item["navigation_path"], "```", ""]

    top_regressions = rc.get("top_regressions") or []
    if top_regressions:
        lines += ["## Top Regressions", ""]
        for item in top_regressions[:10]:
            lines += [
                f"### {item['professor']} ({item['delta']:+d} members)",
                "",
            ]

    return "\n".join(lines)


def render_html(report: dict[str, Any]) -> str:
    rc = report["recall"]
    rows = rc.get("professor_comparisons") or []

    def status_label(status: str) -> str:
        return {
            "improved": "Improved",
            "regressed": "Regressed",
            "unchanged": "Unchanged",
        }.get(status, status)

    body_rows = []
    for row in rows:
        body_rows.append(
            "<tr>"
            f"<td>{html.escape(row['professor'])}</td>"
            f"<td>{row['baseline_members']}</td>"
            f"<td>{row['pr32_members']}</td>"
            f"<td>{row['delta']:+d}</td>"
            f"<td>{status_label(row['status'])}</td>"
            f"<td>{'Yes' if row['baseline_navigation_success'] else 'No'}</td>"
            f"<td>{'Yes' if row['pr32_navigation_success'] else 'No'}</td>"
            "</tr>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>PR32 Professor Comparison</title>
  <style>
    body {{ font-family: sans-serif; margin: 2rem; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ccc; padding: 0.5rem 0.75rem; text-align: left; }}
    th {{ background: #f5f5f5; }}
    tr:nth-child(even) {{ background: #fafafa; }}
    .summary {{ margin-bottom: 1.5rem; }}
  </style>
</head>
<body>
  <h1>PR32 Professor Comparison ({BASELINE_VERSION} → {PR32_VERSION})</h1>
  <p>Generated: {html.escape(report['generated_at'])}</p>
  <div class="summary">
    <p>Matched cohort: <strong>{rc['cohort']['overlap_count']}</strong> professors</p>
    <p>Improved: <strong>{rc['improved_professors']}</strong> |
       Regressed: <strong>{rc['regressed_professors']}</strong> |
       Unchanged: <strong>{rc['unchanged_professors']}</strong></p>
    <p>Navigation success:
       {rc['baseline_navigation_success']} → {rc['pr32_navigation_success']}
       ({rc['navigation_success_delta']:+d})</p>
    <p>Current members:
       {rc['baseline_total_members']} → {rc['pr32_total_members']}
       ({rc['total_members_delta']:+d})</p>
    <p>Navigation success definition:
       <code>{html.escape(rc['methodology']['navigation_success_definition'])}</code></p>
  </div>
  <table>
    <thead>
      <tr>
        <th>Professor</th>
        <th>Baseline Members</th>
        <th>PR32 Members</th>
        <th>Delta</th>
        <th>Status</th>
        <th>Baseline Nav OK</th>
        <th>PR32 Nav OK</th>
      </tr>
    </thead>
    <tbody>
      {''.join(body_rows)}
    </tbody>
  </table>
</body>
</html>
"""


def print_fetch_summary(fetch_summary: dict[str, float | int] | None) -> None:
    if fetch_summary is None:
        print("[PR32] Fetch summary unavailable (--skip-pipeline).")
        return

    print()
    print("========== Fetch Summary ==========")
    print(f"Total requests: {fetch_summary['total_requests']}")
    print(f"Successful: {fetch_summary['successful']}")
    print(f"Timeouts: {fetch_summary['timeouts']}")
    print(f"Network errors: {fetch_summary['network_errors']}")
    print(f"Redirect limit exceeded: {fetch_summary['redirect_limit_exceeded']}")
    print(f"Average latency: {fetch_summary['average_latency']:.2f}s")
    print(f"95th percentile latency: {fetch_summary['p95_latency']:.2f}s")
    print(f"Slow requests (>5s): {fetch_summary['slow_requests']}")
    print("===================================")


def print_recall_summary(recall: dict[str, Any]) -> None:
    print()
    print(f"========== Recall Summary ({BASELINE_VERSION} → {PR32_VERSION}) ==========")
    print(f"Matched cohort: {recall['cohort']['overlap_count']} professors")
    print(f"Improved professors: {recall['improved_professors']}")
    print(f"Regressed professors: {recall['regressed_professors']}")
    print(f"Unchanged professors: {recall['unchanged_professors']}")
    print(
        "Navigation success: "
        f"{recall['baseline_navigation_success']} → {recall['pr32_navigation_success']} "
        f"({recall['navigation_success_delta']:+d})"
    )
    print(
        "Current members: "
        f"{recall['baseline_total_members']} → {recall['pr32_total_members']} "
        f"({recall['total_members_delta']:+d})"
    )
    print("================================================================")


def main() -> None:
    parser = argparse.ArgumentParser(description="PR32 navigation validation")
    parser.add_argument("--skip-pipeline", action="store_true")
    args = parser.parse_args()

    pr32_graphs, fetch_summary = run_pr32_pipeline(skip=args.skip_pipeline)
    baseline_graphs = _load_graphs(BASELINE_GRAPH_FILE)

    if not baseline_graphs:
        print(f"[PR32] Error: baseline not found at {BASELINE_GRAPH_FILE}", file=sys.stderr)
        print(
            "[PR32] Expected PR30 baseline with 100 professors. "
            "Generate it before running this validation.",
            file=sys.stderr,
        )
        sys.exit(1)

    report = build_report(baseline_graphs, pr32_graphs, fetch_summary=fetch_summary)
    recall = report["recall"]
    cohort = recall["cohort"]

    if cohort["overlap_count"] < TARGET_N:
        print(
            f"[PR32] Warning: matched cohort is {cohort['overlap_count']}/{TARGET_N}. "
            f"Baseline-only: {len(cohort['baseline_only'])}, "
            f"PR32-only: {len(cohort['pr32_only'])}.",
            file=sys.stderr,
        )

    OUT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    OUT_MD.write_text(render_markdown(report), encoding="utf-8")
    OUT_HTML.write_text(render_html(report), encoding="utf-8")
    OUT_COMPARISON_JSON.write_text(
        json.dumps(recall["professor_comparisons"], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"[PR32] Wrote {OUT_MD}")
    print(f"[PR32] Wrote {OUT_JSON}")
    print(f"[PR32] Wrote {OUT_HTML}")
    print(f"[PR32] Wrote {OUT_COMPARISON_JSON}")
    print_recall_summary(recall)
    print_fetch_summary(fetch_summary)


if __name__ == "__main__":
    main()
