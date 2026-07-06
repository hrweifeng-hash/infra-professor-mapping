# Failed Research Group Pages — Diagnostics Report

Generated: 2026-07-06T09:31:59.365259+00:00
Pipeline: **PR15** | Inspector: **PR15.5**

> **Purpose:** Explain every failed research group page to guide future
> parser and classifier improvements. Do not guess — use real failures.

## Executive Summary

| Metric | Value |
|--------|-------|
| Total professors analyzed | **10** |
| Succeeded with members | **3** (30%) |
| Failed (0 members) | **7** (70%) |
| Post-navigation failures | **5** (62%) |
| Wrong page navigated | **1** |
| Records with cached HTML | **5** |

## Failure Distribution

| Category | Count | Share |
|----------|-------|-------|
| Section Detection Failure | 3 | 43% |
| Unsupported HTML Structure | 1 | 14% |
| No Homepage | 1 | 14% |
| Dynamic HTML | 1 | 14% |
| Fetch Failure | 1 | 14% |

## Top Rejection Reasons

| Reason | Count |
|--------|-------|
| Page rejected | 4 |
| No suitable group page found in HomepageGraph | 2 |
| Wrong page | 1 |

## Most Common Section Headings (from failed pages)

_These headings were found on failed pages. Member-adjacent headings that_
_don't match CURRENT_SECTION_KEYWORDS are the primary fix candidates._

| Heading | Count |
|---------|-------|
| `About Us` | 2 |
| `Distributed Systems Laboratory` | 2 |
| `SAIL@Princeton` | 1 |
| `Directions` | 1 |
| `News` | 1 |
| `Featured projects` | 1 |
| `Featured publications` | 1 |

## Unmatched Member Headings (Near-Miss Keywords)

_These headings contain member-related words but are NOT in CURRENT_SECTION_KEYWORDS._
_Adding them to precision_constants.py would immediately fix those pages._

| Heading (as found on page) | Count | Suggested Keyword to Add |
|----------------------------|-------|--------------------------|
| `Distributed Systems Laboratory` | 2 | `"distributed systems laboratory"` |

## Unsupported Layout Patterns

| Pattern | Count |
|---------|-------|
| No Headings Found | 2 |
| Css Card Grid | 1 |
| Dynamic Spa | 1 |
| Wrong Page Navigated | 1 |

## PageClassifier Type Distribution (failed pages)

| Page Type | Count |
|-----------|-------|
| `research_group` | 4 |
| `student_page` | 1 |

## Per-Professor Failure Details

_Each entry below is a fully diagnosed failure with root cause and suggested fix._

### 1. Ravi Netravali ✗

| Field | Value |
|-------|-------|
| **Failure Category** | **Unsupported HTML Structure** |
| Professor | Ravi Netravali |
| Original Homepage | `https://www.cs.princeton.edu/people/profile/ravian` |
| Canonical Homepage | `https://www.cs.princeton.edu/~ravian` |
| Research Group URL | `https://sysml.cs.princeton.edu/` |
| Fetch Status | `page_rejected` |
| Classifier Page Type | `research_group` |
| Classifier Confidence | 0.350 |
| Classifier Acceptable | No |
| Parser: Sections Detected | 3 |
| Parser: Member Sections | 0 |
| Parser: Entries Parsed | 0 |
| Wrong Page Detected | No |
| Dynamic / SPA | No |
| SPA Frameworks Detected | — |
| HTML Size | 31,283 bytes |
| Visible Text Ratio | 8.5% |
| Member Keywords in HTML | Yes |
| Plain-Text Section Headers | No |
| Plain-Text Patterns Found | — |
| Card/Grid Pattern | Yes |

**Navigation Path:** `https://www.cs.princeton.edu/people/profile/ravian` → `https://www.cs.princeton.edu/~ravian` → `https://sysml.cs.princeton.edu/`

**Navigation Score:**

| Component | Score |
|-----------|-------|
| Lab Score | 0.805 |
| Member Score | 0.000 |
| Research Group Score | 0.000 |
| Homepage Score | 0.234 |
| Directory Penalty | 0.000 |
| Provider Score | 0.805 |
| Final Score | 0.805 |

**Navigation Evidence:** `node_type:lab_page`, `anchor_lab:lab`, `anchor_group+:lab`

**All Headings Found:** `SAIL@Princeton`, `About Us`, `Directions`

