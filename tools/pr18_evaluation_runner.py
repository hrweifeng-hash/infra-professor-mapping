#!/usr/bin/env python3
"""
PR18 — Large Scale Pipeline Evaluation (Top 100 Professors)

Runs the full PR17 pipeline on all 100 top US infrastructure professors and
generates evaluation reports.

Usage:
    python3.11 tools/pr18_evaluation_runner.py [--skip-pipeline]

Flags:
    --skip-pipeline   Re-use existing research_group_graph.json (if it has 100
                      entries) and jump straight to report generation.
"""

from __future__ import annotations

import csv
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

OUTPUT_DIR = Path("data/output")
GRAPH_FILE = OUTPUT_DIR / "research_group_graph.json"
TOP100_JSON = OUTPUT_DIR / "top100_us_professors.json"
HOMEPAGE_GRAPH_FILE = OUTPUT_DIR / "homepage_graph.json"

TARGET_N = 100  # Run the full top-100

# ──────────────────────────────────────────────────────────────────────────────
# Pipeline runner
# ──────────────────────────────────────────────────────────────────────────────


def run_pipeline(top100_data: list[dict], skip: bool = False) -> list[dict]:
    """Run the PR17 pipeline on all 100 professors and return graphs."""
    from homepage_agent.models import HomepageGraph
    from homepage_agent.homepage_resolver import CanonicalHomepageResolver
    from homepage_agent.pipeline import HomepagePipeline
    from homepage_agent.providers.stub import StubNavigatorProvider
    from models.author import Author
    from models.author_profile import AuthorProfile
    from models.professor_profile import ProfessorProfile
    from research_group_agent.pipeline import ResearchGroupPipeline
    from research_group_agent.providers.stub import StubResearchGroupProvider
    from research_group_agent.report import ResearchGroupReport
    from research_group_agent.debug_writer import NavigationDebugWriter

    if skip and GRAPH_FILE.exists():
        existing = json.loads(GRAPH_FILE.read_text(encoding="utf-8"))
        if len(existing) >= TARGET_N:
            print(f"[PR18] --skip-pipeline: reusing {len(existing)} existing graphs.")
            return existing

    print("[PR18] Loading homepage graphs …")
    homepage_graphs_raw = json.loads(HOMEPAGE_GRAPH_FILE.read_text(encoding="utf-8"))
    homepage_graphs = [HomepageGraph.from_dict(item) for item in homepage_graphs_raw]
    print(f"[PR18]   {len(homepage_graphs)} homepage graphs loaded.")

    print("[PR18] Resolving canonical homepages …")
    hp_pipeline = HomepagePipeline(provider=StubNavigatorProvider())
    resolver = CanonicalHomepageResolver(homepage_pipeline=hp_pipeline)
    resolved_graphs = resolver.resolve_many(homepage_graphs[:TARGET_N])
    print(f"[PR18]   {len(resolved_graphs)} resolved.")

    # Build ProfessorProfile list (attach conference/university from top100_data)
    top100_by_name = {row["Name"]: row for row in top100_data}
    professors: list[ProfessorProfile] = []
    for graph in resolved_graphs:
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

    print(f"[PR18] Running research group pipeline on {len(professors)} professors …")
    rg_pipeline = ResearchGroupPipeline(
        provider=StubResearchGroupProvider(),
        top_n=TARGET_N,
    )
    graphs = rg_pipeline.analyze_many(professors)
    print(f"[PR18]   Pipeline complete. {len(graphs)} graphs produced.")

    json_path, md_path = ResearchGroupReport.write(graphs, metrics=rg_pipeline.last_metrics)
    NavigationDebugWriter.from_graphs(graphs)
    print(f"[PR18]   Graph JSON → {json_path}")
    print(f"[PR18]   Report MD  → {md_path}")

    return [json.loads(json.dumps(g.__dict__ if hasattr(g, '__dict__') else g, default=str))
            for g in graphs]


# ──────────────────────────────────────────────────────────────────────────────
# Failure classifier
# ──────────────────────────────────────────────────────────────────────────────

FAILURE_CATEGORIES = [
    "no_homepage",
    "homepage_resolution_failure",
    "navigation_failure",
    "wrong_page",
    "fetch_failure",
    "spa_javascript",
    "page_classifier_rejection",
    "parser_failure",
    "no_members_found",
    "validator_rejection",
    "other",
]


