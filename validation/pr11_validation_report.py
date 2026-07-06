"""PR11 validation report generator."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from models.professor_profile import ProfessorProfile
from validation.professor_identification import (
    ProfessorRole,
    classify_professor_role,
)


@dataclass
class Top100Comparison:
    legacy_names: list[str]
    new_names: list[str]
    added: list[str]
    removed: list[str]
    rank_changes: list[dict]


class PR11ValidationReport:
    """
    Produce a recruiter-facing validation report covering:
    - Legacy vs PR11 Top100 comparison
    - Infrastructure affinity distribution
    - Professor role estimates
    - Ranking engine improvement notes
    """

    FUTURE_RANKING_SIGNALS = [
        {
            "signal": "Recent activity (last 2 years)",
            "data_available": True,
            "recruiter_value": "High — surfaces actively publishing candidates",
            "notes": "yearly_publications already computed; weight recent papers",
        },
        {
            "signal": "Venue diversity",
            "data_available": True,
            "recruiter_value": "Medium — breadth vs single-venue specialists",
            "notes": "venue_distribution length / entropy",
        },
        {
            "signal": "Long-term impact / seniority",
            "data_available": True,
            "recruiter_value": "Medium — distinguishes established leaders",
            "notes": "active_years, first_publication_year spread",
        },
        {
            "signal": "Productivity trend",
            "data_available": True,
            "recruiter_value": "Medium — rising vs declining output",
            "notes": "productivity_analyzer exists but not in overall_score",
        },
        {
            "signal": "Infrastructure affinity (PR11)",
            "data_available": True,
            "recruiter_value": "High — core deliverable quality fix",
            "notes": "Implemented as 30% of overall_score",
        },
    ]

    @classmethod
    def generate(
        cls,
        ranked_professors: list[ProfessorProfile],
        us_top100: list[ProfessorProfile],
    ) -> dict:
        us_professors = [p for p in ranked_professors if p.is_us]

        legacy_top100 = sorted(
            us_professors,
            key=lambda p: p.intelligence.legacy_overall_score,
            reverse=True,
        )[:100]

        comparison = cls._compare_top100(legacy_top100, us_top100)
        role_counts = cls._role_estimates(us_top100)
        affinity_stats = cls._affinity_stats(us_top100)

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "us_professor_count": len(us_professors),
            "top100_comparison": comparison,
            "infrastructure_affinity": affinity_stats,
            "professor_role_estimates": role_counts,
            "future_ranking_signals": cls.FUTURE_RANKING_SIGNALS,
            "recommendations": cls._recommendations(role_counts, affinity_stats),
        }

    @classmethod
    def write(
        cls,
        report: dict,
        output_dir: str = "data/output",
    ) -> Path:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        json_path = out_dir / "PR11_VALIDATION_REPORT.json"
        md_path = out_dir / "PR11_VALIDATION_REPORT.md"

        with json_path.open("w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        md_path.write_text(cls._render_markdown(report), encoding="utf-8")

        print(f"[PR11] Wrote validation report to {md_path}", flush=True)
        return md_path

    @classmethod
    def _compare_top100(
        cls,
        legacy_top100: list[ProfessorProfile],
        new_top100: list[ProfessorProfile],
    ) -> dict:
        legacy_names = [p.author_profile.author.name for p in legacy_top100]
        new_names = [p.author_profile.author.name for p in new_top100]

        legacy_set = set(legacy_names)
        new_set = set(new_names)

        legacy_rank = {name: i + 1 for i, name in enumerate(legacy_names)}
        new_rank = {name: i + 1 for i, name in enumerate(new_names)}

        rank_changes = []
        for name in legacy_set & new_set:
            delta = legacy_rank[name] - new_rank[name]
            if delta != 0:
                rank_changes.append(
                    {
                        "name": name,
                        "legacy_rank": legacy_rank[name],
                        "new_rank": new_rank[name],
                        "delta": delta,
                    }
                )

        rank_changes.sort(key=lambda item: abs(item["delta"]), reverse=True)

        return {
            "legacy_names": legacy_names,
            "new_names": new_names,
            "added": [name for name in new_names if name not in legacy_set],
            "removed": [name for name in legacy_names if name not in new_set],
            "overlap_count": len(legacy_set & new_set),
            "rank_changes_top20": rank_changes[:20],
        }

    @classmethod
    def _role_estimates(cls, us_top100: list[ProfessorProfile]) -> dict:
        counts = Counter()
        examples: dict[str, list[str]] = {role.value: [] for role in ProfessorRole}

        for professor in us_top100:
            classification = classify_professor_role(professor)
            counts[classification.role.value] += 1
            bucket = examples[classification.role.value]
            if len(bucket) < 5:
                bucket.append(professor.author_profile.author.name)

        total = len(us_top100) or 1

        return {
            "counts": dict(counts),
            "percentages": {
                role: round(counts[role] / total * 100, 1)
                for role in counts
            },
            "examples": examples,
            "professor_identification_priority": cls._identification_priority(counts, total),
        }

    @classmethod
    def _identification_priority(cls, counts: Counter, total: int) -> str:
        faculty_pct = counts.get(ProfessorRole.FACULTY.value, 0) / total * 100

        if faculty_pct >= 85:
            return (
                "LOW — {:.0f}% of Top100 classify as faculty from existing "
                "affiliation/homepage signals. Dedicated Professor "
                "Identification is not yet a priority.".format(faculty_pct)
            )

        if faculty_pct >= 70:
            return (
                "MEDIUM — majority appear to be faculty, but {:.0f}% are "
                "industry/unknown/phd. Consider lightweight validation later.".format(
                    100 - faculty_pct
                )
            )

        return (
            "HIGH — fewer than 70% classify as faculty; Professor "
            "Identification would improve recruiter trust."
        )

    @classmethod
    def _affinity_stats(cls, us_top100: list[ProfessorProfile]) -> dict:
        affinities = [p.intelligence.infrastructure_affinity for p in us_top100]

        if not affinities:
            return {}

        sorted_profs = sorted(
            us_top100,
            key=lambda p: p.intelligence.infrastructure_affinity,
            reverse=True,
        )

        return {
            "mean": round(sum(affinities) / len(affinities), 3),
            "median": round(sorted(affinities)[len(affinities) // 2], 3),
            "min": round(min(affinities), 3),
            "max": round(max(affinities), 3),
            "below_30pct_count": sum(1 for value in affinities if value < 0.3),
            "above_50pct_count": sum(1 for value in affinities if value >= 0.5),
            "top5_by_affinity": [
                {
                    "name": p.author_profile.author.name,
                    "affinity": round(p.intelligence.infrastructure_affinity, 3),
                    "primary_infra_venues": p.intelligence.primary_infra_venues,
                }
                for p in sorted_profs[:5]
            ],
            "bottom5_by_affinity": [
                {
                    "name": p.author_profile.author.name,
                    "affinity": round(p.intelligence.infrastructure_affinity, 3),
                    "top_venues": list(p.intelligence.venue_distribution.keys())[:3],
                }
                for p in sorted_profs[-5:]
            ],
        }

    @classmethod
    def _recommendations(cls, role_counts: dict, affinity_stats: dict) -> list[str]:
        recs = [
            "Infrastructure Affinity is now an explicit, exportable ranking feature — "
            "use it to explain why infra-focused professors rank higher.",
            "Research summaries are generated only for the final Top100 via the "
            "pluggable summaries/ pipeline; swap StubLLMProvider when API keys are ready.",
        ]

        below_30 = affinity_stats.get("below_30pct_count", 0)
        if below_30 > 10:
            recs.append(
                f"{below_30} Top100 professors still have <30% infra affinity — "
                "review manually before stakeholder demo."
            )

        recs.append(role_counts.get("professor_identification_priority", ""))
        return [r for r in recs if r]

    @classmethod
    def _render_markdown(cls, report: dict) -> str:
        lines = [
            "# PR11 Validation Report",
            "",
            f"Generated: {report['generated_at']}",
            "",
            "## Summary",
            "",
            f"- US professors in universe: **{report['us_professor_count']}**",
            "",
            "## Top100 Comparison (Legacy vs PR11 Ranking)",
            "",
        ]

        comp = report["top100_comparison"]
        lines.extend([
            f"- Overlap: **{comp['overlap_count']}/100**",
            f"- Added to Top100: **{len(comp['added'])}**",
            f"- Removed from Top100: **{len(comp['removed'])}**",
            "",
        ])

        if comp["added"]:
            lines.append("### Added (infra affinity boost)")
            for name in comp["added"][:15]:
                lines.append(f"- {name}")
            lines.append("")

        if comp["removed"]:
            lines.append("### Removed (lower infra affinity)")
            for name in comp["removed"][:15]:
                lines.append(f"- {name}")
            lines.append("")

        if comp["rank_changes_top20"]:
            lines.append("### Largest rank changes (still in Top100)")
            lines.append("")
            lines.append("| Name | Legacy Rank | New Rank | Δ |")
            lines.append("| --- | --- | --- | --- |")
            for row in comp["rank_changes_top20"][:15]:
                sign = "+" if row["delta"] > 0 else ""
                lines.append(
                    f"| {row['name']} | {row['legacy_rank']} | "
                    f"{row['new_rank']} | {sign}{row['delta']} |"
                )
            lines.append("")

        aff = report.get("infrastructure_affinity", {})
        if aff:
            lines.extend([
                "## Infrastructure Affinity (Top100)",
                "",
                f"- Mean: **{aff['mean']:.0%}**",
                f"- Median: **{aff['median']:.0%}**",
                f"- Range: {aff['min']:.0%} – {aff['max']:.0%}",
                f"- Professors with ≥50% infra papers: **{aff['above_50pct_count']}**",
                f"- Professors with <30% infra papers: **{aff['below_30pct_count']}**",
                "",
            ])

        roles = report.get("professor_role_estimates", {})
        if roles:
            lines.append("## Professor Role Estimates (Heuristic)")
            lines.append("")
            for role, count in roles.get("counts", {}).items():
                pct = roles.get("percentages", {}).get(role, 0)
                lines.append(f"- **{role}**: {count} ({pct}%)")
            lines.append("")
            lines.append(f"**Assessment:** {roles.get('professor_identification_priority', '')}")
            lines.append("")

        lines.extend([
            "## Future Ranking Signals (Not Implemented in PR11)",
            "",
            "| Signal | Data Available | Recruiter Value | Notes |",
            "| --- | --- | --- | --- |",
        ])

        for signal in report.get("future_ranking_signals", []):
            lines.append(
                f"| {signal['signal']} | {signal['data_available']} | "
                f"{signal['recruiter_value']} | {signal['notes']} |"
            )

        lines.extend(["", "## Recommendations", ""])
        for rec in report.get("recommendations", []):
            lines.append(f"- {rec}")

        lines.append("")
        return "\n".join(lines)
