"""PR16 Research Group Agent report generator."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from collections import Counter

from research_group_agent.models import (
    ExtractionRunMetrics,
    PIPELINE_VERSION,
    SCHEMA_VERSION,
    ResearchGroupGraph,
)
from research_group_agent.precision_constants import HEALTHY_MEMBER_MAX, HEALTHY_MEMBER_MIN


class ResearchGroupReport:
    """Produce a report covering group discovery, member extraction, and precision metrics."""

    @classmethod
    def generate(
        cls,
        graphs: list[ResearchGroupGraph],
        metrics: ExtractionRunMetrics | None = None,
    ) -> dict:
        metrics = metrics or ExtractionRunMetrics()
        total = len(graphs)
        groups_discovered = sum(1 for graph in graphs if graph.group_page is not None)
        successful_fetches = sum(1 for graph in graphs if graph.fetch_status == "success")
        page_rejected = sum(1 for graph in graphs if graph.fetch_status == "page_rejected")

        all_members = [member for graph in graphs for member in graph.members]
        all_former = [member for graph in graphs for member in graph.former_members]
        member_counts = metrics.member_counts or [graph.member_count for graph in graphs]
        precision_stats = cls._precision_stats(graphs, metrics, member_counts)
        homepage_stats = cls._homepage_resolution_stats(graphs, metrics)

        navigation_stats = cls._navigation_stats(graphs)
        manual_review = cls._manual_review_cases(graphs, member_counts)

        wrong_page_rejections = sum(
            1
            for rp in metrics.rejected_pages
            if rp.get("reason", "").startswith("Page title '")
        )

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "schema_version": SCHEMA_VERSION,
            "pipeline_version": PIPELINE_VERSION,
            "professors_processed": total,
            "research_groups_discovered": groups_discovered,
            "successful_group_fetches": successful_fetches,
            "rejected_pages": len(metrics.rejected_pages),
            "page_rejected_count": page_rejected,
            "wrong_page_rejections": wrong_page_rejections,
            "current_members_extracted": len(all_members),
            "former_members_extracted": len(all_former),
            "members_extracted": len(all_members),
            "current_member_ratio": round(
                len(all_members) / (len(all_members) + len(all_former) or 1), 3
            ),
            "homepage_resolution": homepage_stats,
            "navigation": navigation_stats,
            "role_distribution": cls._role_distribution(all_members),
            "identity_coverage": cls._identity_coverage(all_members),
            "language_signal_distribution": cls._language_distribution(all_members),
            "precision_statistics": precision_stats,
            "manual_review": manual_review,
            "manual_review_count": len(manual_review),
            "provider": graphs[0].provider if graphs else "n/a",
        }

    @classmethod
    def write(
        cls,
        graphs: list[ResearchGroupGraph],
        report: dict | None = None,
        metrics: ExtractionRunMetrics | None = None,
        output_dir: str = "data/output",
    ) -> tuple[Path, Path]:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        report = report or cls.generate(graphs, metrics=metrics)

        json_graph_path = out_dir / "research_group_graph.json"
        md_path = out_dir / "RESEARCH_GROUP_REPORT.md"
        json_report_path = out_dir / "RESEARCH_GROUP_REPORT.json"

        payload = [graph.to_dict() for graph in graphs]
        with json_graph_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)

        with json_report_path.open("w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, ensure_ascii=False)

        md_path.write_text(cls._render_markdown(report, graphs), encoding="utf-8")

        print(f"[PR16] Wrote research group graphs to {json_graph_path}", flush=True)
        print(f"[PR16] Wrote report to {md_path}", flush=True)

        return json_graph_path, md_path

    @classmethod
    def _homepage_resolution_stats(
        cls,
        graphs: list[ResearchGroupGraph],
        metrics: ExtractionRunMetrics,
    ) -> dict:
        with_resolution = [
            graph for graph in graphs if graph.homepage_resolution_method
        ]
        upgraded = [
            graph
            for graph in graphs
            if graph.original_homepage
            and graph.canonical_homepage
            and graph.original_homepage.rstrip("/") != graph.canonical_homepage.rstrip("/")
        ]
        no_canonical = [
            graph for graph in graphs
            if not graph.canonical_homepage or graph.canonical_homepage == graph.original_homepage
        ]
        no_current_students = [
            graph.professor_name
            for graph in graphs
            if graph.fetch_status == "success" and graph.member_count == 0
        ]

        return {
            "resolution_attempts": metrics.homepage_resolution_attempts,
            "upgrades_to_personal_homepage": len(upgraded),
            "upgrade_rate": round(len(upgraded) / (len(graphs) or 1), 3),
            "professors_without_canonical_upgrade": len(no_canonical),
            "professors_without_current_students": no_current_students,
            "conversions": [
                {
                    "professor_name": graph.professor_name,
                    "original_homepage": graph.original_homepage,
                    "canonical_homepage": graph.canonical_homepage,
                    "method": graph.homepage_resolution_method,
                    "confidence": graph.homepage_resolution_confidence,
                }
                for graph in upgraded
            ],
        }

    @classmethod
    def _navigation_stats(cls, graphs: list[ResearchGroupGraph]) -> dict:
        with_group_page = [g for g in graphs if g.group_page is not None]
        with_navigation_path = [g for g in graphs if g.navigation_path]

        confidences = [g.group_page.confidence for g in with_group_page]
        avg_confidence = round(sum(confidences) / len(confidences), 3) if confidences else 0.0

        path_depths = [len(g.navigation_path) for g in with_navigation_path]
        avg_depth = round(sum(path_depths) / len(path_depths), 2) if path_depths else 0.0

        # Provider breakdown
        provider_counts: Counter[str] = Counter(
            g.navigation_provider for g in graphs
        )

        # Evidence frequency
        all_evidence: list[str] = []
        for g in with_group_page:
            if g.group_page and g.group_page.evidence:
                all_evidence.extend(g.group_page.evidence)
        top_evidence = dict(Counter(all_evidence).most_common(10))

        fallback_count = provider_counts.get("heuristic", 0)
        llm_count = sum(v for k, v in provider_counts.items() if k != "heuristic")

        return {
            "navigation_success_rate": round(len(with_group_page) / (len(graphs) or 1), 3),
            "average_navigation_confidence": avg_confidence,
            "average_navigation_depth": avg_depth,
            "provider_breakdown": dict(provider_counts),
            "fallback_rate": round(fallback_count / (len(graphs) or 1), 3),
            "llm_navigated_count": llm_count,
            "top_evidence": top_evidence,
        }

    @classmethod
    def _precision_stats(
        cls,
        graphs: list[ResearchGroupGraph],
        metrics: ExtractionRunMetrics,
        member_counts: list[int],
    ) -> dict:
        counts = [value for value in member_counts if value >= 0]
        avg = round(sum(counts) / len(counts), 1) if counts else 0.0
        median = sorted(counts)[len(counts) // 2] if counts else 0

        histogram: Counter[str] = Counter()
        for count in counts:
            if count == 0:
                histogram["0"] += 1
            elif count <= 5:
                histogram["1-5"] += 1
            elif count <= 20:
                histogram["6-20"] += 1
            elif count <= 50:
                histogram["21-50"] += 1
            else:
                histogram["50+"] += 1

        return {
            "average_members_per_professor": avg,
            "median_members_per_professor": median,
            "rejected_candidates": len(metrics.rejected_candidates),
            "rejected_pages": len(metrics.rejected_pages),
            "rejection_reason_counts": metrics.rejection_reason_counts,
            "member_count_histogram": dict(histogram),
            "healthy_range": f"{HEALTHY_MEMBER_MIN}-{HEALTHY_MEMBER_MAX}",
            "professors_in_healthy_range": sum(
                1 for count in counts if HEALTHY_MEMBER_MIN <= count <= HEALTHY_MEMBER_MAX
            ),
            "professors_outside_healthy_range": sum(
                1 for count in counts
                if count > 0 and (count < HEALTHY_MEMBER_MIN or count > HEALTHY_MEMBER_MAX)
            ),
        }

    @classmethod
    def _role_distribution(cls, members) -> dict[str, int]:
        counts = Counter(member.role.value for member in members)
        return dict(counts.most_common())

    @classmethod
    def _identity_coverage(cls, members) -> dict:
        total = len(members) or 1
        github = sum(1 for member in members if member.digital_footprint.github)
        scholar = sum(1 for member in members if member.digital_footprint.google_scholar)
        linkedin = sum(1 for member in members if member.digital_footprint.linkedin)
        homepage = sum(1 for member in members if member.digital_footprint.homepage)
        any_identity = sum(
            1 for member in members if member.digital_footprint.identity_count() > 0
        )

        return {
            "total_members": len(members),
            "any_identity_count": any_identity,
            "any_identity_rate": round(any_identity / total, 3),
            "homepage_count": homepage,
            "homepage_rate": round(homepage / total, 3),
            "github_count": github,
            "github_rate": round(github / total, 3),
            "google_scholar_count": scholar,
            "google_scholar_rate": round(scholar / total, 3),
            "linkedin_count": linkedin,
            "linkedin_rate": round(linkedin / total, 3),
        }

    @classmethod
    def _language_distribution(cls, members) -> dict:
        with_signal = [member for member in members if member.language_signal]
        if not with_signal:
            return {"count": 0, "types": {}}

        types = Counter(
            member.language_signal.signal_type for member in with_signal
        )
        return {
            "count": len(with_signal),
            "rate": round(len(with_signal) / (len(members) or 1), 3),
            "types": dict(types),
        }

    @classmethod
    def _manual_review_cases(
        cls,
        graphs: list[ResearchGroupGraph],
        member_counts: list[int],
    ) -> list[dict]:
        cases: list[dict] = []

        for index, graph in enumerate(graphs):
            reasons: list[str] = []
            count = member_counts[index] if index < len(member_counts) else graph.member_count

            if graph.fetch_status == "skipped":
                reasons.append("group_page_not_found")
            elif graph.fetch_status == "page_rejected":
                reasons.append("page_rejected_by_classifier")
            elif graph.fetch_status != "success":
                reasons.append(f"fetch_{graph.fetch_status}")

            if graph.fetch_status == "success" and count == 0:
                reasons.append("no_members_extracted")

            if count > HEALTHY_MEMBER_MAX:
                reasons.append(f"member_count_high:{count}")
            elif 0 < count < HEALTHY_MEMBER_MIN:
                reasons.append(f"member_count_low:{count}")

            if graph.errors:
                reasons.extend(graph.errors)

            if reasons:
                cases.append(
                    {
                        "professor_name": graph.professor_name,
                        "group_page": graph.group_page.url if graph.group_page else None,
                        "member_count": count,
                        "reasons": reasons,
                    }
                )

        return cases

    @classmethod
    def _render_markdown(cls, report: dict, graphs: list[ResearchGroupGraph]) -> str:
        identity = report.get("identity_coverage", {})
        roles = report.get("role_distribution", {})
        language = report.get("language_signal_distribution", {})
        precision = report.get("precision_statistics", {})
        manual_review = report.get("manual_review", [])

        nav = report.get("navigation", {})

        pipeline_ver = report.get('pipeline_version', 'PR16')
        schema_ver = report.get('schema_version', '1.2')
        wrong_page = report.get('wrong_page_rejections', 0)

        lines = [
            f"# Research Group Intelligence Report ({pipeline_ver})",
            "",
            f"Generated: {report['generated_at']}",
            f"Schema version: **{schema_ver}** | Pipeline: **{pipeline_ver}**",
            "",
            "## Summary",
            "",
            f"- Professors processed: **{report['professors_processed']}**",
            f"- Research groups discovered: **{report['research_groups_discovered']}**",
            f"- Successful group page fetches: **{report['successful_group_fetches']}**",
            f"- Pages rejected by classifier: **{report.get('page_rejected_count', 0)}**",
            f"- Wrong-page rejections (PR16): **{wrong_page}**",
            f"- Current members extracted: **{report.get('current_members_extracted', 0)}**",
            f"- Former members (debug): **{report.get('former_members_extracted', 0)}**",
            f"- Current member ratio: **{report.get('current_member_ratio', 0):.0%}**",
            f"- Extraction provider: **{report.get('provider', 'n/a')}**",
            "",
        ]

        lines.extend([
            "## Navigation Intelligence",
            "",
            f"- Navigation provider: **{', '.join(nav.get('provider_breakdown', {}).keys()) or 'heuristic'}**",
            f"- Navigation success rate: **{nav.get('navigation_success_rate', 0):.0%}**",
            f"- Average navigation confidence: **{nav.get('average_navigation_confidence', 0):.3f}**",
            f"- Average navigation depth: **{nav.get('average_navigation_depth', 0):.1f}** hops",
            f"- Fallback rate: **{nav.get('fallback_rate', 0):.0%}**",
            f"- LLM-navigated: **{nav.get('llm_navigated_count', 0)}**",
            "",
        ])

        top_evidence = nav.get("top_evidence", {})
        if top_evidence:
            lines.extend(["### Most Common Navigation Evidence", ""])
            for signal, count in list(top_evidence.items())[:10]:
                lines.append(f"- `{signal}`: **{count}**")
            lines.append("")

        homepage = report.get("homepage_resolution", {})
        lines.extend([
            "## Homepage Resolution",
            "",
            f"- Resolution attempts: **{homepage.get('resolution_attempts', 0)}**",
            f"- Upgrades to personal homepage: **{homepage.get('upgrades_to_personal_homepage', 0)}** "
            f"({homepage.get('upgrade_rate', 0):.0%})",
            f"- Professors without canonical upgrade: "
            f"**{homepage.get('professors_without_canonical_upgrade', 0)}**",
            "",
        ])
        for conversion in homepage.get("conversions", [])[:10]:
            lines.append(
                f"- **{conversion['professor_name']}**: "
                f"{conversion['original_homepage']} → {conversion['canonical_homepage']} "
                f"({conversion['method']})"
            )
        if homepage.get("conversions"):
            lines.append("")

        no_students = homepage.get("professors_without_current_students", [])
        if no_students:
            lines.append("### Professors Without Current Students")
            for name in no_students[:10]:
                lines.append(f"- {name}")
            lines.append("")

        lines.extend([
            "## Precision Statistics",
            "",
            f"- Average members per professor: **{precision.get('average_members_per_professor', 0)}**",
            f"- Median members per professor: **{precision.get('median_members_per_professor', 0)}**",
            f"- Healthy range: **{precision.get('healthy_range', '5-20')}**",
            f"- Professors in healthy range: **{precision.get('professors_in_healthy_range', 0)}**",
            f"- Rejected pages: **{precision.get('rejected_pages', 0)}**",
            f"- Rejected candidates: **{precision.get('rejected_candidates', 0)}**",
            "",
            "### Member Count Histogram",
            "",
        ])

        for bucket, count in sorted(precision.get("member_count_histogram", {}).items()):
            lines.append(f"- {bucket}: **{count}**")
        lines.append("")

        rejection_reasons = precision.get("rejection_reason_counts", {})
        if rejection_reasons:
            lines.extend(["### Most Common Rejection Reasons", ""])
            for reason, count in list(rejection_reasons.items())[:15]:
                lines.append(f"- **{reason}**: {count}")
            lines.append("")

        lines.extend(["## Role Distribution", ""])
        if roles:
            for role, count in roles.items():
                lines.append(f"- **{role}**: {count}")
            lines.append("")
        else:
            lines.extend(["- No members extracted.", ""])

        lines.extend([
            "## Identity Coverage",
            "",
            f"- Members with any identity: **{identity.get('any_identity_count', 0)}** "
            f"({identity.get('any_identity_rate', 0):.0%})",
            f"- Homepage: **{identity.get('homepage_count', 0)}** "
            f"({identity.get('homepage_rate', 0):.0%})",
            f"- GitHub: **{identity.get('github_count', 0)}** "
            f"({identity.get('github_rate', 0):.0%})",
            f"- Google Scholar: **{identity.get('google_scholar_count', 0)}** "
            f"({identity.get('google_scholar_rate', 0):.0%})",
            f"- LinkedIn: **{identity.get('linkedin_count', 0)}** "
            f"({identity.get('linkedin_rate', 0):.0%})",
            "",
            "## Language Signal Distribution",
            "",
        ])

        if language.get("count"):
            lines.append(
                f"- Members with language signal: **{language['count']}** "
                f"({language.get('rate', 0):.0%})"
            )
            for signal_type, count in language.get("types", {}).items():
                lines.append(f"- {signal_type}: **{count}**")
            lines.append("")
            lines.append(
                "_Note: Language signals are probabilistic recruiting hints — "
                "not nationality, ethnicity, or citizenship classifications._"
            )
            lines.append("")
        else:
            lines.extend(["- No language signals generated.", ""])

        lines.extend(["## Manual Review Cases", ""])
        if manual_review:
            lines.append(f"**{len(manual_review)}** professors flagged:")
            lines.append("")
            for case in manual_review[:20]:
                reason_text = "; ".join(case["reasons"])
                lines.append(
                    f"- **{case['professor_name']}** "
                    f"({case.get('member_count', '?')} members, "
                    f"{case['group_page'] or 'no group page'}): {reason_text}"
                )
            if len(manual_review) > 20:
                lines.append(f"- ... and {len(manual_review) - 20} more")
            lines.append("")
        else:
            lines.append("No manual review cases identified.")
            lines.append("")

        lines.extend([
            "## Output",
            "",
            "- `research_group_graph.json` — ResearchGroupGraph per professor (Top 10)",
            "- `NAVIGATION_DEBUG.json` — full navigation decision log per professor",
            "- Precision-first extraction: false positives rejected over false negatives",
            "",
            f"Total graphs written: **{len(graphs)}**",
            "",
        ])

        return "\n".join(lines)
