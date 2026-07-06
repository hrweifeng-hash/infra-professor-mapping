# Infrastructure Professor Mapping
Project State

Last Updated:
2026-07-01

---

# Goal

Build an academic intelligence pipeline that automatically discovers and ranks
top Infrastructure / Systems professors from major CS conferences.

The final deliverable is NOT an academic search engine.

The final deliverable is a Professor Mapping platform for technical recruiting.

The pipeline should eventually produce structured Professor Cards.

---

# Current Architecture

DBLP

↓

Crawler

↓

Parser

↓

Author Builder

↓

Professor Builder

↓

Professor Registry

↓

Intelligence Pipeline

↓

Ranking Engine

↓

Exporter

↓

Top_Professors.xlsx

---

# Current Progress

## PR0

Project Skeleton

Status:
DONE

---

## PR1

Conference Pipeline

Current implementation:

Conference

↓

DBLP XML

↓

Proceedings

↓

Author Profiles

Status:

PARTIALLY COMPLETE

Problems:

- XML URLs are inconsistent across conferences.
- HTTP 404
- HTTP 429
- RemoteDisconnected
- Current crawler is not suitable for large-scale mapping.

---

## PR2

Professor Builder

Status:

DONE

Implemented:

- AuthorProfile
- ProfessorProfile
- ProfessorRegistry
- Merge duplicate professors

---

## PR3

Intelligence

Status:

DONE

Implemented:

- Publication Analyzer
- Venue Analyzer
- Research Area Analyzer
- Productivity Analyzer
- Statistics Analyzer

Outputs:

- Publication Count
- Research Areas
- Venue Distribution
- Overall Score
- Priority

Ranking exists but will continue to evolve.

---

## PR4

Exporter

Status:

PARTIALLY COMPLETE

Current output:

Top_Professors.xlsx

Current issues:

- Some columns are incomplete.
- University information is missing.
- Export format is still temporary.

Do NOT optimize exporter until data layer becomes stable.

---

# Current Blocker

The project is currently blocked by the data source.

Current crawler downloads conference XML by guessing URLs.

Example:

https://dblp.org/db/conf/osdi/osdi2025.xml

This approach is unreliable.

Many conferences fail because:

- XML naming differs
- Some XML files do not exist
- DBLP rate limits requests

This is currently the highest priority problem.

---

# Current Decision

Do NOT add new features.

Freeze:

- Homepage
- Google Scholar
- OpenAlex
- Semantic Scholar
- HM Match
- Professor Card

Everything above is postponed.

Only focus on fixing the data layer.

---

# Current Plan

Priority 1

Replace online XML downloading.

The project is moving toward parsing the official DBLP dataset:

dblp.xml.gz

Instead of downloading one XML per conference.

Expected pipeline:

dblp.xml.gz

↓

Filter conferences

↓

Filter years

↓

Proceedings

↓

Existing Builder Pipeline

No changes should be required in:

- Builder
- Registry
- Intelligence
- Ranking

---

Priority 2

Run the complete dataset.

Target:

22 conferences

Years:

2021-2026

Validate:

- Paper count
- Author count
- Professor count

---

Priority 3

Fix Export

After the dataset becomes stable.

Exporter should contain:

- Name
- University
- Research Areas
- Top Venues
- Publication Count
- Years Active
- Overall Score
- Priority

---

Priority 4

Professor Card

Professor Card should NOT introduce any new data source.

Only reorganize existing information.

---

# Future Version (V2)

Not now.

Will include:

- Homepage
- DBLP Profile
- Google Scholar
- OpenAlex
- Semantic Scholar
- Research Summary
- HM Match
- Recruiting Recommendation

These features are intentionally postponed.

---

# Design Principles

1. Data correctness is more important than new features.

2. One PR should solve exactly one problem.

3. Do not modify Builder / Registry unless necessary.

4. The project is a recruiting intelligence platform,
   not a paper search engine.

5. Always keep the pipeline modular.