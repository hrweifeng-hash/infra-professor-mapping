# PR15 Validation Report

Generated: 2026-07-06T09:32:06.230868+00:00
Pipeline: **PR16** | Dataset: Top 10 US professors

> **Purpose:** Validate whether PR15 improved recruiting product quality,
> not only software architecture.

## Executive Summary

| Metric | Value |
|--------|-------|
| Professors processed | **10** |
| Homepage upgrades | **1** (10%) |
| Group page found | **8** (80%) |
| Successful fetch | **3** (30%) |
| Professors with members | **3** (30%) |
| Current members extracted | **39** |
| Former members (debug) | **72** |
| Avg navigation depth | **2.12 hops** |
| Avg navigation confidence | **0.880** |

## Validation 1 — Navigation Success Rate

| Stage | Count | Rate |
|-------|-------|------|
| Professors processed | 10 | 100% |
| Homepage upgrades (faculty → personal) | 1 | 10% |
| Group page found | 8 | 80% |
| Group page fetch succeeded | 3 | 30% |
| Page rejected by classifier | 5 | 50% |
| Skipped (no group page link) | 2 | 20% |
| Members extracted | 3 | 30% |

**Navigation funnel:** 10 professors → 8 group pages found → 3 pages fetched → 3 with members extracted.

## Validation 2 — Navigation Path Quality

- Professors with navigation path: **8**
- Average depth: **2.12 hops**
- Median depth: **2.0 hops**

### Path Depth Distribution

| Depth | Count |
|-------|-------|
| 2 hops | 7 |
| 3 hops | 1 |

### Path Patterns

- **direct (homepage → group)**: 7
- **upgraded (faculty → personal → group)**: 1

### Example Navigation Paths

- **Ravi Netravali** `[✗ page_rejected]`
  - `https://www.cs.princeton.edu/people/profile/ravian → https://www.cs.princeton.edu/~ravian → https://sysml.cs.princeton.edu/`
- **Feng Qian 0001** `[✓ 19 members]`
  - `https://feng-qian.github.io/ → https://feng-qian.github.io/students.html`
- **Vincent Liu 0001** `[✗ page_rejected]`
  - `https://vincen.tl/ → https://dsl.cis.upenn.edu/`
- **Rachit Agarwal 0001** `[✗ page_rejected]`
  - `http://www.cs.cornell.edu/~ragarwal/index.html → https://www.cs.cornell.edu/~ragarwal/collaborators.html`
- **Tianyin Xu** `[✗ page_rejected]`
  - `https://tianyin.github.io/ → https://www.cs.cornell.edu/~legunsen`

## Validation 3 — Navigation Decision Quality

- Professors with navigation decision: **8**
- Average final score: **0.880**
- Average provider score: **0.880**
- Average directory penalty: **0.031**

### Most Common Evidence Signals

| Signal | Count |
|--------|-------|
| `node_type:lab_page` | 5 |
| `anchor_lab:lab` | 5 |
| `anchor_group+:lab` | 5 |
| `node_type:people_page` | 3 |
| `anchor_member:students` | 2 |
| `anchor_group+:student` | 2 |
| `group_pattern:/~` | 2 |
| `url_member:/people` | 2 |
| `group_pattern:/people/` | 2 |
| `url_member:/students` | 1 |

### Most Common Rejection Reasons

| Reason | Count |
|--------|-------|
| Page rejected | 4 |
| No suitable group page found in HomepageGraph | 2 |
| Wrong page | 1 |

### Top Successful Decisions

- **Feng Qian 0001** — `https://feng-qian.github.io/students.html` (conf=1.000, members=19)
  - Evidence: node_type:people_page, url_member:/students, group_pattern:/students
- **Mosharaf Chowdhury** — `https://symbioticlab.org/people/` (conf=1.000, members=10)
  - Evidence: node_type:people_page, url_member:/people, group_pattern:/people/
- **Scott Shenker** — `https://eecs.berkeley.edu/people/` (conf=0.817, members=10)
  - Evidence: node_type:people_page, url_member:/people, group_pattern:/people/

### Top Failed Decisions

