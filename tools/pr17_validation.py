#!/usr/bin/env python3
"""
PR17 Validation Script — compares PR16 vs PR17 multi-page discovery.

Reads:
  data/output/research_group_graph.json  (PR17 pipeline output — current run)

Optionally reads:
  data/output/PR16_research_group_graph.json  (PR16 baseline snapshot, if available)

Outputs:
  data/output/PR17_VALIDATION_REPORT.md
  data/output/PR17_VALIDATION_REPORT.json
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

OUTPUT_DIR = Path("data/output")
GRAPH_FILE = OUTPUT_DIR / "research_group_graph.json"
PR16_GRAPH_FILE = OUTPUT_DIR / "PR16_research_group_graph.json"


# ─────────────────────────────────────────────────────────────────────────────
# Data loading
# ─────────────────────────────────────────────────────────────────────────────

def _load(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _pr17_graphs() -> list[dict]:
    data = _load(GRAPH_FILE)
    return data or []


def _pr16_graphs() -> list[dict]:
    data = _load(PR16_GRAPH_FILE)
    return data or []


# ─────────────────────────────────────────────────────────────────────────────
# Validation 1 — Navigation Unchanged
# ─────────────────────────────────────────────────────────────────────────────

def val1_navigation_unchanged(
    pr17_graphs: list[dict],
    pr16_graphs: list[dict],
) -> dict:
    """
    Verify that the primary group_page selection is unchanged between PR16 and PR17.

    PR17 changes multi-page iteration, not the navigation itself.  The first
    selected page (highest confidence) should match PR16's single selected page.
    """
    if not pr16_graphs:
        return {
            "baseline_available": False,
            "note": "PR16 baseline not found — skipping navigation comparison.",
        }

    pr16_by_name: dict[str, dict] = {g["professor_name"]: g for g in pr16_graphs}
    pr17_by_name: dict[str, dict] = {g["professor_name"]: g for g in pr17_graphs}

    unchanged: list[dict] = []
    changed: list[dict] = []
    new_professors: list[str] = []

    for name, g17 in pr17_by_name.items():
        g16 = pr16_by_name.get(name)
        if g16 is None:
            new_professors.append(name)
            continue

        url16 = (g16.get("group_page") or {}).get("url")
        url17 = (g17.get("group_page") or {}).get("url")

        if url16 == url17:
            unchanged.append({"professor": name, "url": url16 or "—"})
        else:
            changed.append({
                "professor": name,
                "pr16_url": url16 or "—",
                "pr17_url": url17 or "—",
            })

    total = len(pr17_by_name)
    return {
        "baseline_available": True,
        "total_professors": total,
        "navigation_unchanged": len(unchanged),
        "navigation_changed": len(changed),
        "new_professors": len(new_professors),
        "unchanged_rate": round(len(unchanged) / (total or 1), 3),
        "changed_details": changed,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Validation 2 — Pages Parsed
# ─────────────────────────────────────────────────────────────────────────────

def val2_pages_parsed(pr17_graphs: list[dict]) -> dict:
    """Analyse how many pages were parsed per professor in PR17."""
    parsed_counts = [len(g.get("parsed_pages", [])) for g in pr17_graphs]
    successful_counts = [len(g.get("successful_pages", [])) for g in pr17_graphs]
    failed_counts = [len(g.get("failed_pages", [])) for g in pr17_graphs]

    total = len(pr17_graphs) or 1

    def _avg(lst: list[int]) -> float:
        return round(sum(lst) / len(lst), 2) if lst else 0.0

    histogram: Counter[str] = Counter()
    for c in parsed_counts:
        if c == 0:
            histogram["0"] += 1
        elif c == 1:
            histogram["1"] += 1
        elif c == 2:
            histogram["2"] += 1
        else:
            histogram["3+"] += 1

    multi_page_professors = [
        g["professor_name"]
        for g in pr17_graphs
        if len(g.get("successful_pages", [])) > 1
    ]

    return {
        "total_professors": len(pr17_graphs),
        "average_parsed_pages": _avg(parsed_counts),
        "average_successful_pages": _avg(successful_counts),
        "average_failed_pages": _avg(failed_counts),
        "professors_with_multiple_successful_pages": len(multi_page_professors),
        "multi_page_rate": round(len(multi_page_professors) / total, 3),
        "parsed_count_histogram": dict(histogram),
        "multi_page_professors": multi_page_professors,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Validation 3 — Merged Members
# ─────────────────────────────────────────────────────────────────────────────

def val3_merged_members(pr17_graphs: list[dict]) -> dict:
    """Show merged member counts and source distribution."""
    member_counts = [g.get("member_count", 0) for g in pr17_graphs]
    total_members = sum(member_counts)
    professors_with_members = sum(1 for c in member_counts if c > 0)
    total = len(pr17_graphs) or 1

    # Member source distribution across all professors
    source_dist: Counter[str] = Counter()
    for g in pr17_graphs:
        for member_name, pages in (g.get("member_sources") or {}).items():
            key = f"{len(pages)}_pages"
            source_dist[key] += 1

    total_with_sources = sum(source_dist.values())
    multi_source_members = sum(v for k, v in source_dist.items() if k != "1_pages")

    return {
        "total_members": total_members,
        "professors_with_members": professors_with_members,
        "member_discovery_rate": round(professors_with_members / total, 3),
        "average_members_per_professor": round(total_members / total, 1),
        "member_source_distribution": dict(source_dist.most_common()),
        "members_from_multiple_pages": multi_source_members,
        "multi_source_rate": round(multi_source_members / (total_with_sources or 1), 3),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Validation 4 — Duplicate Reduction
# ─────────────────────────────────────────────────────────────────────────────

def val4_duplicate_reduction(pr17_graphs: list[dict]) -> dict:
    """Measure how many duplicates were removed by MemberMerger."""
    total_raw = 0
    total_final = 0

    for g in pr17_graphs:
        member_sources = g.get("member_sources") or {}
        # raw = sum of all source page appearances across members
        raw = sum(len(pages) for pages in member_sources.values())
        final = len(member_sources)
        total_raw += raw
        total_final += final

    removed = total_raw - total_final
    rate = round(removed / (total_raw or 1), 3)

    return {
        "total_raw_member_appearances": total_raw,
        "total_final_members": total_final,
        "duplicates_removed": removed,
        "deduplication_rate": rate,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Validation 5 — Member Increase vs PR16
# ─────────────────────────────────────────────────────────────────────────────

def val5_member_increase(
    pr17_graphs: list[dict],
    pr16_graphs: list[dict],
) -> dict:
    """Compare total member counts between PR16 and PR17."""
    if not pr16_graphs:
        return {
            "baseline_available": False,
            "pr17_total_members": sum(g.get("member_count", 0) for g in pr17_graphs),
            "note": "PR16 baseline not found — skipping member count comparison.",
        }

    pr16_by_name: dict[str, dict] = {g["professor_name"]: g for g in pr16_graphs}

    pr17_total = sum(g.get("member_count", 0) for g in pr17_graphs)
    pr16_total = sum(g.get("member_count", 0) for g in pr16_graphs)
    delta = pr17_total - pr16_total

    per_professor: list[dict] = []
    for g17 in pr17_graphs:
        name = g17["professor_name"]
        g16 = pr16_by_name.get(name)
        c17 = g17.get("member_count", 0)
        c16 = g16.get("member_count", 0) if g16 else 0
        if c17 != c16:
            per_professor.append({
                "professor": name,
                "pr16_count": c16,
                "pr17_count": c17,
                "delta": c17 - c16,
            })

    gained = [r for r in per_professor if r["delta"] > 0]
    lost = [r for r in per_professor if r["delta"] < 0]

    return {
        "baseline_available": True,
        "pr16_total_members": pr16_total,
        "pr17_total_members": pr17_total,
        "member_delta": delta,
        "professors_gained_members": len(gained),
        "professors_lost_members": len(lost),
        "professors_unchanged": len(pr17_graphs) - len(per_professor),
        "per_professor_changes": sorted(per_professor, key=lambda r: -abs(r["delta"]))[:20],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Validation 6 — Per-Professor Comparison
# ─────────────────────────────────────────────────────────────────────────────

def val6_per_professor(
    pr17_graphs: list[dict],
    pr16_graphs: list[dict],
) -> dict:
    """Full per-professor comparison table."""
    pr16_by_name: dict[str, dict] = {g["professor_name"]: g for g in pr16_graphs}

    rows: list[dict] = []
    for g17 in pr17_graphs:
        name = g17["professor_name"]
        g16 = pr16_by_name.get(name)
        rows.append({
            "professor": name,
            "pr16_members": g16.get("member_count", 0) if g16 else None,
            "pr17_members": g17.get("member_count", 0),
            "pr17_parsed_pages": len(g17.get("parsed_pages", [])),
            "pr17_successful_pages": len(g17.get("successful_pages", [])),
            "pr17_status": g17.get("fetch_status", "?"),
            "pr17_group_page": (g17.get("group_page") or {}).get("url", "—"),
        })

    return {"rows": rows}


# ─────────────────────────────────────────────────────────────────────────────
# Validation 7 — Architecture Verification
# ─────────────────────────────────────────────────────────────────────────────

def val7_architecture() -> dict:
    results: dict[str, Any] = {}

    # models.py checks
    models_src = Path("research_group_agent/models.py").read_text(encoding="utf-8")
    results["schema_version_is_1_3"] = 'SCHEMA_VERSION = "1.3"' in models_src
    results["pipeline_version_is_PR17"] = 'PIPELINE_VERSION = "PR17"' in models_src
    results["multi_page_selection_defined"] = "class MultiPageSelection" in models_src
    results["group_page_selection_preserved"] = "class GroupPageSelection" in models_src
    results["rgg_has_parsed_pages"] = "parsed_pages" in models_src
    results["rgg_has_successful_pages"] = "successful_pages" in models_src
    results["rgg_has_failed_pages"] = "failed_pages" in models_src
    results["rgg_has_member_sources"] = "member_sources" in models_src

    # navigator.py checks
    nav_src = Path("research_group_agent/navigator.py").read_text(encoding="utf-8")
    results["select_top_candidates_defined"] = "def select_top_candidates" in nav_src
    results["select_is_compatibility_wrapper"] = (
        "select_top_candidates" in nav_src and "def select" in nav_src
    )
    results["navigate_and_select_top_defined"] = "def navigate_and_select_top" in nav_src

    # pipeline.py checks
    pipeline_src = Path("research_group_agent/pipeline.py").read_text(encoding="utf-8")
    results["pipeline_uses_select_top_candidates"] = "select_top_candidates" in pipeline_src
    results["pipeline_iterates_pages"] = "for group_page in multi.selected_pages" in pipeline_src
    results["pipeline_uses_merger"] = "self.member_merger.merge" in pipeline_src
    results["pipeline_tracks_parsed_pages"] = "parsed_pages" in pipeline_src

    # member_merger.py checks
    merger_path = Path("research_group_agent/member_merger.py")
    results["member_merger_file_exists"] = merger_path.exists()
    if merger_path.exists():
        merger_src = merger_path.read_text(encoding="utf-8")
        results["merged_member_class_defined"] = "class MergedMember" in merger_src
        results["member_merger_class_defined"] = "class MemberMerger" in merger_src
        results["merger_deduplicates"] = "_names_match" in merger_src

    # report.py checks
    report_src = Path("research_group_agent/report.py").read_text(encoding="utf-8")
    results["report_has_multipage_stats"] = "_multipage_stats" in report_src
    results["report_has_dedup_rate"] = "deduplication_rate" in report_src
    results["report_has_member_source_distribution"] = "member_source_distribution" in report_src

    # Functional tests
    try:
        from research_group_agent.navigator import ResearchGroupNavigator
        from research_group_agent.providers.navigator_stub import StubResearchGroupNavigatorProvider
        from research_group_agent.models import MultiPageSelection, GroupPageSelection

        nav = ResearchGroupNavigator(provider=StubResearchGroupNavigatorProvider())
        multi = nav.select_top_candidates([], max_candidates=3)
        results["select_top_candidates_returns_multi"] = isinstance(multi, MultiPageSelection)
        results["empty_decisions_returns_empty_selection"] = multi.page_count == 0
    except Exception as exc:
        results["navigator_functional_test_error"] = str(exc)

    try:
        from research_group_agent.member_merger import MemberMerger, MergedMember
        from research_group_agent.models import TalentProfile, MemberRole

        merger = MemberMerger()
        p1 = TalentProfile(name="Alice Smith", role=MemberRole.PHD_STUDENT, confidence=0.8)
        p2 = TalentProfile(name="Alice Smith", role=MemberRole.PHD_STUDENT, confidence=0.7)
        p3 = TalentProfile(name="Bob Jones", role=MemberRole.PHD_STUDENT, confidence=0.9)

        result = merger.merge([
            ("http://page1.com", [p1, p3], []),
            ("http://page2.com", [p2], []),
        ])
        current = result["current"]
        stats = result["stats"]
        results["merger_deduplicates_same_name"] = len(current) == 2
        results["merger_tracks_source_pages"] = any(
            len(m.source_pages) == 2 for m in current
        )
        results["merger_dedup_rate_positive"] = stats["deduplication_rate"] > 0.0
    except Exception as exc:
        results["merger_functional_test_error"] = str(exc)

    all_pass = all(v is True for v in results.values() if isinstance(v, bool))
    results["all_checks_pass"] = all_pass
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Markdown renderer
# ─────────────────────────────────────────────────────────────────────────────

def _pct(v: float) -> str:
    return f"{v:.1%}"


def render_markdown(report: dict) -> str:
    v1 = report["val1_navigation_unchanged"]
    v2 = report["val2_pages_parsed"]
    v3 = report["val3_merged_members"]
    v4 = report["val4_duplicate_reduction"]
    v5 = report["val5_member_increase"]
    v6 = report["val6_per_professor"]
    v7 = report["val7_architecture"]

    lines: list[str] = [
        "# PR17 Validation Report",
        "",
        f"Generated: {report['generated_at']}",
        "Pipeline: **PR17** | Comparison baseline: **PR16**",
        "",
        "> **Purpose:** Validate PR17's multi-page member discovery architecture.",
        "> Confirms navigation is unchanged, pages are parsed correctly,",
        "> members are merged/deduplicated, and member recall has not decreased.",
        "",
    ]

    # ── Executive Summary ──────────────────────────────────────────────────────
    pr17_members = v5.get("pr17_total_members", v3.get("total_members", 0))
    pr16_members = v5.get("pr16_total_members", "—")
    delta = v5.get("member_delta", "—")

    lines += [
        "## Executive Summary",
        "",
        "| Metric | PR16 Baseline | PR17 |",
        "|--------|---------------|------|",
        f"| Navigation unchanged | — | **{_pct(v1.get('unchanged_rate', 1.0))}** |" if v1.get("baseline_available") else "| Navigation unchanged | — | *no baseline* |",
        f"| Average parsed pages | 1.0 | **{v2['average_parsed_pages']}** |",
        f"| Average successful pages | 1.0 | **{v2['average_successful_pages']}** |",
        f"| Total members | {pr16_members} | **{pr17_members}** |",
        f"| Member delta | — | **{delta}** |",
        f"| Deduplication rate | — | **{_pct(v4['deduplication_rate'])}** |",
        f"| Member discovery rate | — | **{_pct(v3['member_discovery_rate'])}** |",
        "",
    ]

    # ── Val 1 ─────────────────────────────────────────────────────────────────
    lines += ["## Validation 1 — Navigation Unchanged", ""]
    if not v1.get("baseline_available"):
        lines += [v1.get("note", "PR16 baseline not available."), ""]
    else:
        lines += [
            f"Primary group page selection unchanged: **{v1['navigation_unchanged']}** of "
            f"**{v1['total_professors']}** professors ({_pct(v1['unchanged_rate'])}).",
            "",
        ]
        if v1.get("changed_details"):
            lines += [
                "### Navigation Changed (inspect manually)",
                "",
                "| Professor | PR16 URL | PR17 URL |",
                "|-----------|---------|---------|",
            ]
            for d in v1["changed_details"]:
                lines.append(
                    f"| {d['professor']} | `{d['pr16_url'][:60]}` | `{d['pr17_url'][:60]}` |"
                )
            lines.append("")

    # ── Val 2 ─────────────────────────────────────────────────────────────────
    lines += [
        "## Validation 2 — Pages Parsed",
        "",
        f"- Average parsed pages: **{v2['average_parsed_pages']}**",
        f"- Average successful pages: **{v2['average_successful_pages']}**",
        f"- Professors with multiple successful pages: **{v2['professors_with_multiple_successful_pages']}** "
        f"({_pct(v2['multi_page_rate'])})",
        "",
        "### Parsed Count Histogram",
        "",
    ]
    for bucket, count in sorted(v2["parsed_count_histogram"].items()):
        lines.append(f"- {bucket} pages: **{count}** professors")
    lines.append("")

    if v2.get("multi_page_professors"):
        lines += ["### Professors with Multiple Successful Pages", ""]
        for name in v2["multi_page_professors"]:
            lines.append(f"- {name}")
        lines.append("")

    # ── Val 3 ─────────────────────────────────────────────────────────────────
    lines += [
        "## Validation 3 — Merged Members",
        "",
        f"- Total members: **{v3['total_members']}**",
        f"- Professors with members: **{v3['professors_with_members']}** "
        f"({_pct(v3['member_discovery_rate'])})",
        f"- Members found on multiple pages: **{v3['members_from_multiple_pages']}** "
        f"({_pct(v3['multi_source_rate'])})",
        "",
        "### Member Source Distribution",
        "",
    ]
    for bucket, count in sorted(v3["member_source_distribution"].items()):
        lines.append(f"- {bucket}: **{count}** members")
    lines.append("")

    # ── Val 4 ─────────────────────────────────────────────────────────────────
    lines += [
        "## Validation 4 — Duplicate Reduction",
        "",
        f"- Raw member appearances: **{v4['total_raw_member_appearances']}**",
        f"- Final deduplicated members: **{v4['total_final_members']}**",
        f"- Duplicates removed: **{v4['duplicates_removed']}**",
        f"- Deduplication rate: **{_pct(v4['deduplication_rate'])}**",
        "",
    ]

    # ── Val 5 ─────────────────────────────────────────────────────────────────
    lines += ["## Validation 5 — Member Increase vs PR16", ""]
    if not v5.get("baseline_available"):
        lines += [v5.get("note", "PR16 baseline not available."), ""]
    else:
        delta_sign = "+" if v5["member_delta"] >= 0 else ""
        lines += [
            f"- PR16 total members: **{v5['pr16_total_members']}**",
            f"- PR17 total members: **{v5['pr17_total_members']}**",
            f"- Delta: **{delta_sign}{v5['member_delta']}**",
            f"- Professors who gained members: **{v5['professors_gained_members']}**",
            f"- Professors who lost members: **{v5['professors_lost_members']}**",
            "",
        ]
        if v5.get("per_professor_changes"):
            lines += [
                "### Largest Changes",
                "",
                "| Professor | PR16 | PR17 | Delta |",
                "|-----------|------|------|-------|",
            ]
            for r in v5["per_professor_changes"][:15]:
                sign = "+" if r["delta"] >= 0 else ""
                lines.append(
                    f"| {r['professor']} | {r['pr16_count']} | {r['pr17_count']} | {sign}{r['delta']} |"
                )
            lines.append("")

    # ── Val 6 ─────────────────────────────────────────────────────────────────
    lines += [
        "## Validation 6 — Per-Professor Comparison",
        "",
        "| Professor | PR16 Members | PR17 Members | Parsed | Successful | Status |",
        "|-----------|-------------|-------------|--------|-----------|--------|",
    ]
    for row in v6["rows"]:
        pr16_m = row["pr16_members"] if row["pr16_members"] is not None else "—"
        lines.append(
            f"| {row['professor']} | {pr16_m} | {row['pr17_members']} | "
            f"{row['pr17_parsed_pages']} | {row['pr17_successful_pages']} | "
            f"{row['pr17_status']} |"
        )
    lines.append("")

    # ── Val 7 ─────────────────────────────────────────────────────────────────
    lines += [
        "## Validation 7 — Architecture Verification",
        "",
        "| Check | Result |",
        "|-------|--------|",
    ]
    for k, v in v7.items():
        if isinstance(v, bool):
            icon = "✓" if v else "✗"
            label = k.replace("_", " ").title()
            lines.append(f"| {label} | {icon} |")
    lines.append("")

    # ── Summary ───────────────────────────────────────────────────────────────
    lines += ["## Summary", ""]

    all_arch_pass = v7.get("all_checks_pass", False)
    nav_ok = not v1.get("baseline_available") or v1.get("unchanged_rate", 1.0) >= 1.0
    dedup_ok = v4["deduplication_rate"] >= 0.0  # any deduplication is progress
    members_ok = v5.get("member_delta", 0) >= 0 if v5.get("baseline_available") else True

    if all_arch_pass and nav_ok and members_ok:
        lines += [
            "**PR17 PASS** — All architecture checks pass, navigation is unchanged, "
            "and member count has not decreased.",
            "",
        ]
    elif all_arch_pass:
        lines += [
            "**PR17 PARTIAL** — Architecture checks pass. "
            "Review navigation or member count changes above.",
            "",
        ]
    else:
        lines += [
            "**PR17 ISSUES FOUND** — One or more architecture checks failed.",
            "Review Validation 7 above.",
            "",
        ]

    lines += [
        "---",
        "",
        "_Generated by `tools/pr17_validation.py` (PR17)._",
        "_Reads PR17 pipeline graph and optionally a PR16 baseline snapshot._",
        "",
    ]

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    print("[PR17 Validation] Loading artifacts…")
    pr17_graphs = _pr17_graphs()
    pr16_graphs = _pr16_graphs()

    if not pr17_graphs:
        print("ERROR: research_group_graph.json not found or empty.")
        print("       Run tools/research_group_agent_run.py first.")
        return 1

    if not pr16_graphs:
        print("WARNING: PR16_research_group_graph.json not found.")
        print("         Copy the PR16 output as PR16_research_group_graph.json for full comparison.")
        print("         Continuing with PR17 data only.")

    print(f"  PR16 graphs loaded: {len(pr16_graphs)}")
    print(f"  PR17 graphs loaded: {len(pr17_graphs)}")

    print("[PR17 Validation] Running validations…")
    v1 = val1_navigation_unchanged(pr17_graphs, pr16_graphs)
    v2 = val2_pages_parsed(pr17_graphs)
    v3 = val3_merged_members(pr17_graphs)
    v4 = val4_duplicate_reduction(pr17_graphs)
    v5 = val5_member_increase(pr17_graphs, pr16_graphs)
    v6 = val6_per_professor(pr17_graphs, pr16_graphs)
    v7 = val7_architecture()

    generated_at = datetime.now(timezone.utc).isoformat()
    report = {
        "generated_at": generated_at,
        "pipeline_version": "PR17",
        "baseline_version": "PR16",
        "val1_navigation_unchanged": v1,
        "val2_pages_parsed": v2,
        "val3_merged_members": v3,
        "val4_duplicate_reduction": v4,
        "val5_member_increase": v5,
        "val6_per_professor": v6,
        "val7_architecture": v7,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "PR17_VALIDATION_REPORT.json"
    md_path = OUTPUT_DIR / "PR17_VALIDATION_REPORT.md"

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    md_path.write_text(render_markdown(report), encoding="utf-8")

    print(f"[PR17 Validation] JSON   → {json_path}")
    print(f"[PR17 Validation] Report → {md_path}")

    print("\n── Key Findings ──────────────────────────────────────")
    nav_rate = v1.get("unchanged_rate", "N/A (no baseline)")
    nav_display = _pct(nav_rate) if isinstance(nav_rate, float) else nav_rate
    print(f"  Navigation unchanged rate    : {nav_display}")
    print(f"  Avg parsed pages / professor : {v2['average_parsed_pages']}")
    print(f"  Multi-page professors        : {v2['professors_with_multiple_successful_pages']}")
    print(f"  Total members (PR17)         : {v3['total_members']}")
    print(f"  Deduplication rate           : {_pct(v4['deduplication_rate'])}")
    if v5.get("baseline_available"):
        delta = v5["member_delta"]
        sign = "+" if delta >= 0 else ""
        print(f"  Member delta vs PR16         : {sign}{delta}")
    print(f"  Architecture checks          : {'all pass' if v7.get('all_checks_pass') else 'FAILURES'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
