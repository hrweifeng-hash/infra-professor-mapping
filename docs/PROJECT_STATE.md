# Project State

**Last updated:** 2026-07-13  
**Research group pipeline version:** PR32

---

## Goal

Build an academic intelligence pipeline that discovers infrastructure / systems professors from conference data, navigates their homepages and lab sites, extracts research group members, and produces structured graphs for recruiting intelligence.

---

## Current research group pipeline

```
Conference Papers
        ↓
Professor Discovery
        ↓
Homepage Agent
        ↓
Homepage Recovery (PR32)
        ↓
Lab Discovery (PR32)
        ↓
Navigation Explorer
        ↓
Member Parser
        ↓
Identity Foundation (PR31)
        ↓
Person Validator
        ↓
Research Group Graph
```

| Stage | Module | PR |
|-------|--------|-----|
| Homepage fetch + graph | `homepage_agent/` | PR12–PR22 |
| Canonical homepage resolution | `homepage_agent/homepage_resolver.py` | PR15 |
| **Homepage recovery** | `homepage_agent/homepage_recovery.py` | **PR32** |
| **Lab discovery** | `research_group_agent/lab_discovery.py` | **PR32** |
| Multi-level BFS | `research_group_agent/navigation_explorer.py` | M5-PR1 |
| Member parsing | `research_group_agent/parser.py` | PR17–PR24 |
| **Identity preservation** | `identity_foundation/` | **PR31** |
| Person validation | `research_group_agent/person_validator.py` | PR16 |
| Graph export | `research_group_agent/graph_builder.py` | PR13+ |

---

## Completed milestones

| PR | Status | Summary |
|----|--------|---------|
| PR31 | ✅ | Identity Foundation — preserves all parser candidates for future OpenAlex / DBLP / Scholar resolution |
| PR32 | ✅ | Homepage Recovery + Lab Discovery + validation overhaul + production fetcher hardening |

Earlier navigation/parser PRs (PR19–PR30) remain in place; PR31 did not change navigation; PR32 adds recovery and lab routing only.

---

## PR32 validation results (apples-to-apples)

**Methodology:** Compare `pr30_research_group_graph.json` vs `pr32_research_group_graph.json` on the **same 100 professors** (matched by `professor_name`). PR30 is the pre-PR32 baseline because PR31 only added the identity layer.

**Navigation success definition (both sides):** `fetch_status == "success" AND member_count > 0`

### Recall (matched cohort, N=100)

| Metric | PR30 | PR32 | Delta |
|--------|-----:|-----:|------:|
| Navigation success | 42 | 49 | **+7** |
| Current members | 980 | 1,259 | **+279** |

| Outcome | Count |
|---------|------:|
| Improved professors | 21 |
| Regressed professors | 4 |
| Unchanged professors | 75 |

### Homepage recovery

| Metric | Count |
|--------|------:|
| Homepages recovered | 27 |
| HTTP redirect | 18 |
| Meta refresh | 4 |
| Canonical | 3 |
| Moved page | 2 |

### Lab discovery

| Metric | Count |
|--------|------:|
| Professors with lab links | 49 |
| Labs discovered | 242 |
| Lab pages visited | 3,665 |
| Team pages discovered | 2,619 |

### Fetch summary (production fetcher, PR32 validation run)

The HTTP layer uses separate **connect (5s) / read (10s)** timeouts, a **5-redirect** cap, graceful timeout handling, and slow-request warnings (>5s). During a full validation run, `FetchStats` reports:

- Total HTTP requests, successes, timeouts, network errors, redirect-limit exceeded
- Average and 95th-percentile latency
- Slow request count (>5s)

Re-run without `--skip-pipeline` to capture live fetch stats at the end of the run:

```bash
python3.11 tools/pr32_navigation_validation.py
```

Reports are written locally to `data/output/` (gitignored): `PR32_NAVIGATION_VALIDATION.{json,md,html}`, `PR32_PROFESSOR_COMPARISON.json`.

---

## Major conclusions (2026-07)

1. **Parser improvements have reached diminishing returns** — further layout/parser tweaks yield small gains relative to engineering cost.
2. **Homepage Recovery and Lab Discovery provide significantly higher ROI** — +279 members and +7 navigation successes on the Top-100 cohort from navigation alone.
3. **Identity preservation is in place (PR31)** — rejected parser candidates are retained for downstream resolver work.
4. **Future work should prioritize navigation overrides and identity resolution**, not more parser heuristics.

---

## Next PRs (planned)

| Priority | PR | Focus |
|----------|-----|-------|
| 1 | Manual Homepage Override | Curated homepage corrections for known-bad URLs |
| 2 | Lab Override | Manual lab URL hints where discovery misses |
| 3 | OpenAlex Resolver | Identity enrichment via OpenAlex API |

---

## Running validation

```bash
# Full pipeline + report (slow — fetches live pages)
python3.11 tools/pr32_navigation_validation.py

# Reuse cached pr32 graphs, regenerate comparison only
python3.11 tools/pr32_navigation_validation.py --skip-pipeline

# PR31 identity layer checks
python3.11 tools/identity_foundation_validation.py
```

---

## DBLP ranking pipeline (separate track)

The original conference → professor ranking pipeline (PR0–PR11) remains available via `python main.py`. See [HANDOFF.md](HANDOFF.md) for DBLP-specific architecture and status.