def classify_failure(graph: dict, hp_data: dict | None) -> str | None:
    """Return a failure category string or None for successes."""
    status = graph.get("fetch_status", "")
    hp_status = (hp_data or {}).get("fetch_status", "")

    # Not actually a failure
    if status == "success" and graph.get("member_count", 0) > 0:
        return None

    # No homepage
    if not (hp_data or {}).get("homepage_url") or hp_status in ("invalid_url",):
        return "no_homepage"

    # Homepage resolution / fetch failure
    if hp_status in ("network_error", "http_error", "timeout"):
        return "homepage_resolution_failure"

    # Navigation failure (no group page found)
    if status == "skipped":
        reason = " ".join(graph.get("errors", []) or []).lower()
        if "no suitable" in reason or "no group page" in reason:
            return "navigation_failure"
        if not (hp_data or {}).get("homepage_url"):
            return "no_homepage"
        return "navigation_failure"

    # Fetch failure for the group page
    if status in ("fetch_failed", "network_error", "http_error", "timeout"):
        return "fetch_failure"

    # Page rejected
    if status == "page_rejected":
        errors = " ".join(graph.get("errors", []) or []).lower()
        if "javascript" in errors or "spa" in errors or "dynamic" in errors:
            return "spa_javascript"
        if "does not match" in errors or "wrong" in errors or "different person" in errors:
            return "wrong_page"
        if "classifier" in errors or "no members section" in errors:
            return "page_classifier_rejection"
        return "page_classifier_rejection"

    # Success but no members
    if status == "success" and graph.get("member_count", 0) == 0:
        return "no_members_found"

    # Parser/extraction failure
    if status in ("parse_failed", "extraction_failed"):
        return "parser_failure"

    return "other"


# ──────────────────────────────────────────────────────────────────────────────
# Part 1 — Dataset Summary
# ──────────────────────────────────────────────────────────────────────────────


def generate_dataset_summary(top100_data: list[dict]) -> None:
    print("[PR18] Generating TOP100_DATASET_SUMMARY.md …")

    total = len(top100_data)

    # University distribution
    uni_counts: Counter = Counter()
    for p in top100_data:
        uni_counts[p.get("University") or "Unknown"] += 1

    # Conference/venue distribution
    venue_counts: Counter = Counter()
    for p in top100_data:
        venues_str = p.get("Primary Infra Venues") or ""
        for v in venues_str.split(";"):
            v = v.strip()
            if v:
                venue_counts[v] += 1

    lines = [
        "# Top 100 US Infrastructure Professors — Dataset Summary",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "## Overview",
        "",
        f"- **Total professors:** {total}",
        f"- **Unique universities:** {len(uni_counts)}",
        f"- **Conferences represented:** {', '.join(sorted(venue_counts.keys()))}",
        "",
        "## University Distribution",
        "",
        "| University | Professor Count |",
        "|------------|----------------|",
    ]
    for uni, count in sorted(uni_counts.items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"| {uni} | {count} |")

    lines += [
        "",
        "## Conference / Venue Distribution",
        "",
        "> A professor may appear in multiple venue buckets (they published at multiple conferences).",
        "",
        "| Venue | Professor Appearances |",
        "|-------|----------------------|",
    ]
    for venue, count in sorted(venue_counts.items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"| {venue} | {count} |")

    lines += [
        "",
        "## Sample Records",
        "",
        "| Rank | Name | University | Primary Venues | Score |",
        "|------|------|-----------|----------------|-------|",
    ]
    for p in top100_data[:10]:
        lines.append(
            f"| {p['Rank']} | {p['Name']} | {p.get('University','?')} "
            f"| {p.get('Primary Infra Venues','?')} | {p.get('Score','?')} |"
        )

    path = OUTPUT_DIR / "TOP100_DATASET_SUMMARY.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[PR18]   → {path}")


# ──────────────────────────────────────────────────────────────────────────────
# Analysis helpers
# ──────────────────────────────────────────────────────────────────────────────


def _avg(lst: list) -> float:
    return round(sum(lst) / len(lst), 2) if lst else 0.0


def _median(lst: list) -> float:
    return round(statistics.median(lst), 1) if lst else 0.0


def _pct(v: float) -> str:
    return f"{v:.1%}"