**Parser-Detected Member Sections:** _none_

**Rejected Reason:** `Page rejected: Rejected as research_group (confidence=0.35)`

**Suggested Fix:**

> Page lists members in a CSS grid/card layout (card pattern detected, visible text ratio=8.5%). The parser relies on h1–h4 headings before member lists. Fix: add a profile-card container parser to MemberPageParser.

---

### 2. Arvind Krishnamurthy ✗

| Field | Value |
|-------|-------|
| **Failure Category** | **No Homepage** |
| Professor | Arvind Krishnamurthy |
| Original Homepage | `http://www.cs.washington.edu/homes/arvind/` |
| Canonical Homepage | `http://www.cs.washington.edu/homes/arvind/` |
| Research Group URL | — |
| Fetch Status | `skipped` |

**Parser-Detected Member Sections:** _none_

**Rejected Reason:** `No suitable group page found in HomepageGraph`

**Suggested Fix:**

> HomepageGraph only contains: [homepage, publications_page, teaching_page]. No lab/group/people page link was discovered. Possible causes: (1) homepage uses Google Sites / JavaScript navigation that the static HP agent cannot crawl; (2) the lab page link text does not match GROUP_ANCHOR_POSITIVE keywords; (3) the professor lists students only on their personal page without a dedicated lab URL. Fix: expand HomepagePipeline anchor scoring for Google Sites or add a second navigation hop.

---

### 3. Vincent Liu 0001 ✗

| Field | Value |
|-------|-------|
| **Failure Category** | **Dynamic HTML** |
| Professor | Vincent Liu 0001 |
| Original Homepage | `https://vincen.tl/` |
| Canonical Homepage | `https://vincen.tl/` |
| Research Group URL | `https://dsl.cis.upenn.edu/` |
| Fetch Status | `page_rejected` |
| Classifier Page Type | `research_group` |
| Classifier Confidence | 0.250 |
| Classifier Acceptable | No |
| Parser: Sections Detected | 2 |
| Parser: Member Sections | 0 |
| Parser: Entries Parsed | 0 |
| Wrong Page Detected | No |
| Dynamic / SPA | Yes |
| SPA Frameworks Detected | React |
| HTML Size | 35,189 bytes |
| Visible Text Ratio | 2.2% |
| Member Keywords in HTML | Yes |
| Plain-Text Section Headers | No |
| Plain-Text Patterns Found | — |
| Card/Grid Pattern | No |

**Navigation Path:** `https://vincen.tl/` → `https://dsl.cis.upenn.edu/`

**Navigation Score:**

| Component | Score |
|-----------|-------|
| Lab Score | 0.805 |
| Member Score | 0.000 |
| Research Group Score | 0.000 |
| Homepage Score | 0.234 |
| Directory Penalty | 0.000 |
| Provider Score | 0.805 |
| Final Score | 0.805 |

**Navigation Evidence:** `node_type:lab_page`, `anchor_lab:lab`, `anchor_group+:lab`

**All Headings Found:** `Distributed Systems Laboratory`, `Distributed Systems Laboratory`, `About Us`

**Unmatched Member Headings (near-miss):** `Distributed Systems Laboratory`, `Distributed Systems Laboratory`

**Parser-Detected Member Sections:** _none_

**Rejected Reason:** `Page rejected: No member sections found on page`

**Suggested Fix:**

> Page is JavaScript-rendered (React) — visible text ratio is only 2.2%. The static HTML parser receives near-empty content. Fix: (1) add a headless-browser fetch path (Playwright/Puppeteer) for SPA pages; (2) look for a server-side-rendered sitemap or /people.json endpoint; (3) check if the page has a static fallback URL.

---

### 4. Rachit Agarwal 0001 ✗

| Field | Value |
|-------|-------|
| **Failure Category** | **Section Detection Failure** |
| Professor | Rachit Agarwal 0001 |
| Original Homepage | `http://www.cs.cornell.edu/~ragarwal/index.html` |
| Canonical Homepage | `http://www.cs.cornell.edu/~ragarwal/index.html` |
| Research Group URL | `https://www.cs.cornell.edu/~ragarwal/collaborators.html` |
| Fetch Status | `page_rejected` |
| Classifier Page Type | `research_group` |
| Classifier Confidence | 0.400 |
| Classifier Acceptable | No |
| Parser: Sections Detected | 0 |
| Parser: Member Sections | 0 |
| Parser: Entries Parsed | 0 |
| Wrong Page Detected | No |
| Dynamic / SPA | No |
| SPA Frameworks Detected | — |
| HTML Size | 21,203 bytes |
| Visible Text Ratio | 24.0% |
| Member Keywords in HTML | Yes |
| Plain-Text Section Headers | No |
| Plain-Text Patterns Found | — |
| Card/Grid Pattern | No |

