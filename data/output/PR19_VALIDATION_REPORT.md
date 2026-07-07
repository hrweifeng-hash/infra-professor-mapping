# PR19 Validation Report — Candidate Page Discovery & Ranking

Generated: 2026-07-07T03:32:01.839010+00:00

Compares PR18 (navigator-based, top-3 candidates) vs PR19 (CandidatePageRanker, top-5 candidates).

---

## Side-by-Side Comparison

| Metric | PR18 | PR19 | Delta |
|--------|------|------|-------|
| Total professors | 100 | 100 | 0 |
| Homepage success | 42 | 69 | +27 |
| Homepage success rate | 42.0% | 69.0% | +0.270 |
| Navigation success | 42 | 69 | +27 |
| Navigation success rate | 42.0% | 69.0% | +0.270 |
| Professors with members | 16 | 16 | 0 |
| Member discovery rate | 16.0% | 16.0% | 0.000 |
| Total current members | 151 | 151 | 0 |
| Total former members | 297 | 297 | 0 |
| Total members | 448 | 448 | 0 |
| Avg members/professor | 1.51 | 1.51 | 0.000 |
| Total pages parsed | 58 | 166 | +108 |
| Total pages successful | 16 | 16 | 0 |
| Avg pages parsed | 0.58 | 1.66 | +1.080 |

### PR19-only Metrics

- Total candidate pages discovered: **288**
- Average candidates per professor: **2.88**
- Candidate page success rate: **9.6%**

### Candidate Source Node Type Distribution (PR19)

- `lab_page`: **24**
- `homepage`: **24**
- `people_page`: **8**
- `research_group_page`: **8**
- `projects_page`: **5**

---

## Precision / Recall Observations

New discoveries (PR18=0 → PR19>0): 0

Member count gains (0 professors improved):

---

## PR18 Fetch Status Distribution

- `page_rejected`: **26**
- `success`: **16**
- `skipped`: **58**

## PR19 Fetch Status Distribution

- `page_rejected`: **53**
- `success`: **16**
- `skipped`: **31**

---

## Methodology Notes

- **PR18** used `ResearchGroupNavigator` (top-3 from LAB_PAGE, RG_PAGE, PEOPLE_PAGE).
- **PR19** uses `CandidatePageGenerator` (ALL HomepageGraph nodes + canonical homepage) → `CandidatePageRanker` (top-5 by explainable rule score).
- Parser, MemberMerger, and downstream extraction logic are **unchanged**.
- Both runs use the same cached HTML (no new network fetches).
