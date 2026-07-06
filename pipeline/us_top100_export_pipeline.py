import csv
import json
from pathlib import Path

from utils.observability import stage_start, stage_end


class USTop100Exporter:
    """
    PR10/PR11: Export the ranked, US-filtered professor list to
    top100_us_professors.csv / .json / TOP100_US.md.

    PR11 adds Infrastructure Affinity and research summary fields.
    """

    def export(
        self,
        us_professors: list,
        output_dir: str = "data/output",
    ) -> list[dict]:
        start = stage_start("Export:us_top100")

        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        rows = [
            self._normalize(professor, rank)
            for rank, professor in enumerate(us_professors, start=1)
        ]

        self._write_csv(rows, out_dir / "top100_us_professors.csv")
        self._write_json(rows, out_dir / "top100_us_professors.json")
        self._write_markdown(rows, out_dir / "TOP100_US.md")

        print(
            f"[PR10 EXPORT] Saved {len(rows)} US professors to {out_dir}",
            flush=True,
        )
        stage_end("Export:us_top100", start)

        return rows

    def _normalize(self, professor, rank: int) -> dict:
        author = professor.author_profile.author
        intelligence = professor.intelligence
        summary = professor.research_summary

        top_venues = sorted(
            intelligence.venue_distribution.items(),
            key=lambda item: item[1],
            reverse=True,
        )
        top_venues = [venue for venue, _ in top_venues[:3]]

        row = {
            "Rank": rank,
            "Name": author.name,
            "University": professor.university or "",
            "Country": professor.country or "",
            "Homepage": professor.homepage or "",
            "Score": round(intelligence.overall_score, 1),
            "Legacy Score": round(intelligence.legacy_overall_score, 1),
            "Infrastructure Affinity": round(intelligence.infrastructure_affinity, 3),
            "Infra Paper Count": intelligence.infra_paper_count,
            "Primary Infra Venues": "; ".join(intelligence.primary_infra_venues),
            "Research Areas": "; ".join(intelligence.research_areas[:5]),
            "Top Venues": "; ".join(top_venues),
            "Source Confidence": self._source_confidence(professor),
        }

        if summary:
            row.update({
                "Research Summary": summary.one_sentence_summary,
                "Primary Research Area": summary.primary_research_area,
                "Secondary Research Area": summary.secondary_research_area,
                "Research Tags": "; ".join(summary.research_tags),
                "Summary Provider": summary.provider,
            })

        return row

    def _source_confidence(self, professor) -> str:
        has_homepage = bool(professor.homepage)
        confidence = professor.affiliation_confidence

        if confidence >= 0.85 and has_homepage:
            return "High"

        if confidence >= 0.6:
            return "Medium"

        return "Low"

    def _write_csv(self, rows: list[dict], path: Path) -> None:
        if not rows:
            path.write_text("")
            return

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    def _write_json(self, rows: list[dict], path: Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2, ensure_ascii=False)

    def _write_markdown(self, rows: list[dict], path: Path) -> None:
        lines = ["# Top 100 US Infrastructure Professors", ""]

        if not rows:
            lines.append("_No US professors found._")
            path.write_text("\n".join(lines) + "\n")
            return

        headers = list(rows[0].keys())
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

        for row in rows:
            values = [str(row[h]).replace("|", "\\|") for h in headers]
            lines.append("| " + " | ".join(values) + " |")

        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