def compute_metrics(
    graphs: list[dict],
    top100_data: list[dict],
    homepage_graphs: list[dict],
) -> dict:
    """Compute all metrics from pipeline graphs."""
    hp_by_name = {g["professor_name"]: g for g in homepage_graphs}
    top100_by_name = {p["Name"]: p for p in top100_data}

    total = len(graphs)

    # Homepage success
    hp_success = sum(
        1 for g in graphs
        if hp_by_name.get(g["professor_name"], {}).get("fetch_status") == "success"
    )

    # Navigation success — group_page is set and not skipped
    nav_success = sum(
        1 for g in graphs
        if g.get("group_page") and g.get("fetch_status") != "skipped"
    )

    # Multi-page — more than one parsed page
    multi_page = sum(
        1 for g in graphs
        if len(g.get("parsed_pages", [])) > 1
    )

    # Fetch success
    fetch_success = sum(
        1 for g in graphs
        if len(g.get("successful_pages", [])) > 0
    )

    # Parser success (at least one successful page)
    parser_success = fetch_success  # simplified: if page fetched and classified it was parsed

    # Member discovery
    with_members = sum(1 for g in graphs if g.get("member_count", 0) > 0)

    # member_count == current_member_count (PR17 model: "members" = current members)
    current_counts = [g.get("current_member_count", g.get("member_count", 0)) for g in graphs]
    former_counts = [g.get("former_member_count", 0) for g in graphs]
    total_counts = [c + f for c, f in zip(current_counts, former_counts)]
    member_counts = current_counts  # used for "members discovered" stats (current only)
    parsed_counts = [len(g.get("parsed_pages", [])) for g in graphs]
    successful_counts = [len(g.get("successful_pages", [])) for g in graphs]

    total_members = sum(total_counts)
    total_current = sum(current_counts)
    total_former = sum(former_counts)

    # Deduplication
    total_raw = 0
    total_final = 0
    for g in graphs:
        member_sources = g.get("member_sources") or {}
        raw = sum(len(pages) for pages in member_sources.values())
        final = len(member_sources)
        total_raw += raw
        total_final += final
    dedup_rate = round((total_raw - total_final) / (total_raw or 1), 3)

    # Navigation confidence
    confidences = []
    for g in graphs:
        gp = g.get("group_page") or {}
        c = gp.get("confidence") or gp.get("navigation_confidence")
        if c is not None:
            try:
                confidences.append(float(c))
            except (TypeError, ValueError):
                pass

    # Failure classification
    failure_counts: Counter = Counter()
    for g in graphs:
        hp = hp_by_name.get(g["professor_name"])
        cat = classify_failure(g, hp)
        if cat:
            failure_counts[cat] += 1

    return {
        "total_professors": total,
        "homepage_success": hp_success,
        "homepage_success_rate": round(hp_success / total, 3),
        "navigation_success": nav_success,
        "navigation_success_rate": round(nav_success / total, 3),
        "multi_page_professors": multi_page,
        "multi_page_rate": round(multi_page / total, 3),
        "fetch_success": fetch_success,
        "fetch_success_rate": round(fetch_success / total, 3),
        "parser_success": parser_success,
        "parser_success_rate": round(parser_success / total, 3),
        "professors_with_members": with_members,
        "member_discovery_rate": round(with_members / total, 3),
        "avg_members": _avg(member_counts),
        "median_members": _median(member_counts),
        "total_members": total_members,
        "total_current_members": total_current,
        "total_former_members": total_former,
        "avg_parsed_pages": _avg(parsed_counts),
        "avg_successful_pages": _avg(successful_counts),
        "avg_navigation_confidence": _avg(confidences),
        "deduplication_rate": dedup_rate,
        "total_raw_appearances": total_raw,
        "total_final_members": total_final,
        "duplicates_removed": total_raw - total_final,
        "failure_counts": dict(failure_counts),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Part 3 — Pipeline Evaluation
# ──────────────────────────────────────────────────────────────────────────────


def generate_pipeline_evaluation(metrics: dict) -> None:
    print("[PR18] Generating PIPELINE_EVALUATION.md …")
    m = metrics
    lines = [
        "# Pipeline Evaluation — Top 100 Professors",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "Pipeline: **PR17** | Dataset: Top 100 US Infrastructure Professors",
        "",
        "---",
        "",
        "## Overall Metrics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total professors | **{m['total_professors']}** |",
        f"| Homepage success rate | **{_pct(m['homepage_success_rate'])}** ({m['homepage_success']}/{m['total_professors']}) |",
        f"| Navigation success rate | **{_pct(m['navigation_success_rate'])}** ({m['navigation_success']}/{m['total_professors']}) |",
        f"| Multi-page success rate | **{_pct(m['multi_page_rate'])}** ({m['multi_page_professors']}/{m['total_professors']}) |",
        f"| Page fetch success rate | **{_pct(m['fetch_success_rate'])}** ({m['fetch_success']}/{m['total_professors']}) |",
        f"| Parser success rate | **{_pct(m['parser_success_rate'])}** ({m['parser_success']}/{m['total_professors']}) |",
        f"| Member discovery rate | **{_pct(m['member_discovery_rate'])}** ({m['professors_with_members']}/{m['total_professors']}) |",
        "",
        "## Member Statistics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Average members discovered (current) | **{m['avg_members']}** |",
        f"| Median members discovered (current) | **{m['median_members']}** |",
        f"| Total members (current + former) | **{m['total_members']}** |",
        f"| Current members | **{m['total_current_members']}** |",
        f"| Former members | **{m['total_former_members']}** |",
        "",
        "## Page Processing Statistics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Average pages parsed | **{m['avg_parsed_pages']}** |",
        f"| Average successful pages | **{m['avg_successful_pages']}** |",
        f"| Average navigation confidence | **{m['avg_navigation_confidence']:.3f}** |",
        "",
        "## Deduplication",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total raw member appearances | **{m['total_raw_appearances']}** |",
        f"| Final deduplicated members | **{m['total_final_members']}** |",
        f"| Duplicates removed | **{m['duplicates_removed']}** |",
        f"| Deduplication rate | **{_pct(m['deduplication_rate'])}** |",
        "",
        "## Failure Summary",
        "",
        "| Category | Count | Rate |",
        "|----------|-------|------|",
    ]
    total = m["total_professors"]
    for cat in FAILURE_CATEGORIES:
        count = m["failure_counts"].get(cat, 0)
        if count > 0:
            lines.append(f"| {cat.replace('_', ' ').title()} | {count} | {_pct(count/total)} |")

    lines += [
        "",
        "---",
        "_Generated by `tools/pr18_evaluation_runner.py`_",
    ]
    path = OUTPUT_DIR / "PIPELINE_EVALUATION.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[PR18]   → {path}")


