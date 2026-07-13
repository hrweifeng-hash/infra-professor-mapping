# PR32 — Homepage Recovery & Lab Discovery

PR32 improves **navigation** to reach the correct research group pages. It does not modify the parser, validator, or Identity Foundation (PR31).

**Status:** ✅ Complete (2026-07-13)

---

## Problem

Two navigation gaps cause recall loss:

1. **Homepage Recovery** — stored professor URLs often point at stale pages ("I moved to …", meta refresh, redirects, canonical links).
2. **Lab Discovery** — modern faculty sites route through research labs before team/people pages.

---

## Pipeline position

```
Conference Papers
        ↓
Professor Discovery
        ↓
Homepage Agent
        ↓
Homepage Recovery (PR32)     ← this PR
        ↓
Lab Discovery (PR32)         ← this PR
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

---

## Navigation graph (detail)

```
Professor Homepage
       ↓
Homepage Recovery          ← HTTP redirect, meta refresh, canonical, moved-page
       ↓
Lab Discovery              ← anchor text, nav menus, URL signals
       ↓
Lab Homepage (LAB_HOME)    ← new page type, high ranking
       ↓
Lab Navigation Expansion   ← NavigationExplorer BFS from each lab
       ↓
Team / People / Members
       ↓
Member Extraction          ← unchanged parser + validator
```

---

## Modules

### HomepageRecovery (`homepage_agent/homepage_recovery.py`)

| Pattern | Detection | Confidence |
|---------|-----------|------------|
| HTTP redirect | `final_url ≠ original_url` from fetcher | 0.95 |
| Meta refresh | `<meta http-equiv="refresh" …>` | 0.92 |
| Canonical | `<link rel="canonical" …>` | 0.88 |
| Moved page | Text patterns + destination links | 0.85 |

When recovery succeeds, the pipeline updates the canonical homepage and re-fetches before lab discovery.

### LabDiscovery (`research_group_agent/lab_discovery.py`)

Discovers research lab homepages from professor homepage HTML via anchor text, navigation menus, and URL signals. Returns `CandidatePage` objects with `page_type=lab_home`.

### Lab Navigation Expansion

Runs a second `NavigationExplorer` BFS pass from each discovered lab URL. Team/people pages merge into the candidate pool before ranking.

### Production fetcher (`homepage_agent/fetcher.py`)

- Connect timeout 5s, read timeout 10s
- Max 5 redirects; timeouts fail fast without blocking the pipeline
- `FetchStats` for validation observability

---

## Validated results (Top-100, PR30 → PR32)

**Methodology:** Matched cohort (N=100 professors by name). Baseline: `pr30_research_group_graph.json`. Navigation success: `fetch_status == "success" AND member_count > 0`.

### Recall

| Metric | PR30 | PR32 | Delta |
|--------|-----:|-----:|------:|
| Navigation success | 42 | 49 | +7 |
| Current members | 980 | 1,259 | +279 |

| Outcome | Count |
|---------|------:|
| Improved professors | 21 |
| Regressed professors | 4 |
| Unchanged professors | 75 |

### Homepage recovery

| Metric | Count |
|--------|------:|
| Homepages recovered | 27 |

### Lab discovery

| Metric | Count |
|--------|------:|
| Professors with lab links | 49 |
| Labs discovered | 242 |
| Team pages discovered | 2,619 |

### Fetch summary

Full validation runs print a networking summary (total requests, timeouts, redirect limits, latency percentiles, slow requests >5s). Use a full run (not `--skip-pipeline`) to capture live stats.

---

## Validation

```bash
python3.11 tools/pr32_navigation_validation.py
python3.11 tools/pr32_navigation_validation.py --skip-pipeline
```

**Outputs** (local `data/output/`, gitignored):

- `PR32_NAVIGATION_VALIDATION.{json,md,html}`
- `PR32_PROFESSOR_COMPARISON.json` — per-professor table sorted by |delta|
- `pr32_research_group_graph.json`

**Baseline:** `pr30_research_group_graph.json` (PR31 did not change navigation).

---

## Constraints

- No parser changes in PR32
- No validator changes
- No Identity Foundation changes
- Reuses `NavigationExplorer` for lab expansion

---

## Tests

```bash
python3.11 -m pytest tests/test_pr32_navigation.py tests/test_pr32_validation_tooling.py -v
```
