# HANDOFF.md

> Project handoff document. Read before making architectural changes.  
> **Last updated:** 2026-07-13

---

## Current status

**Research group pipeline version:** PR32

| PR | Status | Summary |
|----|--------|---------|
| PR30 | ✅ | Navigation evidence ranking |
| PR31 | ✅ | Identity Foundation — preserves parser candidates |
| PR32 | ✅ | Homepage Recovery + Lab Discovery + validation overhaul |

### PR32 validation (Top-100, PR30 → PR32, matched cohort)

- Navigation success: **42 → 49 (+7)**
- Current members: **980 → 1,259 (+279)**
- Improved / regressed / unchanged: **21 / 4 / 75**
- Homepage recoveries: **27** · Lab links: **49** · Labs discovered: **242**

Details: [PROJECT_STATE.md](PROJECT_STATE.md)

---

## Research group pipeline

```
Conference Papers → Professor Discovery → Homepage Agent
    → Homepage Recovery (PR32) → Lab Discovery (PR32)
    → Navigation Explorer → Member Parser
    → Identity Foundation (PR31) → Person Validator → Research Group Graph
```

| Component | Path |
|-----------|------|
| Orchestration | `research_group_agent/pipeline.py` |
| Homepage Recovery | `homepage_agent/homepage_recovery.py` |
| Lab Discovery | `research_group_agent/lab_discovery.py` |
| Navigation BFS | `research_group_agent/navigation_explorer.py` |
| Identity layer | `identity_foundation/` |
| Validation | `tools/pr32_navigation_validation.py` |

```bash
python3.11 tools/pr32_navigation_validation.py
python3.11 -m pytest tests/test_pr32_navigation.py tests/test_identity_foundation.py -v
```

---

## DBLP ranking pipeline (PR0–PR11)

Separate track for conference-based professor ranking:

```
DBLP XML → Scanner → Conference Pipeline → Professor Registry
    → Intelligence → Ranking → Exporter → Top_Professors.xlsx
```

PR10 adds US filtering + DBLP homepage enrichment. PR11 adds infrastructure affinity scoring. Run with `python main.py`.

Historical PR10/PR11 implementation notes remain in git history; see `pipeline/mapping_pipeline.py` and `validation/pr11_validation_report.py`.

---

## Next tasks

1. **Manual Homepage Override (PR33)** — curated URL corrections
2. **Lab Override (PR34)** — manual lab entry points  
3. **OpenAlex Resolver (PR35)** — external identity enrichment on PR31 candidate graph

**Deprioritize** additional parser heuristics — PR32 showed navigation has higher ROI.

---

## Design principles

- **Navigation before parsing** — reach the right page first.
- **Preserve identity evidence (PR31)** — do not discard parser output silently.
- **Apples-to-apples validation** — matched cohort, consistent metrics.
- **Streaming + modular pipelines** — no monolithic stages.
- **Identity ≠ intelligence** — DBLP metadata separate from computed scores.

---

## Coding principles

Prefer: streaming, typed dataclasses, modular pipelines, deterministic execution, cached HTTP.

Avoid: duplicated state, network calls inside analyzers, business logic in exporters/registry.

---

## Long-term vision

Research Intelligence Platform → professor identity → lab/student discovery → candidate intelligence → recruiting intelligence.

See [ROADMAP.md](ROADMAP.md).