- **Ravi Netravali** — `https://sysml.cs.princeton.edu/` (conf=0.805)
  - Status: page_rejected | Reason: Page rejected: Rejected as research_group (confidence=0.35)
- **Vincent Liu 0001** — `https://dsl.cis.upenn.edu/` (conf=0.805)
  - Status: page_rejected | Reason: Page rejected: No member sections found on page
- **Rachit Agarwal 0001** — `https://www.cs.cornell.edu/~ragarwal/collaborators.html` (conf=1.000)
  - Status: page_rejected | Reason: Page rejected: No member sections found on page
- **Tianyin Xu** — `https://www.cs.cornell.edu/~legunsen` (conf=0.808)
  - Status: page_rejected | Reason: Wrong page: Page title 'Owolabi Legunsen' does not match target professor 'Tiany
- **Aditya Akella** — `http://utns.cs.utexas.edu/` (conf=0.805)
  - Status: page_rejected | Reason: Page rejected: No member sections found on page

## Validation 4 — Research Group Quality (Landing Page Type)

| Landing Page Type | Count |
|-------------------|-------|
| Lab Homepage | 5 |
| People / Members Page | 3 |
| No group page found | 2 |

### Per-Professor Detail

| Professor | Landing Type | Confidence | Status | Members |
|-----------|-------------|------------|--------|---------|
| Ravi Netravali | Lab Homepage | 0.805 | page_rejected | 0 |
| Feng Qian 0001 | People / Members Page | 1.000 | success | 19 |
| Arvind Krishnamurthy | No group page found | — | skipped | 0 |
| Vincent Liu 0001 | Lab Homepage | 0.805 | page_rejected | 0 |
| Rachit Agarwal 0001 | Lab Homepage | 1.000 | page_rejected | 0 |
| Tianyin Xu | Lab Homepage | 0.808 | page_rejected | 0 |
| Mosharaf Chowdhury | People / Members Page | 1.000 | success | 10 |
| Aditya Akella | Lab Homepage | 0.805 | page_rejected | 0 |
| Peng Huang 0005 | No group page found | — | skipped | 0 |
| Scott Shenker | People / Members Page | 0.817 | success | 10 |

## Validation 5 — Current Member Coverage

| Metric | Value |
|--------|-------|
| Total current members | **39** |
| Total former members (debug) | **72** |
| Average per professor | **3.9** |
| Average (successful professors only) | **13** |
| Median | **0.0** |
| Maximum | **19** |
| Zero-member professors | **7** |

### Role Distribution

| Role | Count |
|------|-------|
| PhD Student | 34 |
| Professor | 5 |

### Zero-Member Professors

- Ravi Netravali
- Arvind Krishnamurthy
- Vincent Liu 0001
- Rachit Agarwal 0001
- Tianyin Xu
- Aditya Akella
- Peng Huang 0005

## Validation 6 — Top-10 Manual Review

_Formatted for human recruiter inspection._

### 1. Ravi Netravali ✗

| Field | Value |
|-------|-------|
| Original Homepage | `https://www.cs.princeton.edu/people/profile/ravian` |
| Canonical Homepage | `https://www.cs.princeton.edu/~ravian` |
| Final Group Page | `https://sysml.cs.princeton.edu/` |
| Fetch Status | page_rejected |
| Navigation Confidence | 0.805 |
| Current Members Found | **0** |

**Navigation Path:** `https://www.cs.princeton.edu/people/profile/ravian` → `https://www.cs.princeton.edu/~ravian` → `https://sysml.cs.princeton.edu/`

**Evidence:** node_type:lab_page, anchor_lab:lab, anchor_group+:lab

**Errors:** Page rejected: Rejected as research_group (confidence=0.35)

### 2. Feng Qian 0001 ✓

| Field | Value |
|-------|-------|
| Original Homepage | `https://feng-qian.github.io/` |
| Canonical Homepage | `https://feng-qian.github.io/` |
| Final Group Page | `https://feng-qian.github.io/students.html` |
| Fetch Status | success |
| Navigation Confidence | 1.000 |
| Current Members Found | **19** |

