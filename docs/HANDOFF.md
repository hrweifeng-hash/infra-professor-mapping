# HANDOFF.md

> Project handoff document.
>
> Read this file before making architectural changes.
> This document reflects the current project status.

---

# Current Status

Current Branch

PR11 — Infrastructure Affinity Ranking + Research Summaries + Validation Report

Previous Milestones

✅ PR1
DBLP Streaming Scanner

✅ PR2
Conference Pipeline Refactor

✅ PR3
Professor Registry

✅ PR4
Ranking & Excel Export

✅ PR5
Architecture Cleanup

✅ PR6
Intelligence Pipeline Refactor

✅ PR7
Demo Release

Current achievements:

- Streaming DBLP parser
- Conference pipeline
- Professor registry
- Intelligence pipeline
- Ranking engine
- Excel exporter
- Top Professor generation
- Pipeline observability
- Dataset normalization

Current dataset

DBLP

Years:

2021–2025

Conferences:

OSDI
SOSP
NSDI
SIGCOMM
VLDB
SIGMOD
FAST
ATC
EuroSys
SoCC

Output:

Top_Professors.xlsx

---

# Current Architecture

```
DBLP XML
      │
      ▼
Streaming Scanner
      │
      ▼
Dataset Pipeline
      │
      ▼
Conference Pipeline
      │
      ▼
Author Profile Builder
      │
      ▼
Professor Profile Builder
      │
      ▼
Professor Registry
      │
      ▼
Intelligence Pipeline
      │
      ▼
Ranking Engine
      │
      ▼
Exporter
```

---

# Current Data Model

Author

↓

AuthorProfile

↓

ProfessorProfile

↓

ProfessorIntelligence

ProfessorIntelligence is the single source of truth for all derived information.

ProfessorProfile stores only raw data.

---

# Completed Features

✔ Streaming XML parsing

✔ Incremental conference pipeline

✔ Professor deduplication

✔ Publication aggregation

✔ Research area inference

✔ Venue statistics

✔ Publication statistics

✔ Ranking

✔ Excel export

✔ Progress logging

✔ Validation tool

---

# Known Limitations

Current ranking is publication-driven.

Missing information:

- Faculty profile
- Department
- Lab
- Google Scholar (intentionally out of scope, see PR10 TODOs)
- Semantic Scholar

University, Country, Homepage, and Affiliation Confidence are now resolved
by PR10 (AffiliationResolver / DBLPWWWEnrichmentBuilder), scoped to US
institutions only — see "PR10 — US Professor Filtering" below.

Research areas rely only on publication metadata.

---

# PR10 — US Professor Filtering + Homepage Enrichment + Top100 Export

Status: DONE

Adds two additive pipeline stages (see `pipeline/mapping_pipeline.py`)
without touching existing paper parsing or `RankingEngine`:

1. **`DBLPWWWEnrichmentBuilder`** (runs right after `ProfessorRegistry.build()`,
   before intelligence/ranking) — a second, local-file-only streaming pass
   over the already-downloaded `data/raw/dblp.xml.gz`, reading DBLP's
   `<www key="homepages/...">` person records (`crawler/dblp_www_scanner.py`,
   `parser/www_record_parser.py`). No network calls, no full 4.1M-person
   index — only records matching our known professor names are ever
   materialized. Populates `ProfessorProfile.homepage` / `.affiliation`
   when they're still empty.

   **Important finding**: DBLP's bulk XML dump never puts a `pid` attribute
   on `<author>` elements inside publication records (verified empirically:
   0 of ~33.7M author-tag occurrences). This means `Author.pid` is always
   `None` today, and the join against `<www>` records is keyed by the
   case-folded author name string instead — which DBLP itself uses as the
   join key between publication authors and person records. Real match
   rate on our professor universe: 99.34%. See `resources/dblp_url_denylist.json`
   for how a real personal homepage is distinguished from the many
   aggregator/profile links (ORCID, Google Scholar, ACM DL, Wikidata, ...)
   also present in `<www>` records.

