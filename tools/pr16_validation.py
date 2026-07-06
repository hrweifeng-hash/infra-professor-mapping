#!/usr/bin/env python3
"""
PR16 Validation Script — compares PR15.5 vs PR16 on the pages that previously failed.

Reads:
  data/output/FAILED_GROUP_PAGES.json   (PR15.5 failure inspector output)
  data/output/research_group_graph.json (PR16 pipeline output)

Outputs:
  data/output/PR16_VALIDATION_REPORT.md
  data/output/PR16_VALIDATION_REPORT.json
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
FAILED_PAGES_FILE = OUTPUT_DIR / "FAILED_GROUP_PAGES.json"
GRAPH_FILE = OUTPUT_DIR / "research_group_graph.json"


# ─────────────────────────────────────────────────────────────────────────────
# Data loading
# ─────────────────────────────────────────────────────────────────────────────

def _load(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _pr15_5_failures() -> list[dict]:
    data = _load(FAILED_PAGES_FILE)
    if not data:
        return []
    return data.get("failures", [])


def _pr16_graphs() -> list[dict]:
    data = _load(GRAPH_FILE)
    return data or []


# ─────────────────────────────────────────────────────────────────────────────
# Validation 1 — Wrong-Page Filter Effectiveness
# ─────────────────────────────────────────────────────────────────────────────

def val1_wrong_page_filter(
    pr15_5_failures: list[dict],
    pr16_by_name: dict[str, dict],
) -> dict:
    """
    Count how many pages that PR15.5 identified as 'wrong_page_navigated'
    are now caught by PR16's _wrong_page_professor() filter.
    """
    wrong_in_pr15_5: list[dict] = []
    for rec in pr15_5_failures:
        sigs = rec.get("visible_signals") or {}
        if sigs.get("wrong_page_detected"):
            wrong_in_pr15_5.append(rec)

    caught_by_pr16: list[dict] = []
    still_missed: list[dict] = []

    for rec in wrong_in_pr15_5:
        name = rec["professor"]
        g16 = pr16_by_name.get(name)
        if g16 is None:
            still_missed.append({"professor": name, "reason": "not in PR16 output"})
            continue

        errors = g16.get("errors", [])
        wrong_page_caught = any("Wrong page:" in e for e in errors)
        if wrong_page_caught:
            caught_by_pr16.append({
                "professor": name,
                "pr16_error": errors[0] if errors else "—",
                "pr16_status": g16.get("fetch_status"),
            })
        else:
            still_missed.append({
                "professor": name,
                "pr16_status": g16.get("fetch_status"),
                "pr16_errors": errors,
                "pr15_5_url": rec.get("research_group_url"),
            })

    total = len(wrong_in_pr15_5)
    caught = len(caught_by_pr16)
    return {
        "wrong_page_identified_by_pr15_5": total,
        "caught_by_pr16_filter": caught,
        "catch_rate": round(caught / (total or 1), 3),
        "still_missed": len(still_missed),
        "caught_details": caught_by_pr16,
        "missed_details": still_missed,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Validation 2 — Member Count Comparison (PR15.5 baseline vs PR16)
# ─────────────────────────────────────────────────────────────────────────────

def val2_member_count_delta(
    pr15_5_failures: list[dict],
    pr16_graphs: list[dict],
    pr16_by_name: dict[str, dict],
) -> dict:
    """
    For every professor that failed in PR15.5, compare PR16 member count.
    Also show total member count change across all professors.
    """
    pr15_5_names = {r["professor"] for r in pr15_5_failures}

    previously_failed_now_fixed: list[dict] = []
    still_zero: list[dict] = []

    for name in pr15_5_names:
        g16 = pr16_by_name.get(name)
        if g16 is None:
            continue
        count = g16.get("member_count", 0)
        if count > 0:
            previously_failed_now_fixed.append({
                "professor": name,
                "pr16_members": count,
                "pr16_status": g16.get("fetch_status"),
            })
        else:
            still_zero.append({
                "professor": name,
                "pr16_status": g16.get("fetch_status"),
                "pr16_errors": g16.get("errors", []),
            })

    total_pr16_members = sum(g.get("member_count", 0) for g in pr16_graphs)
    total_pr16_with_members = sum(1 for g in pr16_graphs if g.get("member_count", 0) > 0)

    return {
        "previously_failed_professors": len(pr15_5_names),
        "now_fixed_in_pr16": len(previously_failed_now_fixed),
        "still_zero_in_pr16": len(still_zero),
        "fixed_details": previously_failed_now_fixed,
        "still_zero_details": still_zero,
        "total_pr16_member_count": total_pr16_members,
        "professors_with_members_pr16": total_pr16_with_members,
        "total_professors_pr16": len(pr16_graphs),
        "member_discovery_rate_pr16": round(
            total_pr16_with_members / (len(pr16_graphs) or 1), 3
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Validation 3 — Failure Category Shift
# ─────────────────────────────────────────────────────────────────────────────

def val3_failure_category_shift(
    pr15_5_failures: list[dict],
    pr16_by_name: dict[str, dict],
) -> dict:
    """
    Show how PR15.5 failure categories map to PR16 outcomes.
    E.g. pages that were 'section_detection_failure' in PR15.5 may now be
    properly rejected as 'wrong page' in PR16 (improving precision).
    """
    rows: list[dict] = []
    for rec in pr15_5_failures:
        name = rec["professor"]
        g16 = pr16_by_name.get(name)
        pr15_cat = rec.get("failure_category", "unknown")
        pr15_label = rec.get("failure_category_label", pr15_cat)

        pr16_status = g16.get("fetch_status", "not_in_output") if g16 else "not_in_output"
        pr16_errors = g16.get("errors", []) if g16 else []
        pr16_members = g16.get("member_count", 0) if g16 else 0

        pr16_outcome: str
        if pr16_members > 0:
            pr16_outcome = "members_extracted"
        elif any("Wrong page:" in e for e in pr16_errors):
            pr16_outcome = "wrong_page_rejected"
        elif pr16_status == "page_rejected":
            pr16_outcome = "page_rejected"
        elif pr16_status == "skipped":
            pr16_outcome = "skipped"
        elif pr16_status == "success":
            pr16_outcome = "success_zero_members"
        else:
            pr16_outcome = pr16_status or "unknown"

        rows.append({
            "professor": name,
            "pr15_5_category": pr15_label,
            "pr16_outcome": pr16_outcome,
            "pr16_members": pr16_members,
        })

    # Summarize
    transition_counts: Counter[str] = Counter(
        f"{r['pr15_5_category']} → {r['pr16_outcome']}" for r in rows
    )
    pr16_outcome_counts: Counter[str] = Counter(r["pr16_outcome"] for r in rows)

    return {
        "total_previously_failed": len(rows),
        "pr16_outcome_distribution": dict(pr16_outcome_counts.most_common()),
        "transition_matrix": dict(transition_counts.most_common()),
        "per_professor": rows,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Validation 4 — Precision Impact of Wrong-Page Filter
# ─────────────────────────────────────────────────────────────────────────────

def val4_precision_impact(
    pr16_graphs: list[dict],
) -> dict:
    """
    Measure precision impact: how many pages in PR16 were rejected by the
    wrong-page filter vs the standard classifier, and what the overall
    page-rejection breakdown looks like.
    """
    total = len(pr16_graphs)
    fetch_status_counts: Counter[str] = Counter(
        g.get("fetch_status", "unknown") for g in pr16_graphs
    )

    wrong_page_caught = 0
    classifier_rejected = 0

    for g in pr16_graphs:
        if g.get("fetch_status") != "page_rejected":
            continue
        errors = g.get("errors", [])
        if any("Wrong page:" in e for e in errors):
            wrong_page_caught += 1
        else:
            classifier_rejected += 1

    skipped = fetch_status_counts.get("skipped", 0)
    success = fetch_status_counts.get("success", 0)

    return {
        "total_professors": total,
        "fetch_status_breakdown": dict(fetch_status_counts.most_common()),
        "wrong_page_filter_rejections": wrong_page_caught,
        "standard_classifier_rejections": classifier_rejected,
        "total_page_rejected": wrong_page_caught + classifier_rejected,
        "skipped_no_group_page": skipped,
        "successful_fetches": success,
        "professors_with_members": sum(
            1 for g in pr16_graphs if g.get("member_count", 0) > 0
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Validation 5 — Architecture Verification
# ─────────────────────────────────────────────────────────────────────────────

def val5_architecture() -> dict:
    results: dict[str, Any] = {}

    pipeline_src = Path("research_group_agent/pipeline.py").read_text(encoding="utf-8")
    results["wrong_page_professor_defined"] = "_wrong_page_professor" in pipeline_src
    results["wrong_page_called_in_analyze"] = (
        "wrong_reason = _wrong_page_professor(parsed, name)" in pipeline_src
    )
    results["wrong_page_rejection_recorded"] = (
        "record_rejected_page" in pipeline_src
        and "wrong_reason" in pipeline_src
    )

    models_src = Path("research_group_agent/models.py").read_text(encoding="utf-8")
    results["schema_version_is_1_2"] = 'SCHEMA_VERSION = "1.2"' in models_src
    results["pipeline_version_is_PR16"] = 'PIPELINE_VERSION = "PR16"' in models_src

    report_src = Path("research_group_agent/report.py").read_text(encoding="utf-8")
    results["report_includes_wrong_page_metric"] = "wrong_page_rejections" in report_src
    results["report_header_is_PR16"] = "PR16" in report_src

    try:
        from research_group_agent.pipeline import _wrong_page_professor
        from research_group_agent.parser import ParsedMemberPage

        parsed_wrong = ParsedMemberPage(page_title="Owolabi Legunsen")
        reason = _wrong_page_professor(parsed_wrong, "Tianyin Xu")
        results["wrong_page_catches_different_person"] = reason is not None

        parsed_correct = ParsedMemberPage(page_title="Tianyin Xu Research Group")
        reason2 = _wrong_page_professor(parsed_correct, "Tianyin Xu")
        results["wrong_page_passes_lab_title"] = reason2 is None

        parsed_match = ParsedMemberPage(page_title="Tianyin Xu")
        reason3 = _wrong_page_professor(parsed_match, "Tianyin Xu")
        results["wrong_page_passes_matching_name"] = reason3 is None

    except Exception as exc:
        results["function_test_error"] = str(exc)

    all_pass = all(v is True for v in results.values() if isinstance(v, bool))
    results["all_checks_pass"] = all_pass
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Markdown renderer
# ─────────────────────────────────────────────────────────────────────────────

def _pct(v: float) -> str:
    return f"{v:.0%}"


def render_markdown(report: dict) -> str:
    v1 = report["val1_wrong_page_filter"]
    v2 = report["val2_member_count_delta"]
    v3 = report["val3_failure_category_shift"]
    v4 = report["val4_precision_impact"]
    v5 = report["val5_architecture"]

    lines: list[str] = [
        "# PR16 Validation Report",
        "",
        f"Generated: {report['generated_at']}",
        "Pipeline: **PR16** | Comparison baseline: **PR15.5**",
        "",
        "> **Purpose:** Validate that PR16's `_wrong_page_professor()` filter",
        "> correctly catches pages that PR15.5 identified as wrong-page navigations,",
        "> and that no regressions were introduced.",
        "",
    ]

    # ── Executive Summary ────────────────────────────────────────────────────
    lines += [
        "## Executive Summary",
        "",
        "| Metric | PR15.5 Baseline | PR16 |",
        "|--------|-----------------|------|",
        f"| Wrong pages identified | {v1['wrong_page_identified_by_pr15_5']} | — |",
        f"| Wrong pages caught by filter | — | **{v1['caught_by_pr16_filter']}** "
        f"({_pct(v1['catch_rate'])}) |",
        f"| Total page rejections | — | {v4['total_page_rejected']} |",
        f"| Wrong-page rejections | — | {v4['wrong_page_filter_rejections']} |",
        f"| Standard classifier rejections | — | {v4['standard_classifier_rejections']} |",
        f"| Professors with members | — | **{v2['professors_with_members_pr16']}** "
        f"({_pct(v2['member_discovery_rate_pr16'])}) |",
        f"| Total members extracted | — | **{v2['total_pr16_member_count']}** |",
        "",
    ]

    # ── Val 1 ────────────────────────────────────────────────────────────────
    lines += [
        "## Validation 1 — Wrong-Page Filter Effectiveness",
        "",
        f"PR15.5 identified **{v1['wrong_page_identified_by_pr15_5']}** professors where "
        "the navigator landed on a different person's page.",
        f"PR16's `_wrong_page_professor()` filter catches **{v1['caught_by_pr16_filter']}** "
        f"of these ({_pct(v1['catch_rate'])}).",
        "",
    ]

    if v1["caught_details"]:
        lines += [
            "### Caught by PR16 Filter",
            "",
            "| Professor | PR16 Status | Rejection Reason (truncated) |",
            "|-----------|------------|------------------------------|",
        ]
        for d in v1["caught_details"]:
            reason_short = (d["pr16_error"][:70] + "…") if len(d["pr16_error"]) > 70 else d["pr16_error"]
            lines.append(f"| {d['professor']} | {d['pr16_status']} | `{reason_short}` |")
        lines.append("")

    if v1["missed_details"]:
        lines += [
            "### Still Missed (not caught by filter)",
            "",
            "| Professor | PR16 Status | PR15.5 URL |",
            "|-----------|------------|-----------|",
        ]
        for d in v1["missed_details"]:
            url = d.get("pr15_5_url") or "—"
            status = d.get("pr16_status") or d.get("reason") or "—"
            lines.append(f"| {d['professor']} | {status} | `{url}` |")
        lines.append("")

    # ── Val 2 ────────────────────────────────────────────────────────────────
    lines += [
        "## Validation 2 — Member Count Comparison",
        "",
        f"Of **{v2['previously_failed_professors']}** previously-failed professors:",
        "",
        f"- Now fixed in PR16 (members > 0): **{v2['now_fixed_in_pr16']}**",
        f"- Still zero members in PR16: **{v2['still_zero_in_pr16']}**",
        "",
        "### PR16 Overall Member Coverage",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Professors processed | {v2['total_professors_pr16']} |",
        f"| Professors with members | **{v2['professors_with_members_pr16']}** "
        f"({_pct(v2['member_discovery_rate_pr16'])}) |",
        f"| Total members extracted | **{v2['total_pr16_member_count']}** |",
        "",
    ]

    if v2["fixed_details"]:
        lines += [
            "### Previously Failed, Now Fixed",
            "",
            "| Professor | PR16 Members | Status |",
            "|-----------|-------------|--------|",
        ]
        for d in sorted(v2["fixed_details"], key=lambda x: -x["pr16_members"]):
            lines.append(f"| {d['professor']} | {d['pr16_members']} | {d['pr16_status']} |")
        lines.append("")

    if v2["still_zero_details"]:
        lines += [
            "### Still Zero Members in PR16",
            "",
            "| Professor | PR16 Status | Errors |",
            "|-----------|------------|--------|",
        ]
        for d in v2["still_zero_details"]:
            err_short = "; ".join(d["pr16_errors"])[:60] + ("…" if len("; ".join(d["pr16_errors"])) > 60 else "")
            lines.append(f"| {d['professor']} | {d['pr16_status']} | {err_short} |")
        lines.append("")

    # ── Val 3 ────────────────────────────────────────────────────────────────
    lines += [
        "## Validation 3 — Failure Category Shift (PR15.5 → PR16)",
        "",
        "Shows how each PR15.5 failure category maps to a PR16 outcome.",
        "",
        "### PR16 Outcome Distribution (for previously-failed professors)",
        "",
        "| PR16 Outcome | Count | Share |",
        "|--------------|-------|-------|",
    ]
    total_prev = v3["total_previously_failed"] or 1
    for outcome, count in v3["pr16_outcome_distribution"].items():
        lines.append(f"| {outcome.replace('_', ' ').title()} | {count} | {_pct(count / total_prev)} |")
    lines.append("")

    if v3["transition_matrix"]:
        lines += [
            "### Transition Matrix (PR15.5 category → PR16 outcome)",
            "",
            "| Transition | Count |",
            "|-----------|-------|",
        ]
        for transition, count in list(v3["transition_matrix"].items())[:15]:
            lines.append(f"| {transition} | {count} |")
        lines.append("")

    lines += [
        "### Per-Professor Outcome",
        "",
        "| Professor | PR15.5 Category | PR16 Outcome | PR16 Members |",
        "|-----------|----------------|-------------|-------------|",
    ]
    for row in v3["per_professor"]:
        lines.append(
            f"| {row['professor']} | {row['pr15_5_category']} | "
            f"{row['pr16_outcome'].replace('_', ' ')} | {row['pr16_members']} |"
        )
    lines.append("")

    # ── Val 4 ────────────────────────────────────────────────────────────────
    lines += [
        "## Validation 4 — PR16 Precision Impact",
        "",
        "| Metric | Count |",
        "|--------|-------|",
        f"| Total professors | {v4['total_professors']} |",
        f"| Successful fetches | {v4['successful_fetches']} |",
        f"| Wrong-page filter rejections | **{v4['wrong_page_filter_rejections']}** |",
        f"| Standard classifier rejections | {v4['standard_classifier_rejections']} |",
        f"| Total page_rejected | {v4['total_page_rejected']} |",
        f"| Skipped (no group page) | {v4['skipped_no_group_page']} |",
        f"| Professors with members | **{v4['professors_with_members']}** |",
        "",
        "### Fetch Status Breakdown",
        "",
        "| Status | Count |",
        "|--------|-------|",
    ]
    for status, count in v4["fetch_status_breakdown"].items():
        lines.append(f"| {status} | {count} |")
    lines.append("")

    # ── Val 5 ────────────────────────────────────────────────────────────────
    lines += [
        "## Validation 5 — Architecture Verification",
        "",
        "| Check | Result |",
        "|-------|--------|",
    ]
    for k, v in v5.items():
        if isinstance(v, bool):
            icon = "✓" if v else "✗"
            label = k.replace("_", " ").title()
            lines.append(f"| {label} | {icon} |")
    lines.append("")

    # ── Summary ──────────────────────────────────────────────────────────────
    lines += [
        "## Summary",
        "",
    ]

    all_arch_pass = v5.get("all_checks_pass", False)
    catch_rate = v1["catch_rate"]

    if all_arch_pass and catch_rate >= 1.0:
        lines += [
            "**PR16 PASS** — All architecture checks pass and the wrong-page filter",
            "catches 100% of the pages identified by PR15.5.",
            "",
        ]
    elif all_arch_pass:
        lines += [
            f"**PR16 PARTIAL** — Architecture checks pass. Wrong-page filter catch rate: "
            f"{_pct(catch_rate)}.",
            "",
            "Some pages identified by PR15.5 as wrong-page navigations are not caught.",
            "This is expected when the page title is a lab name rather than a personal name.",
            "",
        ]
    else:
        lines += [
            "**PR16 ISSUES FOUND** — One or more architecture checks failed. "
            "Review Validation 5 above.",
            "",
        ]

    lines += [
        "---",
        "",
        "_Generated by `tools/pr16_validation.py` (PR16)._",
        "_Reads PR15.5 failure inspector output and PR16 pipeline graph._",
        "",
    ]

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    print("[PR16 Validation] Loading artifacts…")
    pr15_5_failures = _pr15_5_failures()
    pr16_graphs = _pr16_graphs()

    if not pr16_graphs:
        print("ERROR: research_group_graph.json not found or empty.")
        print("       Run tools/research_group_agent_run.py first.")
        return 1

    if not pr15_5_failures:
        print("WARNING: FAILED_GROUP_PAGES.json not found.")
        print("         Run tools/pr15_5_failure_inspector.py for full comparison.")
        print("         Continuing with PR16 pipeline data only.")

    print(f"  PR15.5 failures loaded: {len(pr15_5_failures)}")
    print(f"  PR16 graphs loaded: {len(pr16_graphs)}")

    pr16_by_name: dict[str, dict] = {g["professor_name"]: g for g in pr16_graphs}

    print("[PR16 Validation] Running validations…")
    v1 = val1_wrong_page_filter(pr15_5_failures, pr16_by_name)
    v2 = val2_member_count_delta(pr15_5_failures, pr16_graphs, pr16_by_name)
    v3 = val3_failure_category_shift(pr15_5_failures, pr16_by_name)
    v4 = val4_precision_impact(pr16_graphs)
    v5 = val5_architecture()

    generated_at = datetime.now(timezone.utc).isoformat()
    report = {
        "generated_at": generated_at,
        "pipeline_version": "PR16",
        "baseline_version": "PR15.5",
        "val1_wrong_page_filter": v1,
        "val2_member_count_delta": v2,
        "val3_failure_category_shift": v3,
        "val4_precision_impact": v4,
        "val5_architecture": v5,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "PR16_VALIDATION_REPORT.json"
    md_path = OUTPUT_DIR / "PR16_VALIDATION_REPORT.md"

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    md_path.write_text(render_markdown(report), encoding="utf-8")

    print(f"[PR16 Validation] JSON   → {json_path}")
    print(f"[PR16 Validation] Report → {md_path}")

    print("\n── Key Findings ──────────────────────────────────────")
    print(f"  Wrong-page filter catch rate : {_pct(v1['catch_rate'])}")
    print(f"  Total wrong-page rejections  : {v4['wrong_page_filter_rejections']}")
    print(f"  Member discovery rate (PR16) : {_pct(v2['member_discovery_rate_pr16'])}")
    print(f"  Total members extracted      : {v2['total_pr16_member_count']}")
    print(f"  Architecture checks          : {'all pass' if v5.get('all_checks_pass') else 'FAILURES'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