**Navigation Path:** `http://www.cs.cornell.edu/~ragarwal/index.html` → `https://www.cs.cornell.edu/~ragarwal/collaborators.html`

**Navigation Score:**

| Component | Score |
|-----------|-------|
| Lab Score | 1.000 |
| Member Score | 0.000 |
| Research Group Score | 0.000 |
| Homepage Score | 0.300 |
| Directory Penalty | 0.000 |
| Provider Score | 1.000 |
| Final Score | 1.000 |

**Navigation Evidence:** `node_type:lab_page`, `group_pattern:/~`, `anchor_lab:lab`, `anchor_group+:lab`

**Parser-Detected Member Sections:** _none_

**Rejected Reason:** `Page rejected: No member sections found on page`

**Suggested Fix:**

> Page contains member-related words in HTML body but no h1–h4 headings matched section keywords. Members may be listed without standard HTML heading elements — possibly using bold text, divs, or CSS classes as visual separators. Fix: extend MemberPageParser to handle div/span-based section boundaries.

---

### 5. Tianyin Xu ✗

| Field | Value |
|-------|-------|
| **Failure Category** | **Section Detection Failure** |
| Professor | Tianyin Xu |
| Original Homepage | `https://tianyin.github.io/` |
| Canonical Homepage | `https://tianyin.github.io/` |
| Research Group URL | `https://www.cs.cornell.edu/~legunsen` |
| Fetch Status | `page_rejected` |
| Classifier Page Type | `research_group` |
| Classifier Confidence | 0.400 |
| Classifier Acceptable | No |
| Parser: Sections Detected | 0 |
| Parser: Member Sections | 0 |
| Parser: Entries Parsed | 0 |
| Wrong Page Detected | **Yes ⚠️** |
| Dynamic / SPA | No |
| SPA Frameworks Detected | — |
| HTML Size | 35,819 bytes |
| Visible Text Ratio | 33.6% |
| Member Keywords in HTML | Yes |
| Plain-Text Section Headers | No |
| Plain-Text Patterns Found | — |
| Card/Grid Pattern | No |

**Navigation Path:** `https://tianyin.github.io/` → `https://www.cs.cornell.edu/~legunsen`

**Navigation Score:**

| Component | Score |
|-----------|-------|
| Lab Score | 0.808 |
| Member Score | 0.000 |
| Research Group Score | 0.000 |
| Homepage Score | 0.195 |
| Directory Penalty | 0.000 |
| Provider Score | 0.808 |
| Final Score | 0.808 |

**Navigation Evidence:** `node_type:lab_page`, `group_pattern:/~`, `anchor_lab:lab`, `anchor_group+:lab`

**Parser-Detected Member Sections:** _none_

**Rejected Reason:** `Wrong page: Page title 'Owolabi Legunsen' does not match target professor 'Tianyin Xu'; likely a different person's homepage`

**Suggested Fix:**

