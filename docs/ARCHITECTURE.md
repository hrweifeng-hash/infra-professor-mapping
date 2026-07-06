# ARCHITECTURE.md

# Research Intelligence Platform

---

# Vision

The project is evolving from a DBLP parser into a Research Intelligence Platform.

Long-term workflow

```
DBLP
      │
      ▼
Author Extraction
      │
      ▼
Professor Resolution
      │
      ▼
Identity Resolution
      │
      ▼
Research Intelligence
      │
      ▼
Ranking
      │
      ▼
Lab Discovery
      │
      ▼
Student Discovery
      │
      ▼
Candidate Intelligence
      │
      ▼
Recruiting Intelligence
```

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