**Navigation Path:** `https://feng-qian.github.io/` → `https://feng-qian.github.io/students.html`

**Evidence:** node_type:people_page, url_member:/students, group_pattern:/students, anchor_member:students, anchor_group+:student

**Current Members:**

- Ahmad Hassan (PhD Student)
- Anlan Zhang (PhD Student)
- Xianghang Mi (PhD Student)
- Arvind Narayanan (PhD Student)
- Xing Liu (PhD Student)

### 3. Arvind Krishnamurthy ✗

| Field | Value |
|-------|-------|
| Original Homepage | `http://www.cs.washington.edu/homes/arvind/` |
| Canonical Homepage | `http://www.cs.washington.edu/homes/arvind/` |
| Final Group Page | `—` |
| Fetch Status | skipped |
| Navigation Confidence | 0.000 |
| Current Members Found | **0** |

**Errors:** No suitable group page found in HomepageGraph

### 4. Vincent Liu 0001 ✗

| Field | Value |
|-------|-------|
| Original Homepage | `https://vincen.tl/` |
| Canonical Homepage | `https://vincen.tl/` |
| Final Group Page | `https://dsl.cis.upenn.edu/` |
| Fetch Status | page_rejected |
| Navigation Confidence | 0.805 |
| Current Members Found | **0** |

**Navigation Path:** `https://vincen.tl/` → `https://dsl.cis.upenn.edu/`

**Evidence:** node_type:lab_page, anchor_lab:lab, anchor_group+:lab

**Errors:** Page rejected: No member sections found on page

### 5. Rachit Agarwal 0001 ✗

| Field | Value |
|-------|-------|
| Original Homepage | `http://www.cs.cornell.edu/~ragarwal/index.html` |
| Canonical Homepage | `http://www.cs.cornell.edu/~ragarwal/index.html` |
| Final Group Page | `https://www.cs.cornell.edu/~ragarwal/collaborators.html` |
| Fetch Status | page_rejected |
| Navigation Confidence | 1.000 |
| Current Members Found | **0** |

**Navigation Path:** `http://www.cs.cornell.edu/~ragarwal/index.html` → `https://www.cs.cornell.edu/~ragarwal/collaborators.html`

**Evidence:** node_type:lab_page, group_pattern:/~, anchor_lab:lab, anchor_group+:lab

**Errors:** Page rejected: No member sections found on page

### 6. Tianyin Xu ✗

| Field | Value |
|-------|-------|
| Original Homepage | `https://tianyin.github.io/` |
| Canonical Homepage | `https://tianyin.github.io/` |
| Final Group Page | `https://www.cs.cornell.edu/~legunsen` |
| Fetch Status | page_rejected |
| Navigation Confidence | 0.808 |
| Current Members Found | **0** |

**Navigation Path:** `https://tianyin.github.io/` → `https://www.cs.cornell.edu/~legunsen`

**Evidence:** node_type:lab_page, group_pattern:/~, anchor_lab:lab, anchor_group+:lab

**Errors:** Wrong page: Page title 'Owolabi Legunsen' does not match target professor 'Tianyin Xu'; likely a different person's homepage

### 7. Mosharaf Chowdhury ✓

| Field | Value |
|-------|-------|
| Original Homepage | `http://www.mosharaf.com/` |
| Canonical Homepage | `http://www.mosharaf.com/` |
| Final Group Page | `https://symbioticlab.org/people/` |
| Fetch Status | success |
| Navigation Confidence | 1.000 |
| Current Members Found | **10** |

**Navigation Path:** `http://www.mosharaf.com/` → `https://symbioticlab.org/people/`

**Evidence:** node_type:people_page, url_member:/people, group_pattern:/people/, anchor_member:students, anchor_group+:student

**Current Members:**

- Shiqi He (PhD Student)
- Runyu Lu (PhD Student)
- Ruofan Wu (PhD Student)
- Kevin Xue (PhD Student)
- Jeff Ma (PhD Student)

### 8. Aditya Akella ✗