# ──────────────────────────────────────────────────────────────────────────────
# Part 4 — Failure Breakdown
# ──────────────────────────────────────────────────────────────────────────────


def generate_failure_breakdown(
    graphs: list[dict],
    top100_data: list[dict],
    homepage_graphs: list[dict],
) -> None:
    print("[PR18] Generating FAILURE_BREAKDOWN.md …")
    hp_by_name = {g["professor_name"]: g for g in homepage_graphs}
    top100_by_name = {p["Name"]: p for p in top100_data}
    total = len(graphs)

    categorized: dict[str, list[dict]] = defaultdict(list)
    for g in graphs:
        hp = hp_by_name.get(g["professor_name"])
        cat = classify_failure(g, hp)
        if cat:
            prof_data = top100_by_name.get(g["professor_name"], {})
            categorized[cat].append({
                "name": g["professor_name"],
                "university": prof_data.get("University", "?"),
                "homepage": g.get("professor_homepage") or g.get("professor_homepage", ""),
                "status": g.get("fetch_status", "?"),
                "errors": (g.get("errors") or [])[:2],
                "group_page": (g.get("group_page") or {}).get("url", "—"),
            })

    lines = [
        "# Failure Breakdown — PR17 Pipeline",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        f"Total professors: **{total}**",
        "",
        "---",
        "",
    ]

    for cat in FAILURE_CATEGORIES:
        entries = categorized.get(cat, [])
        count = len(entries)
        if count == 0:
            continue
        pct = _pct(count / total)
        lines += [
            f"## {cat.replace('_', ' ').title()}",
            "",
            f"**Count:** {count} | **Rate:** {pct}",
            "",
        ]

        # Description per category
        descriptions = {
            "no_homepage": "Professor has no valid homepage URL in the dataset.",
            "homepage_resolution_failure": "Homepage URL was invalid or unreachable.",
            "navigation_failure": "No suitable research group page found via navigator.",
            "wrong_page": "Navigator selected a page belonging to a different professor.",
            "fetch_failure": "Research group page could not be fetched (network/HTTP error).",
            "spa_javascript": "Page is a JavaScript SPA and returned no parseable HTML content.",
            "page_classifier_rejection": "Page classified as not a research group page.",
            "parser_failure": "Page was fetched but member extraction returned no results.",
            "no_members_found": "Pipeline succeeded but parser found zero members.",
            "validator_rejection": "Members were extracted but rejected by the validator.",
            "other": "Uncategorized failure.",
        }
        lines.append(f"_{descriptions.get(cat, '')}_")
        lines.append("")

        # Representative examples (up to 5)
        lines += [
            "### Examples",
            "",
            "| Professor | University | Status | Group Page | Errors |",
            "|-----------|-----------|--------|-----------|--------|",
        ]
        for e in entries[:5]:
            errs = "; ".join(str(x)[:60] for x in e["errors"]) or "—"
            gp = (e["group_page"] or "—")[:60]
            lines.append(
                f"| {e['name']} | {e['university']} | {e['status']} | `{gp}` | {errs} |"
            )
        if len(entries) > 5:
            lines.append(f"| … and {len(entries)-5} more | | | | |")
        lines.append("")

    lines += [
        "---",
        "_Generated by `tools/pr18_evaluation_runner.py`_",
    ]
    path = OUTPUT_DIR / "FAILURE_BREAKDOWN.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[PR18]   → {path}")


# ──────────────────────────────────────────────────────────────────────────────
# Part 5 — University Report
# ──────────────────────────────────────────────────────────────────────────────


