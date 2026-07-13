# ARCHITECTURE.md

# Research Intelligence Platform

**Last updated:** 2026-07-13

---

# Vision

The project combines two complementary tracks:

1. **DBLP ranking pipeline** — discover and rank professors from conference proceedings.
2. **Research group pipeline** — navigate professor/lab homepages and extract group members for recruiting intelligence.

Long-term workflow

```
DBLP / Conference Papers
      │
      ▼
Professor Discovery
      │
      ▼
Homepage Agent
      │
      ▼
Homepage Recovery (PR32)
      │
      ▼
Lab Discovery (PR32)
      │
      ▼
Navigation Explorer
      │
      ▼
Member Parser
      │
      ▼
Identity Foundation (PR31)
      │
      ▼
Person Validator
      │
      ▼
Research Group Graph
      │
      ▼
Ranking / Export / Recruiting Intelligence
```

---

# Research Group Pipeline (PR13–PR32)

End-to-end flow for the Top-100 US infrastructure professor validation cohort.

```
HomepageGraph (from Homepage Agent)
        │
        ▼
CanonicalHomepageResolver
        │
        ▼
ResearchGroupPipeline.analyze()
        │
        ├─► HomepageFetcher (HTTP, cache, timeouts)
        ├─► HomepageRecovery (PR32) — redirect, meta refresh, canonical, moved-page
        ├─► HomepageMemberDetector (PR22)
        ├─► LabDiscovery (PR32) — lab link signals
        ├─► NavigationExplorer (BFS) — from homepage + each lab
        ├─► CandidatePageGenerator + Ranker + NavigationGuard
        ├─► MemberPageParser
        ├─► IdentityCollector + IdentityRepository (PR31)
        ├─► PersonValidator
        └─► ResearchGroupGraphBuilder
```

### Key modules

| Component | Path |
|-----------|------|
| Homepage Recovery | `homepage_agent/homepage_recovery.py` |
| Lab Discovery | `research_group_agent/lab_discovery.py` |
| Navigation Explorer | `research_group_agent/navigation_explorer.py` |
| Identity Foundation | `identity_foundation/` |
| HTTP Fetcher | `homepage_agent/fetcher.py` (+ `FetchStats`) |
| Validation | `tools/pr32_navigation_validation.py` |

### Validation baseline

PR32 recall comparisons use **PR30@100** as baseline (PR31 did not change navigation). Professors are matched by name; metrics use the same navigation-success definition on both sides.

---

# Layer 1

Dataset Layer

Responsibilities

- Parse DBLP
- Streaming
- XML normalization
- Conference extraction

Produces

Proceedings

---

# Layer 2

Profile Layer

Responsibilities

Build

AuthorProfile

ProfessorProfile

No analytics.

No ranking.

No statistics.

---

# Layer 3

Identity Layer (PR8)

Responsibilities

Resolve real-world identity.

Produces

ProfessorIdentity

Fields

- University
- Homepage
- Faculty Page
- Country
- Department
- Lab
- Google Scholar
- ORCID
- Semantic Scholar

Identity should never compute scores.

---

# Layer 4

Intelligence Layer

Responsibilities

Compute

Publication count

Venue distribution

Research areas

Conference statistics

Influence score

Priority

Outputs

ProfessorIntelligence

---

# Layer 5

Ranking Layer

Consumes

ProfessorIdentity

ProfessorIntelligence

Produces

RankedProfessor

Responsibilities

Sorting only.

No statistics.

No crawling.

---

# Layer 6

Export Layer

Consumes

RankedProfessor

Produces

Excel

CSV

JSON

Future

REST API

---

# Model Relationships

```
Author
    │
    ▼
AuthorProfile
    │
    ▼
ProfessorProfile
      │
      ├────────────┐
      ▼            ▼
ProfessorIdentity  ProfessorIntelligence
          │            │
          └──────┬─────┘
                 ▼
          RankedProfessor
                 │
                 ▼
              Exporter
```

---

# Pipeline

```
Scanner

↓

Dataset Pipeline

↓

Conference Pipeline

↓

Author Builder

↓

Professor Builder

↓

Professor Registry

↓

Identity Pipeline

↓

Intelligence Pipeline

↓

Ranking Engine

↓

Exporter
```

---

# Pipeline Contracts

Scanner

Input

DBLP XML

Output

Proceedings

---

Builders

Input

Raw models

Output

Profiles

---

Identity

Input

ProfessorProfile

Output

ProfessorIdentity

---

Intelligence

Input

ProfessorProfile

Output

ProfessorIntelligence

---

Ranking

Input

Identity + Intelligence

Output

RankedProfessor

---

Exporter

Input

RankedProfessor

Output

Excel / CSV / JSON

---

# Future Modules

IdentityResolver

HomepageResolver

ScholarResolver

UniversityResolver

LabCrawler

StudentCrawler

CandidateBuilder

RecruitingEngine

TrendAnalyzer

UniversityIntelligence

LabIntelligence

CollaborationGraph

AdvisorGraph