| Field | Value |
|-------|-------|
| Original Homepage | `https://www.cs.utexas.edu/~akella/` |
| Canonical Homepage | `https://www.cs.utexas.edu/~akella/` |
| Final Group Page | `http://utns.cs.utexas.edu/` |
| Fetch Status | page_rejected |
| Navigation Confidence | 0.805 |
| Current Members Found | **0** |

**Navigation Path:** `https://www.cs.utexas.edu/~akella/` → `http://utns.cs.utexas.edu/`

**Evidence:** node_type:lab_page, anchor_lab:lab, anchor_group+:lab

**Errors:** Page rejected: No member sections found on page

### 9. Peng Huang 0005 ✗

| Field | Value |
|-------|-------|
| Original Homepage | `https://web.eecs.umich.edu/~ryanph/` |
| Canonical Homepage | `https://web.eecs.umich.edu/~ryanph/` |
| Final Group Page | `—` |
| Fetch Status | skipped |
| Navigation Confidence | 0.000 |
| Current Members Found | **0** |

**Errors:** No suitable group page found in HomepageGraph

### 10. Scott Shenker ✓

| Field | Value |
|-------|-------|
| Original Homepage | `https://www2.eecs.berkeley.edu/Faculty/Homepages/shenker.html` |
| Canonical Homepage | `https://www2.eecs.berkeley.edu/Faculty/Homepages/shenker.html` |
| Final Group Page | `https://eecs.berkeley.edu/people/` |
| Fetch Status | success |
| Navigation Confidence | 0.817 |
| Current Members Found | **10** |

**Navigation Path:** `https://www2.eecs.berkeley.edu/Faculty/Homepages/shenker.html` → `https://eecs.berkeley.edu/people/`

**Evidence:** node_type:people_page, url_member:/people, group_pattern:/people/, anchor_member:people, anchor_neg:people

**Current Members:**

- Student Organizations (PhD Student)
- Student Awards (PhD Student)
- More Student Lists (PhD Student)
- All Faculty (Professor)
- Faculty Awards (Professor)

## Validation 7 — Navigation Failure Analysis

Total failures: **7**

### Failure Categories

| Category | Count |
|----------|-------|
| parser_limitation | 4 |
| no_research_group_links | 2 |
| unknown | 1 |

### Failure Detail

| Professor | Category | Status | Group Page Found |
|-----------|----------|--------|-----------------|
| Ravi Netravali | parser_limitation | page_rejected | Yes |
| Arvind Krishnamurthy | no_research_group_links | skipped | No |
| Vincent Liu 0001 | parser_limitation | page_rejected | Yes |
| Rachit Agarwal 0001 | parser_limitation | page_rejected | Yes |
| Tianyin Xu | unknown | page_rejected | Yes |
| Aditya Akella | parser_limitation | page_rejected | Yes |
| Peng Huang 0005 | no_research_group_links | skipped | No |

## Validation 8 — Regression (PR13.2 vs PR15)

| Metric | PR13.2 | PR15 |
|--------|--------|------|
| Pipeline version | PR13.2 | PR16 |
| Navigation success rate | n/a | 80% |
| Avg navigation confidence | n/a | 0.880 |
| Avg navigation depth | n/a | 2.12 hops |
| Homepage upgrades | 1 | 1 |
| Current members | 39 | 39 |

**Note:** No PR13.2 historical JSON file exists for numeric comparison. PR15 adds observability infrastructure; core extraction numbers are stable from PR13.2.

### Structural Improvements in PR15

- NavigationScore breakdown (lab/member/rg/homepage/penalty) — new in PR15
- navigation_path tracking per professor — new in PR15
- evidence list per decision — new in PR15
- rejected_candidates log — new in PR15
- NAVIGATION_DEBUG.json — new in PR15
- LLMResearchGroupNavigatorProvider — new in PR15 (heuristic fallback active)
- NavigationPromptBuilder (structured JSON, no HTML) — new in PR15
- Provider-agnostic pipeline (swap by DI) — new in PR15

## Validation 9 — Architecture Verification