2. **`AffiliationResolver`** + **`USUniversityMatcher`** (run right after
   `RankingEngine.rank()`) — resolves `professor.affiliation` (raw DBLP
   text) into `university` / `country` / `is_us` / `affiliation_confidence`
   on `ProfessorProfile`, matched against `resources/us_universities.json`.
   No Geo API. Independent of ranking — `RankingEngine` and
   `ProfessorIntelligence` are never modified by this stage.

3. **`HomepageResolver`** — deliberately minimal (DBLP-only), applied only
   to the final US Top100 slice.

4. **`USTop100Exporter`** (`pipeline/us_top100_export_pipeline.py`) — writes
   `data/output/top100_us_professors.csv`, `.json`, and `TOP100_US.md`.
   Does not touch `pipeline/export_pipeline.py` — `Top_Professors.xlsx`
   still works exactly as before.

### Results from the full run (`python main.py --no-enrich`, all configured
conferences, years 2021–2025)

```
Total Professors (post-dedup)  : 79,307
Homepage Available (DBLP-only) : 8,605   (10.9%)
Affiliation Available          : 15,792  (19.9%)
No <www> record at all         : 986     (1.2%)
Unmatched affiliation strings  : 5,960 distinct (see unmatched_affiliations.txt —
                                  dominated by non-US institutions: Peking,
                                  Tsinghua, ETH Zurich, NUS, plus a few
                                  industry labs like Google/Microsoft Research
                                  that are correctly excluded since this PR
                                  only matches US universities)
US professors identified       : 4,570
Top100 exported                : 100 (all "High"/"Medium" Source Confidence)
```