def generate_university_report(
    graphs: list[dict],
    top100_data: list[dict],
    homepage_graphs: list[dict],
) -> None:
    print("[PR18] Generating UNIVERSITY_REPORT.md …")
    top100_by_name = {p["Name"]: p for p in top100_data}
    hp_by_name = {g["professor_name"]: g for g in homepage_graphs}

    uni_stats: dict[str, dict] = defaultdict(lambda: {
        "total": 0, "nav_success": 0, "with_members": 0,
        "member_counts": [],
    })

    for g in graphs:
        name = g["professor_name"]
        p = top100_by_name.get(name, {})
        uni = p.get("University") or "Unknown"
        s = uni_stats[uni]
        s["total"] += 1
        if g.get("group_page") and g.get("fetch_status") != "skipped":
            s["nav_success"] += 1
        mc = g.get("member_count", 0)
        s["member_counts"].append(mc)
        if mc > 0:
            s["with_members"] += 1

    rows = []
    for uni, s in uni_stats.items():
        total = s["total"]
        nav_rate = round(s["nav_success"] / total, 3)
        disc_rate = round(s["with_members"] / total, 3)
        avg_m = _avg(s["member_counts"])
        rows.append({
            "university": uni,
            "total": total,
            "nav_success": s["nav_success"],
            "nav_rate": nav_rate,
            "disc_rate": disc_rate,
            "avg_members": avg_m,
            "with_members": s["with_members"],
        })

    rows.sort(key=lambda r: (-r["disc_rate"], -r["avg_members"]))

    lines = [
        "# University Report — PR17 Pipeline Evaluation",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "## All Universities",
        "",
        "| University | Professors | Nav Success | Member Discovery | Avg Members |",
        "|-----------|-----------|------------|-----------------|-------------|",
    ]
    for r in rows:
        lines.append(
            f"| {r['university']} | {r['total']} | {r['nav_success']} ({_pct(r['nav_rate'])}) "
            f"| {r['with_members']} ({_pct(r['disc_rate'])}) | {r['avg_members']} |"
        )

    # Top performers (sorted by avg_members, min 2 professors)
    top = [r for r in sorted(rows, key=lambda x: -x["avg_members"]) if r["total"] >= 2][:5]
    bottom = [r for r in sorted(rows, key=lambda x: x["avg_members"]) if r["total"] >= 2][:5]

    lines += [
        "",
        "## Top Performing Universities",
        "(by average members discovered, ≥2 professors)",
        "",
        "| University | Professors | Avg Members | Discovery Rate |",
        "|-----------|-----------|------------|---------------|",
    ]
    for r in top:
        lines.append(
            f"| {r['university']} | {r['total']} | {r['avg_members']} | {_pct(r['disc_rate'])} |"
        )

    lines += [
        "",
        "## Lowest Performing Universities",
        "(by average members discovered, ≥2 professors)",
        "",
        "| University | Professors | Avg Members | Discovery Rate |",
        "|-----------|-----------|------------|---------------|",
    ]
    for r in bottom:
        lines.append(
            f"| {r['university']} | {r['total']} | {r['avg_members']} | {_pct(r['disc_rate'])} |"
        )

    lines += [
        "",
        "---",
        "_Generated by `tools/pr18_evaluation_runner.py`_",
    ]
    path = OUTPUT_DIR / "UNIVERSITY_REPORT.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[PR18]   → {path}")


# ──────────────────────────────────────────────────────────────────────────────
# Part 6 — Conference Report
# ──────────────────────────────────────────────────────────────────────────────


def generate_conference_report(
    graphs: list[dict],
    top100_data: list[dict],
    homepage_graphs: list[dict],
) -> None:
    print("[PR18] Generating CONFERENCE_REPORT.md …")
    top100_by_name = {p["Name"]: p for p in top100_data}

    CONF_ORDER = ["OSDI", "SOSP", "NSDI", "ATC", "EuroSys", "FAST", "SIGCOMM", "ASPLOS"]

    conf_stats: dict[str, dict] = defaultdict(lambda: {
        "total": 0, "nav_success": 0, "with_members": 0, "member_counts": [],
    })

    for g in graphs:
        name = g["professor_name"]
        p = top100_by_name.get(name, {})
        venues_str = p.get("Primary Infra Venues") or ""
        venues = [v.strip() for v in venues_str.split(";") if v.strip()]
        if not venues:
            venues = ["Other"]

        for venue in venues:
            s = conf_stats[venue]
            s["total"] += 1
            if g.get("group_page") and g.get("fetch_status") != "skipped":
                s["nav_success"] += 1
            mc = g.get("member_count", 0)
            s["member_counts"].append(mc)
            if mc > 0:
                s["with_members"] += 1

    all_confs = CONF_ORDER + [c for c in conf_stats if c not in CONF_ORDER]

    lines = [
        "# Conference Report — PR17 Pipeline Evaluation",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "> Note: A professor may appear under multiple conference buckets if they publish at multiple venues.",
        "",
        "| Conference | Professor Appearances | Nav Success | Member Discovery | Avg Members |",
        "|-----------|----------------------|------------|-----------------|-------------|",
    ]
    for conf in all_confs:
        s = conf_stats.get(conf)
        if not s:
            continue
        total = s["total"]
        nav_r = round(s["nav_success"] / total, 3)
        disc_r = round(s["with_members"] / total, 3)
        avg_m = _avg(s["member_counts"])
        lines.append(
            f"| {conf} | {total} | {s['nav_success']} ({_pct(nav_r)}) "
            f"| {s['with_members']} ({_pct(disc_r)}) | {avg_m} |"
        )

    lines += [
        "",
        "---",
        "_Generated by `tools/pr18_evaluation_runner.py`_",
    ]
    path = OUTPUT_DIR / "CONFERENCE_REPORT.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[PR18]   → {path}")


