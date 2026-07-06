import pandas as pd
from utils.observability import stage_start, stage_end


class ProfessorExporter:
    """
    PR4: Export intelligence results to Top_Professors.xlsx
    """

    def __init__(self):
        pass

    def export(self, professors, output_path="Top_Professors.xlsx"):
        """
        professors: list[ProfessorIntelligence]
        """

        start = stage_start("Export:write_excel")

        rows = []

        for p in professors:
            rows.append(self._normalize(p))

        df = pd.DataFrame(rows)

        # 排序（核心交付质量）
        if "Score" in df.columns:
            df = df.sort_values(by="Score", ascending=False)

        df.to_excel(output_path, index=False)

        print(f"[PR4 EXPORT] Saved to {output_path} | total={len(df)}", flush=True)
        stage_end("Export:write_excel", start)

        return df

    def _normalize(self, p):
        """
        把 internal object flatten 成 Excel row
        """

        author = getattr(getattr(p, "author_profile", None), "author", None)
        name = getattr(author, "name", "") if author is not None else ""

        affiliation = getattr(p, "affiliation", None)
        if affiliation is None:
            university = ""
        elif hasattr(affiliation, "university"):
            university = getattr(affiliation, "university", "") or ""
        elif isinstance(affiliation, str):
            university = affiliation
        else:
            university = ""

        intelligence = getattr(p, "intelligence", None)
        publication_count = getattr(intelligence, "publication_count", 0)
        research_areas = getattr(intelligence, "research_areas", [])
        overall_score = getattr(intelligence, "overall_score", 0)

        priority = getattr(intelligence, "priority", None)
        if priority is None:
            priority = self._compute_priority(overall_score)

        hm_match = getattr(intelligence, "hm_score", None)
        if hm_match is None:
            hm_scores = getattr(intelligence, "hm_scores", None)
            if isinstance(hm_scores, dict) and hm_scores:
                hm_match = ", ".join(f"{k}:{v}" for k, v in hm_scores.items())
            else:
                hm_match = ""

        return {
            "Name": name,
            "University": university,
            "Papers": publication_count,
            "Research": self._format_research(research_areas),
            "Score": overall_score,
            "Priority": priority,
            "HM Match": hm_match,
        }

    def _safe_count(self, papers):
        if papers is None:
            return 0
        if isinstance(papers, list):
            return len(papers)
        return papers

    def _format_research(self, areas):
        """
        list[str] → string
        """
        if not areas:
            return ""
        if isinstance(areas, dict):
            # 如果未来变成 dict scoring
            return ", ".join(list(areas.keys())[:5])
        return ", ".join(areas[:5])

    def _compute_priority(self, score):
        """
        PR4: simple deterministic mapping
        """
        try:
            score = float(score)
        except:
            return "P3"

        if score >= 80:
            return "P0"
        elif score >= 60:
            return "P1"
        elif score >= 40:
            return "P2"
        else:
            return "P3"