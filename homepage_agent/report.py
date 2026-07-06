"""PR12 Homepage Agent report generator."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from homepage_agent.models import (
    FetchStatus,
    HomepageGraph,
    NodeCategory,
    PIPELINE_VERSION,
    SCHEMA_VERSION,
)


class HomepageAgentReport:
    """
    Produce a report covering fetch success, navigation discovery rates,
    confidence distribution, and failures requiring manual review.
    """

    REVIEW_CONFIDENCE_THRESHOLD = 0.5

    DISCOVERY_SLOTS = (
        NodeCategory.PEOPLE_PAGE,
        NodeCategory.LAB_PAGE,
        NodeCategory.PROJECTS_PAGE,
    )

    BROKEN_STATUSES = {
        FetchStatus.TIMEOUT,
        FetchStatus.HTTP_ERROR,
        FetchStatus.NETWORK_ERROR,
        FetchStatus.EMPTY_RESPONSE,
    }

    @classmethod
    def generate(cls, graphs: list[HomepageGraph]) -> dict:
        total = len(graphs)
        with_homepage = sum(1 for graph in graphs if graph.homepage_url)
        fetch_success = sum(
            1 for graph in graphs if graph.fetch_status == FetchStatus.SUCCESS
        )
        homepage_coverage = round(with_homepage / total, 3) if total else 0.0

        discovery_counts = cls._discovery_counts(graphs)
        node_type_distribution = cls._node_type_distribution(graphs)
        all_confidences = cls._collect_confidences(graphs)
        manual_review = cls._manual_review_cases(graphs)
        manual_review_reasons = cls._manual_review_reason_counts(manual_review)
        broken_stats = cls._broken_homepage_stats(graphs)
        anchor_texts = cls._common_anchor_texts(graphs)
        link_stats = cls._link_stats(graphs)

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "schema_version": SCHEMA_VERSION,
            "pipeline_version": PIPELINE_VERSION,
            "total_professors": total,
            "professors_processed": total,
            "professors_with_homepage": with_homepage,
            "homepage_coverage": homepage_coverage,
            "fetch_success_count": fetch_success,
            "fetch_success_rate": round(fetch_success / with_homepage, 3)
            if with_homepage
            else 0.0,
            "discovery_counts": discovery_counts,
            "node_type_distribution": node_type_distribution,
            "average_links_per_homepage": link_stats["average"],
            "link_count_stats": link_stats,
            "confidence_distribution": cls._confidence_distribution(all_confidences),
            "most_common_anchor_texts": anchor_texts,
            "manual_review": manual_review,
            "manual_review_reasons": manual_review_reasons,
            "broken_homepage_statistics": broken_stats,
            "provider": graphs[0].provider if graphs else "n/a",
        }

    @classmethod
    def write(
        cls,
        graphs: list[HomepageGraph],
        report: dict | None = None,
        output_dir: str = "data/output",
    ) -> tuple[Path, Path]:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        report = report or cls.generate(graphs)

        json_graph_path = out_dir / "homepage_graph.json"
        md_path = out_dir / "HOMEPAGE_AGENT_REPORT.md"
        json_report_path = out_dir / "HOMEPAGE_AGENT_REPORT.json"

        graph_payload = [graph.to_dict() for graph in graphs]
        with json_graph_path.open("w", encoding="utf-8") as handle:
            json.dump(graph_payload, handle, indent=2, ensure_ascii=False)

        with json_report_path.open("w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, ensure_ascii=False)

        md_path.write_text(cls._render_markdown(report, graphs), encoding="utf-8")

        print(f"[PR12.1] Wrote homepage graphs to {json_graph_path}", flush=True)
        print(f"[PR12.1] Wrote report to {md_path}", flush=True)

        return json_graph_path, md_path

    @classmethod
    def _discovery_counts(cls, graphs: list[HomepageGraph]) -> dict[str, int]:
        return {
            slot.value: sum(1 for graph in graphs if graph.get_node(slot))
            for slot in cls.DISCOVERY_SLOTS
        }

    @classmethod
    def _node_type_distribution(cls, graphs: list[HomepageGraph]) -> dict[str, int]:
        counts: Counter[str] = Counter()
        for graph in graphs:
            for node in graph.graph_nodes:
                if node.node_type != NodeCategory.HOMEPAGE.value:
                    counts[node.node_type] += 1
        return dict(sorted(counts.items(), key=lambda item: item[1], reverse=True))

    @classmethod
    def _link_stats(cls, graphs: list[HomepageGraph]) -> dict:
        successful = [
            graph.link_count
            for graph in graphs
            if graph.fetch_status == FetchStatus.SUCCESS
        ]
        if not successful:
            return {"average": 0.0, "min": 0, "max": 0, "count": 0}

        return {
            "average": round(sum(successful) / len(successful), 1),
            "min": min(successful),
            "max": max(successful),
            "count": len(successful),
        }

    @classmethod
    def _collect_confidences(cls, graphs: list[HomepageGraph]) -> list[float]:
        values: list[float] = []
        for graph in graphs:
            for node in graph.graph_nodes:
                if node.node_type == NodeCategory.HOMEPAGE.value:
                    continue
                values.append(node.confidence_value)
        return values

    @classmethod
    def _common_anchor_texts(cls, graphs: list[HomepageGraph], limit: int = 15) -> list[dict]:
        counter: Counter[str] = Counter()
        for graph in graphs:
            for node in graph.graph_nodes:
                if node.node_type == NodeCategory.HOMEPAGE.value:
                    continue
                if node.anchor_text:
                    counter[node.anchor_text.strip()] += 1

        return [
            {"anchor_text": text, "count": count}
            for text, count in counter.most_common(limit)
        ]

    @classmethod
    def _confidence_distribution(cls, confidences: list[float]) -> dict:
        if not confidences:
            return {}

        buckets = Counter()
        for value in confidences:
            if value >= 0.8:
                buckets["0.80-1.00"] += 1
            elif value >= 0.6:
                buckets["0.60-0.79"] += 1
            elif value >= 0.4:
                buckets["0.40-0.59"] += 1
            else:
                buckets["0.00-0.39"] += 1

        return {
            "count": len(confidences),
            "mean": round(sum(confidences) / len(confidences), 3),
            "median": round(sorted(confidences)[len(confidences) // 2], 3),
            "buckets": dict(buckets),
        }

    @classmethod
    def _broken_homepage_stats(cls, graphs: list[HomepageGraph]) -> dict:
        broken = [
            graph for graph in graphs
            if graph.homepage_url and graph.fetch_status in cls.BROKEN_STATUSES
        ]
        by_status: Counter[str] = Counter()
        for graph in broken:
            by_status[graph.fetch_status.value] += 1

        return {
            "total_broken": len(broken),
            "by_status": dict(by_status),
            "examples": [
                {
                    "professor_name": graph.professor_name,
                    "homepage_url": graph.homepage_url,
                    "status": graph.fetch_status.value,
                    "errors": graph.errors,
                }
                for graph in broken[:10]
            ],
        }

    @classmethod
    def _manual_review_cases(cls, graphs: list[HomepageGraph]) -> list[dict]:
        cases: list[dict] = []

        for graph in graphs:
            reasons: list[str] = []

            if not graph.homepage_url:
                reasons.append("missing_homepage")
            elif graph.fetch_status != FetchStatus.SUCCESS:
                reasons.append(f"fetch_{graph.fetch_status.value}")

            low_confidence = [
                node.node_type
                for node in graph.graph_nodes
                if node.node_type != NodeCategory.HOMEPAGE.value
                and node.confidence_value < cls.REVIEW_CONFIDENCE_THRESHOLD
            ]
            if low_confidence:
                reasons.append(f"low_confidence:{','.join(low_confidence)}")

            if graph.errors:
                reasons.extend(graph.errors)

            if reasons:
                cases.append(
                    {
                        "professor_name": graph.professor_name,
                        "homepage_url": graph.homepage_url,
                        "reasons": reasons,
                    }
                )

        return cases

    @classmethod
    def _manual_review_reason_counts(cls, manual_review: list[dict]) -> dict[str, int]:
        counts: Counter[str] = Counter()
        for case in manual_review:
            for reason in case["reasons"]:
                key = reason.split(":", 1)[0]
                counts[key] += 1
        return dict(counts.most_common())

    @classmethod
    def _render_markdown(cls, report: dict, graphs: list[HomepageGraph]) -> str:
        discovery = report.get("discovery_counts", {})
        confidence = report.get("confidence_distribution", {})
        manual_review = report.get("manual_review", [])
        node_types = report.get("node_type_distribution", {})
        link_stats = report.get("link_count_stats", {})
        anchor_texts = report.get("most_common_anchor_texts", [])
        broken = report.get("broken_homepage_statistics", {})
        review_reasons = report.get("manual_review_reasons", {})

        lines = [
            "# Homepage Intelligence Agent Report (PR12.1)",
            "",
            f"Generated: {report['generated_at']}",
            f"Schema version: **{report.get('schema_version', '1.1')}** | "
            f"Pipeline: **{report.get('pipeline_version', 'PR12.1')}**",
            "",
            "## Summary",
            "",
            f"- Total professors: **{report['total_professors']}**",
            f"- Homepage coverage: **{report['homepage_coverage']:.0%}** "
            f"({report['professors_with_homepage']} with URL)",
            f"- Fetch success rate: **{report['fetch_success_rate']:.0%}** "
            f"({report['fetch_success_count']} succeeded)",
            f"- Average links per homepage: **{report.get('average_links_per_homepage', 0)}**",
            f"- Navigator provider: **{report.get('provider', 'n/a')}**",
            "",
            "## Navigation Discovery",
            "",
            f"- People page discovered: **{discovery.get('people_page', 0)}**",
            f"- Lab page discovered: **{discovery.get('lab_page', 0)}**",
            f"- Projects page discovered: **{discovery.get('projects_page', 0)}**",
            "",
            "## Node Type Distribution",
            "",
        ]

        if node_types:
            for node_type, count in node_types.items():
                lines.append(f"- **{node_type}**: {count}")
            lines.append("")
        else:
            lines.extend(["- No navigation nodes classified.", ""])

        lines.extend([
            "## Link Statistics (successful fetches)",
            "",
            f"- Average links: **{link_stats.get('average', 0)}**",
            f"- Range: {link_stats.get('min', 0)} – {link_stats.get('max', 0)}",
            f"- Homepages analyzed: **{link_stats.get('count', 0)}**",
            "",
            "## Confidence Distribution (non-homepage nodes)",
            "",
        ])

        if confidence:
            lines.extend([
                f"- Nodes classified: **{confidence.get('count', 0)}**",
                f"- Mean confidence: **{confidence.get('mean', 0):.2f}**",
                f"- Median confidence: **{confidence.get('median', 0):.2f}**",
                "",
            ])
            for bucket, count in sorted(confidence.get("buckets", {}).items()):
                lines.append(f"- {bucket}: **{count}**")
            lines.append("")
        else:
            lines.extend(["- No classified navigation nodes.", ""])

        lines.extend(["## Most Common Anchor Texts", ""])
        if anchor_texts:
            for item in anchor_texts[:10]:
                lines.append(f"- \"{item['anchor_text']}\" ({item['count']}×)")
            lines.append("")
        else:
            lines.extend(["- No anchor texts recorded.", ""])

        lines.extend(["## Broken Homepage Statistics", ""])
        lines.append(f"- Total broken: **{broken.get('total_broken', 0)}**")
        for status, count in broken.get("by_status", {}).items():
            lines.append(f"- {status}: **{count}**")
        lines.append("")

        lines.extend(["## Manual Review Reasons", ""])
        if review_reasons:
            for reason, count in review_reasons.items():
                lines.append(f"- **{reason}**: {count}")
            lines.append("")

        lines.extend(["## Failures Requiring Manual Review", ""])
        if manual_review:
            lines.append(f"**{len(manual_review)}** professors flagged:")
            lines.append("")
            for case in manual_review[:25]:
                reason_text = "; ".join(case["reasons"])
                lines.append(
                    f"- **{case['professor_name']}** "
                    f"({case['homepage_url'] or 'no URL'}): {reason_text}"
                )
            if len(manual_review) > 25:
                lines.append(f"- ... and {len(manual_review) - 25} more")
            lines.append("")
        else:
            lines.append("No manual review cases identified.")
            lines.append("")

        lines.extend([
            "## Output",
            "",
            "- `homepage_graph.json` — one navigation graph per professor (schema 1.1)",
            "- Graphs analyze only the professor homepage (no recursive crawling)",
            "",
            f"Total graphs written: **{len(graphs)}**",
            "",
        ])

        return "\n".join(lines)