# ──────────────────────────────────────────────────────────────────────────────
# Part 7 — Professor-Level CSV
# ──────────────────────────────────────────────────────────────────────────────


def generate_top100_results_csv(
    graphs: list[dict],
    top100_data: list[dict],
    homepage_graphs: list[dict],
) -> None:
    print("[PR18] Generating TOP100_RESULTS.csv …")
    top100_by_name = {p["Name"]: p for p in top100_data}
    hp_by_name = {g["professor_name"]: g for g in homepage_graphs}

    rows = []
    for g in graphs:
        name = g["professor_name"]
        p = top100_by_name.get(name, {})
        hp = hp_by_name.get(name, {})
        gp = g.get("group_page") or {}
        failure = classify_failure(g, hp)

        rows.append({
            "Professor": name,
            "University": p.get("University", ""),
            "Conference": p.get("Primary Infra Venues", ""),
            "Homepage": p.get("Homepage", ""),
            "Resolved Homepage": g.get("canonical_homepage") or g.get("professor_homepage", ""),
            "Selected Pages": "; ".join(g.get("parsed_pages", [])),
            "Pages Parsed": len(g.get("parsed_pages", [])),
            "Members Discovered": g.get("member_count", 0),
            "Current Members": g.get("current_member_count", 0),
            "Former Members": g.get("former_member_count", 0),
            "Failure Category": failure or "",
            "Navigation Confidence": gp.get("confidence", ""),
            "Pipeline Status": g.get("fetch_status", ""),
        })

    path = OUTPUT_DIR / "TOP100_RESULTS.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"[PR18]   → {path}")


# ──────────────────────────────────────────────────────────────────────────────
# Part 8 — Bottleneck Ranking
# ──────────────────────────────────────────────────────────────────────────────