Two real matcher bugs were found and fixed while validating this run (both
now covered by regression tests in `tests/test_us_university_matcher.py`):
bare two-letter state-code fragments (e.g. "WA" from "Redmond, WA, USA")
were substring-matching into unrelated long university names ("george
**wa**shington university"), and comma-containing university names (e.g.
"University of California, San Diego") were getting fragmented by naive
comma-splitting and false-matching a different university ("San Diego
State University"). Fix: `USUniversityMatcher`'s substring tier now only
checks canonical/alias-in-full-string, one direction, never
fragment-vs-fragment.

## Maintaining `resources/us_universities.json`

This list (~150 major US CS/systems research universities, each entry
`{"canonical", "aliases", "country"}`) will not have full coverage on day
one. After every pipeline run, `AffiliationResolver.write_unmatched_report()`
writes every raw affiliation string that failed to match to
`data/output/unmatched_affiliations.txt` (most-common first). To extend
coverage:

1. Run the pipeline (`python main.py`).
2. Open `data/output/unmatched_affiliations.txt`.
3. For each real US university that appears, add an entry (or an alias to
   an existing entry) to `resources/us_universities.json`.
4. **Keep entries sorted alphabetically by `canonical`** — this keeps diffs
   small and reviewable. `USUniversityMatcher` does not care about order,
   this is purely for maintainability.
5. Re-run the pipeline to confirm the new entries resolve.

Matching heuristics (exact / alias / substring, with confidence tiers) live
entirely in `identity/us_university_matcher.py`, not in the JSON — the
resource file should stay plain data.

---

# PR11 — Infrastructure Affinity + Research Summaries + Validation

Status: DONE

Improves recruiter-facing deliverable quality without adding external data
sources.

### 1. Infrastructure Affinity Score

`intelligence/infrastructure_affinity.py` computes an interpretable 0–1
affinity from venue distribution. Core infra venues: OSDI, SOSP, NSDI, FAST,
ATC, EuroSys, ASPLOS, SIGCOMM, SoCC, Middleware. ML conferences are **not
removed** — they simply do not contribute to affinity.

Integrated into `RankingEngine` (30% of `overall_score`):

| Component | Weight |
| --- | --- |
| Publication volume | 30% |
| Venue quality | 25% |
| Research breadth | 15% |
| Infrastructure Affinity | 30% |

`legacy_overall_score` preserves the pre-PR11 formula for validation
comparisons. Exported on every Top100 row as `Infrastructure Affinity`,
`Infra Paper Count`, `Primary Infra Venues`.

### 2. Research Summaries (Top100 only)

Modular pipeline under `summaries/`:

```
ResearchSummaryPipeline
    └── LLMProvider (abstract)
            └── StubLLMProvider (heuristic, no API)
```

`summaries/prompt_builder.py` builds the recruiter prompt from recent paper
titles + venues + research areas. Swap in OpenAI/Claude providers later —
no integration in this PR.

Populates `ProfessorProfile.research_summary` for the final US Top100 slice
only. Exported fields: Research Summary, Primary/Secondary Research Area,
Research Tags.

### 3. Validation Report

`validation/pr11_validation_report.py` writes:

- `data/output/PR11_VALIDATION_REPORT.md`
- `data/output/PR11_VALIDATION_REPORT.json`

Contents: legacy vs PR11 Top100 comparison, affinity distribution, heuristic
professor role estimates (faculty / industry / phd / unknown), future ranking
signal review, recommendations.

`validation/professor_identification.py` provides role heuristics. On the
full Top100 run, expect ~90%+ faculty — dedicated Professor Identification
is **not yet a priority** (documented in report).

Standalone fixture report: `python tools/pr11_validation_report.py`

### 4. Future Ranking Signals (documented, not implemented)

See validation report table: recent activity, venue diversity, long-term
impact, productivity trend.

---

# Next Task

PR11 deliverable polish (post full pipeline run):

- **Re-run `python main.py --no-enrich`** and review
  `data/output/PR11_VALIDATION_REPORT.md` — confirm ML-heavy professors
  drop out of Top100 and infra researchers rise.
- **Swap `StubLLMProvider` for a real LLM** when API keys are available
  (prompt interface is ready in `summaries/prompt_builder.py`).
- **Manual Top100 sanity check** before stakeholder demo.

Remaining future-PR TODOs (unchanged from PR10):

- **Fix `Author.pid`.** It is never populated from the bulk dataset (see
  PR10 finding above), which means `builders/professor_enrichment_builder.py`
  (PR8's per-author network enrichment, keyed by pid) never actually fires —
  every professor hits `skipped_no_pid`. It's effectively dead code today.
  A real fix would derive pid during the `<www>` join (the `key="homepages/X/Y"`
  attribute *does* carry it) and backfill `Author.pid`.
- **OpenAlex integration** — `HomepageResolver` is deliberately DBLP-only
  right now. Before adding an OpenAlex source, validate what fields
  OpenAlex's API actually returns for our professor set (do not assume
  `homepage` exists).
- **University faculty-directory fallback** — recover homepage via
  "Professor Name + University" only when DBLP/OpenAlex have nothing,
  using only official `.edu` domains.
- **Google Scholar** — intentionally out of scope. No official API,
  unstable, anti-bot restrictions, poor reproducibility.
- Encoding/mojibake fix for non-ASCII author names causing a handful of
  `<www>` join misses (see PR10 finding — low priority, ~0.1% of names).

---

# Design Principles

Never mix identity information with intelligence.

Identity represents real-world metadata.

Intelligence represents computed analytics.

Suggested new model:

ProfessorProfile
    │
    ├── AuthorProfile
    ├── ProfessorIdentity
    └── ProfessorIntelligence

---

# Coding Principles

Prefer

✔ Streaming

✔ Typed dataclasses

✔ Modular pipelines

✔ Deterministic execution

✔ Cached identity lookup

Avoid

✘ Duplicated state

✘ Network calls inside analyzers

✘ Business logic inside exporter

✘ Business logic inside registry

---

# Review Checklist

□ No duplicated identity fields

□ Identity pipeline separated from intelligence

□ Export uses identity model

□ Ranking independent from identity

□ No extra DBLP scan

□ Pipeline remains streaming

□ Full pipeline passes

---

# Long-Term Vision

Research Intelligence Platform

Roadmap

Professor Intelligence

↓

Professor Identity

↓

Lab Discovery

↓

Student Discovery

↓

Candidate Intelligence

↓

Recruiting Intelligence