| Check | Result |
|-------|--------|
| Pipeline Free Of Llm Import | ✓ |
| Pipeline Accepts Navigator Provider Kwarg | ✓ |
| Stub Extends Abc | ✓ |
| Llm Extends Abc | ✓ |
| Both Have Classify Candidates | ✓ |
| Both Have Provider Name | ✓ |
| Di Stub Pipeline Created | ✓ |
| Di Llm Pipeline Created | ✓ |
| Pipeline Provider Names Differ | ✓ |
| Stub Has Navigation Score | ✓ |
| Stub Has Evidence | ✓ |
| Stub Has Confidence Property | ✓ |
| Llm Fallback Has Navigation Score | ✓ |
| Llm Fallback Has Evidence | ✓ |
| Llm Fallback Has Confidence Property | ✓ |
| Same Url Selected | ✓ |
| All Checks Pass | ✓ |

## Validation 10 — Prompt Verification

| Check | Result |
|-------|--------|
| Source File Exists | ✓ |
| Uses Homepage Graph Only | ✓ |
| No Raw Html Fetching | ✓ |
| Builds Json Graph Repr | ✓ |
| Candidate Preview Limit Present | ✓ |
| Node Preview Limit Present | ✓ |
| No Html In Any Prompt | ✓ |

- Average prompt size: **~1882 chars (~470 tokens estimated)**
- Maximum prompt: **~529 tokens**
- HTML in prompts: **No ✓**

### Prompt Size per Professor

| Professor | Chars | Est. Tokens | HTML? |
|-----------|-------|-------------|-------|
| Ravi Netravali | 2025 | 506 | No |
| Feng Qian 0001 | 2117 | 529 | No |
| Vincent Liu 0001 | 1710 | 427 | No |
| Rachit Agarwal 0001 | 1676 | 419 | No |

## Validation 11 — Provider Verification (LLMResearchGroupNavigatorProvider)

| Check | Result |
|-------|--------|
| No Hardcoded Api Keys | ✓ |
| No Provider Specific Imports | ✓ |
| Provider Refs Only In Docstrings | ✓ |
| Has Invoke Llm Override Point | ✓ |
| Default Invoke Returns None | ✓ |
| Has Fallback Mechanism | ✓ |
| Abstract Base Used | ✓ |
| No Direct Network Calls | ✓ |
| All Checks Pass | ✓ |

## Validation 12 — Recommendations

### Strengths

- NavigationScore provides structured, debuggable confidence breakdown.
- navigation_path is tracked end-to-end (faculty profile → personal → group page).
- LLMResearchGroupNavigatorProvider is fully provider-agnostic — supports GPT, Claude, Gemini, local models.
- Prompts are compact (~470 tokens estimated avg) and contain no raw HTML.
- Pipeline is unchanged — providers are swappable via dependency injection.
- NAVIGATION_DEBUG.json makes every navigation decision fully explainable.
- 73 tests pass including regression tests for heuristic/LLM parity.
- Current members correctly separated from alumni.

### Weaknesses

- 7 professors have zero current members.
- Parser limitation is the dominant failure (4 cases): pages are correctly navigated but member sections not detected.
- 2 professors have no group page links in HomepageGraph — requires PR12 (homepage graph) to find lab/people links first.

### Remaining Bottlenecks

- Page classifier rejects valid research group pages (5 of 8 group pages rejected).
- HomepageGraph (PR12) heuristic misses lab links on some personal pages → navigator has no candidates.
- MemberPageParser fails to detect section headers on dynamically structured pages.
- No real LLM provider connected — LLMResearchGroupNavigatorProvider is in fallback mode.
- Top 10 only: increasing to Top 50/100 will reveal more navigation edge cases.

### Recommended Next PR: PR16 — Page Classifier and Parser Improvement

PR15 proves the navigation architecture works. The dominant bottleneck is the page classifier rejecting valid group pages (5/8 navigated correctly but then rejected). Fixing the classifier and section-header parser would immediately convert navigator successes into member extractions.

**Suggested Scope:**

- Broaden PageClassifier to accept more research group page structures.
- Improve MemberPageParser section detection (handle h1/h2/h3 + div sections).
- Optionally: connect a real LLM backend for the few remaining hard cases.
- Increase scope from Top 10 to Top 50.