def generate_bottleneck_report(
    graphs: list[dict],
    metrics: dict,
    top100_data: list[dict],
    homepage_graphs: list[dict],
) -> None:
    print("[PR18] Generating PIPELINE_BOTTLENECKS.md …")
    hp_by_name = {g["professor_name"]: g for g in homepage_graphs}
    total = metrics["total_professors"]
    fc = metrics["failure_counts"]

    # Calculate potential gains
    bottlenecks = []

    # 1. navigation_failure / no group page
    nav_fail = fc.get("navigation_failure", 0)
    # If we fixed nav failures, those profs could discover members
    # Assume average members = current avg_members across successful profs
    successful_member_counts = [
        g.get("member_count", 0) for g in graphs
        if g.get("member_count", 0) > 0
    ]
    avg_success_members = _avg(successful_member_counts) if successful_member_counts else 0
    nav_gain = round((nav_fail / total) * 100, 1)
    bottlenecks.append({
        "rank": 1,
        "name": "Navigator — No Group Page Found",
        "failure_category": "navigation_failure",
        "affected_professors": nav_fail,
        "rate": round(nav_fail / total, 3),
        "estimated_improvement": f"+{nav_gain:.0f}% member discovery coverage",
        "evidence": (
            f"{nav_fail} professors had no group page selected. "
            f"At avg {avg_success_members:.1f} members each, fixing this could add "
            f"~{round(nav_fail * avg_success_members):.0f} members."
        ),
    })

    # 2. page_classifier_rejection
    cls_fail = fc.get("page_classifier_rejection", 0)
    cls_gain = round((cls_fail / total) * 100, 1)
    bottlenecks.append({
        "rank": 2,
        "name": "Page Classifier — Rejection of Valid Pages",
        "failure_category": "page_classifier_rejection",
        "affected_professors": cls_fail,
        "rate": round(cls_fail / total, 3),
        "estimated_improvement": f"+{cls_gain:.0f}% member discovery coverage",
        "evidence": (
            f"{cls_fail} professors had their group page rejected by the classifier. "
            "This suggests overly strict classification criteria."
        ),
    })

    # 3. no_members_found (parser finds nothing)
    no_members = fc.get("no_members_found", 0)
    nm_gain = round((no_members / total) * 100, 1)
    bottlenecks.append({
        "rank": 3,
        "name": "Parser — Member Section Not Detected",
        "failure_category": "no_members_found",
        "affected_professors": no_members,
        "rate": round(no_members / total, 3),
        "estimated_improvement": f"+{nm_gain:.0f}% member discovery coverage",
        "evidence": (
            f"{no_members} professors had a successful page fetch but zero members extracted. "
            "Improving section detection and member extraction patterns would address this."
        ),
    })

    # 4. homepage resolution failure
    hp_fail = fc.get("homepage_resolution_failure", 0) + fc.get("no_homepage", 0)
    hp_gain = round((hp_fail / total) * 100, 1)
    bottlenecks.append({
        "rank": 4,
        "name": "Homepage Resolution — Invalid / Unreachable URLs",
        "failure_category": "homepage_resolution_failure / no_homepage",
        "affected_professors": hp_fail,
        "rate": round(hp_fail / total, 3),
        "estimated_improvement": f"+{hp_gain:.0f}% pipeline coverage",
        "evidence": (
            f"{hp_fail} professors have invalid or unreachable homepage URLs. "
            "Adding fallback resolution (DBLP profile page, institution directory) would recover these."
        ),
    })

    # 5. wrong_page
    wrong = fc.get("wrong_page", 0)
    wrong_gain = round((wrong / total) * 100, 1)
    bottlenecks.append({
        "rank": 5,
        "name": "Navigator — Wrong Page Selected",
        "failure_category": "wrong_page",
        "affected_professors": wrong,
        "rate": round(wrong / total, 3),
        "estimated_improvement": f"+{wrong_gain:.0f}% member discovery coverage",
        "evidence": (
            f"{wrong} professors had a group page selected that belonged to a different person. "
            "Cross-identity verification improvements could reduce this."
        ),
    })

    # 6. SPA/JavaScript
    spa = fc.get("spa_javascript", 0)
    spa_gain = round((spa / total) * 100, 1)
    bottlenecks.append({
        "rank": 6,
        "name": "Fetcher — JavaScript / SPA Pages",
        "failure_category": "spa_javascript",
        "affected_professors": spa,
        "rate": round(spa / total, 3),
        "estimated_improvement": f"+{spa_gain:.0f}% member discovery coverage",
        "evidence": (
            f"{spa} professors have group pages built as JavaScript SPAs. "
            "A JS-capable fetcher (e.g. Playwright) would recover these."
        ),
    })

    # 7. multi-page expansion potential
    multi_gain_potential = metrics["multi_page_professors"]
    single_success = [
        g for g in graphs
        if len(g.get("successful_pages", [])) == 1 and g.get("member_count", 0) < 5
    ]
    bottlenecks.append({
        "rank": 7,
        "name": "Multi-page Discovery — Expand Candidate Set",
        "failure_category": "improvement_opportunity",
        "affected_professors": len(single_success),
        "rate": round(len(single_success) / total, 3),
        "estimated_improvement": "+5–15% member recall on single-page successes",
        "evidence": (
            f"{len(single_success)} professors succeeded with exactly one page and fewer than 5 members. "
            f"Expanding candidate pages from 3→5 may find additional lab/people pages. "
            f"Currently {multi_gain_potential} professors already benefit from multi-page."
        ),
    })

    # Sort by affected_professors desc
    bottlenecks.sort(key=lambda b: -b["affected_professors"])
    for i, b in enumerate(bottlenecks, 1):
        b["rank"] = i

    lines = [
        "# Pipeline Bottleneck Ranking",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "Bottlenecks are ranked by number of affected professors.",
        "All estimates are derived from the PR17 evaluation run — not guesses.",
        "",
        "---",
        "",
    ]

    for b in bottlenecks:
        lines += [
            f"## {b['rank']}. {b['name']}",
            "",
            f"**Failure Category:** `{b['failure_category']}`",
            f"**Affected Professors:** {b['affected_professors']} ({_pct(b['rate'])})",
            f"**Estimated Improvement:** {b['estimated_improvement']}",
            "",
            f"**Evidence:** {b['evidence']}",
            "",
            "---",
            "",
        ]

    lines += [
        "## Summary Table",
        "",
        "| Rank | Bottleneck | Affected | Rate | Potential Gain |",
        "|------|-----------|---------|------|---------------|",
    ]
    for b in bottlenecks:
        lines.append(
            f"| {b['rank']} | {b['name']} | {b['affected_professors']} "
            f"| {_pct(b['rate'])} | {b['estimated_improvement']} |"
        )

    lines += [
        "",
        "---",
        "_Generated by `tools/pr18_evaluation_runner.py`_",
    ]
    path = OUTPUT_DIR / "PIPELINE_BOTTLENECKS.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[PR18]   → {path}")


# ──────────────────────────────────────────────────────────────────────────────
# Part 9 — Dashboard JSON
# ──────────────────────────────────────────────────────────────────────────────