> WRONG PAGE NAVIGATED: the selected URL (https://www.cs.cornell.edu/~legunsen) belongs to a different person (page title: 'Owolabi Legunsen'). The navigator followed a link on the professor's homepage that points to a collaborator's or colleague's page rather than the professor's own lab. Fix: (1) add cross-professor name verification to GroupPageDiscoverer — reject candidates whose page title does not contain the professor's name or institution; (2) add the URL pattern to the navigator's denylist.

---

### 6. Aditya Akella ✗

| Field | Value |
|-------|-------|
| **Failure Category** | **Section Detection Failure** |
| Professor | Aditya Akella |
| Original Homepage | `https://www.cs.utexas.edu/~akella/` |
| Canonical Homepage | `https://www.cs.utexas.edu/~akella/` |
| Research Group URL | `http://utns.cs.utexas.edu/` |
| Fetch Status | `page_rejected` |
| Classifier Page Type | `student_page` |
| Classifier Confidence | 0.050 |
| Classifier Acceptable | No |
| Parser: Sections Detected | 3 |
| Parser: Member Sections | 0 |
| Parser: Entries Parsed | 0 |
| Wrong Page Detected | No |
| Dynamic / SPA | No |
| SPA Frameworks Detected | — |
| HTML Size | 13,466 bytes |
| Visible Text Ratio | 23.0% |
| Member Keywords in HTML | Yes |
| Plain-Text Section Headers | No |
| Plain-Text Patterns Found | — |
| Card/Grid Pattern | No |

**Navigation Path:** `https://www.cs.utexas.edu/~akella/` → `http://utns.cs.utexas.edu/`

**Navigation Score:**

| Component | Score |
|-----------|-------|
| Lab Score | 0.805 |
| Member Score | 0.000 |
| Research Group Score | 0.000 |
| Homepage Score | 0.234 |
| Directory Penalty | 0.000 |
| Provider Score | 0.805 |
| Final Score | 0.805 |

**Navigation Evidence:** `node_type:lab_page`, `anchor_lab:lab`, `anchor_group+:lab`

**All Headings Found:** `News`, `Featured projects`, `Featured publications`

**Parser-Detected Member Sections:** _none_

**Rejected Reason:** `Page rejected: No member sections found on page`

**Suggested Fix:**

> Page headings found: "News", "Featured projects", "Featured publications". None of these headings matched CURRENT_SECTION_KEYWORDS or ALUMNI_SECTION_KEYWORDS. Fix: review these headings and add matching entries to precision_constants.py. Members may also be organized by CSS class/div without heading elements.

---

### 7. Peng Huang 0005 ✗

| Field | Value |
|-------|-------|
| **Failure Category** | **Fetch Failure** |
| Professor | Peng Huang 0005 |
| Original Homepage | `https://web.eecs.umich.edu/~ryanph/` |
| Canonical Homepage | `https://web.eecs.umich.edu/~ryanph/` |
| Research Group URL | — |
| Fetch Status | `skipped` |

**Parser-Detected Member Sections:** _none_

**Rejected Reason:** `No suitable group page found in HomepageGraph`

**Suggested Fix:**

> Homepage fetch itself failed (HTTPSConnectionPool(host='web.eecs.umich.edu', port=443): Max retries exceeded with url: /~ryanph/ (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden')))). Group page was never reachable. Fix: retry with a longer timeout, use a proxy, or skip this professor.

---

## Prioritized Recommendations

_Ranked by number of professors affected._

### R1. Expand CURRENT_SECTION_KEYWORDS (3 professors affected)

The most common failure. Pages have member-related headings that don't match any keyword. Near-miss headings: "Distributed Systems Laboratory".

**File:** `research_group_agent/precision_constants.py`
**Action:** Add normalized versions of unmatched headings to CURRENT_SECTION_KEYWORDS.

### R2. Add CSS Card/Grid Layout Parser (1 professors affected)

Some pages list members in card/grid layouts without h1–h4 section headings. The parser only supports heading-delimited sections.

**File:** `research_group_agent/parser.py`
**Action:** Add a secondary parser path for repeated profile-card containers.

### R3. Add Headless Browser Fetch for SPA Pages (1 professors affected)

JavaScript-rendered pages return near-empty HTML to the static fetcher.

**File:** `research_group_agent/fetcher.py`
**Action:** Add a Playwright/Puppeteer-based fetch option as a fallback.

### R4. Improve HomepageGraph Group Page Discovery (1 professors affected)

For some professors the HP agent didn't discover any lab/people/group page. This may be due to Google Sites JS navigation or unusual anchor text.

**File:** `homepage_agent/navigator.py` + `research_group_agent/precision_constants.py`
**Action:** Broaden GROUP_ANCHOR_POSITIVE keywords and add a Google Sites-aware crawl strategy.

### R5. Investigate Network Fetch Failures (1 professors affected)

Some pages couldn't be fetched at all (network error, timeout, or proxy block). Retry with different network configuration.

**Action:** Retry affected URLs with increased timeout or direct network access.

---

_This report was generated by `tools/pr15_5_failure_inspector.py` (PR15.5)._
_All findings are evidence-based from cached HTML and existing pipeline artifacts._
_Do not modify parser heuristics without evidence from this report._