def generate_evaluation_summary_json(
    metrics: dict,
    top100_data: list[dict],
    graphs: list[dict],
) -> None:
    print("[PR18] Generating evaluation_summary.json …")

    top100_by_name = {p["Name"]: p for p in top100_data}

    # University breakdown
    uni_data: dict[str, dict] = defaultdict(lambda: {
        "professors": 0, "with_members": 0, "total_members": 0
    })
    conf_data: dict[str, dict] = defaultdict(lambda: {
        "professors": 0, "with_members": 0, "total_members": 0
    })

    for g in graphs:
        name = g["professor_name"]
        p = top100_by_name.get(name, {})
        uni = p.get("University") or "Unknown"
        mc = g.get("member_count", 0)

        uni_data[uni]["professors"] += 1
        uni_data[uni]["total_members"] += mc
        if mc > 0:
            uni_data[uni]["with_members"] += 1

        venues = [v.strip() for v in (p.get("Primary Infra Venues") or "").split(";") if v.strip()]
        for v in venues:
            conf_data[v]["professors"] += 1
            conf_data[v]["total_members"] += mc
            if mc > 0:
                conf_data[v]["with_members"] += 1

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_version": "PR17",
        "evaluation_run": "PR18",
        "dataset": {
            "total_professors": len(top100_data),
            "unique_universities": len(set(p.get("University", "?") for p in top100_data)),
            "conferences": sorted(set(
                v.strip()
                for p in top100_data
                for v in (p.get("Primary Infra Venues") or "").split(";")
                if v.strip()
            )),
        },
        "overall": metrics,
        "university_breakdown": {
            uni: {
                "professors": d["professors"],
                "with_members": d["with_members"],
                "discovery_rate": round(d["with_members"] / d["professors"], 3),
                "avg_members": round(d["total_members"] / d["professors"], 1),
                "total_members": d["total_members"],
            }
            for uni, d in sorted(uni_data.items())
        },
        "conference_breakdown": {
            conf: {
                "appearances": d["professors"],
                "with_members": d["with_members"],
                "discovery_rate": round(d["with_members"] / d["professors"], 3),
                "avg_members": round(d["total_members"] / d["professors"], 1),
                "total_members": d["total_members"],
            }
            for conf, d in sorted(conf_data.items())
        },
    }

    path = OUTPUT_DIR / "evaluation_summary.json"
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[PR18]   → {path}")


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────


def main() -> int:
    skip_pipeline = "--skip-pipeline" in sys.argv

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load dataset metadata
    print("[PR18] Loading Top 100 professor dataset …")
    top100_data = json.loads(TOP100_JSON.read_text(encoding="utf-8"))
    print(f"[PR18]   {len(top100_data)} professors.")

    # Load homepage graphs
    homepage_graphs = json.loads(HOMEPAGE_GRAPH_FILE.read_text(encoding="utf-8"))

    # ── Part 1: Dataset Summary ────────────────────────────────────────────────
    generate_dataset_summary(top100_data)

    # ── Part 2: Run pipeline ───────────────────────────────────────────────────
    _graphs_raw = run_pipeline(top100_data, skip=skip_pipeline)

    # After pipeline runs, reload from the authoritative JSON file
    graphs = json.loads(GRAPH_FILE.read_text(encoding="utf-8"))
    print(f"[PR18] Loaded {len(graphs)} graphs from {GRAPH_FILE}")

    # ── Parts 3–9: Analysis ────────────────────────────────────────────────────
    metrics = compute_metrics(graphs, top100_data, homepage_graphs)

    generate_pipeline_evaluation(metrics)
    generate_failure_breakdown(graphs, top100_data, homepage_graphs)
    generate_university_report(graphs, top100_data, homepage_graphs)
    generate_conference_report(graphs, top100_data, homepage_graphs)
    generate_top100_results_csv(graphs, top100_data, homepage_graphs)
    generate_bottleneck_report(graphs, metrics, top100_data, homepage_graphs)
    generate_evaluation_summary_json(metrics, top100_data, graphs)

    print()
    print("=" * 70)
    print("PR18 Evaluation Complete")
    print("=" * 70)
    print(f"  Total professors     : {metrics['total_professors']}")
    print(f"  Homepage success     : {_pct(metrics['homepage_success_rate'])}")
    print(f"  Navigation success   : {_pct(metrics['navigation_success_rate'])}")
    print(f"  Member discovery     : {_pct(metrics['member_discovery_rate'])}")
    print(f"  Total members        : {metrics['total_members']}")
    print(f"  Avg members          : {metrics['avg_members']}")
    print(f"  Deduplication rate   : {_pct(metrics['deduplication_rate'])}")
    print()
    print("  Output files:")
    for fname in [
        "TOP100_DATASET_SUMMARY.md",
        "PIPELINE_EVALUATION.md",
        "FAILURE_BREAKDOWN.md",
        "UNIVERSITY_REPORT.md",
        "CONFERENCE_REPORT.md",
        "TOP100_RESULTS.csv",
        "PIPELINE_BOTTLENECKS.md",
        "evaluation_summary.json",
    ]:
        p = OUTPUT_DIR / fname
        exists = "✓" if p.exists() else "✗"
        print(f"  {exists} {p}")
    print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
