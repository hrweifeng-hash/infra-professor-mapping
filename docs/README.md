# Infra Professor Mapping

> Research Intelligence Platform for Infrastructure Faculty Discovery

## Overview

Infra Professor Mapping is an academic intelligence platform that automatically builds structured profiles for infrastructure researchers from top computer systems conferences.

The goal is to replace manual professor research with an automated, reproducible, and continuously updatable pipeline.

Current focus:

- Infrastructure professors
- Top systems conferences
- Recruiting intelligence
- Research landscape analysis

---

## Motivation

Finding strong infrastructure researchers is currently a highly manual process.

Typical workflow:

- Search conference proceedings
- Read author pages
- Check university websites
- Identify faculty manually
- Estimate research strength

This process is:

- Time-consuming
- Difficult to reproduce
- Hard to scale
- Quickly becomes outdated

Infra Professor Mapping automates this workflow.

---

## Current Capabilities

### Supported Conferences

Current pipeline supports:

- OSDI
- SOSP
- NSDI
- SIGCOMM
- FAST
- EuroSys
- ATC

(Current conference list can be easily extended.)

---

### Pipeline

```
DBLP XML
    │
    ▼
Streaming Dataset Scanner
    │
    ▼
Conference Parser
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
Research Intelligence
    │
    ▼
Ranking Engine
    │
    ▼
Exporter
```

The pipeline processes DBLP in a streaming fashion without loading the full dataset into memory.

---

### Generated Intelligence

For every professor, the platform generates:

- Publication history
- Conference distribution
- Venue distribution
- Research keywords
- Active years
- Publication score
- Venue score
- Overall ranking score

All derived information is stored inside a single `ProfessorIntelligence` object.

---

## Engineering Highlights

- Streaming DBLP processing
- Modular architecture
- Typed domain models
- Merge-before-analysis pipeline
- Single Source of Truth
- Deterministic ranking pipeline

---

## Current Status

### DBLP ranking pipeline (PR0–PR11)

- Streaming DBLP parser
- Conference extraction
- Professor registry + intelligence
- Top-100 US export + validation

### Research group pipeline (PR13–PR32)

- Homepage agent + canonical resolution
- Multi-level navigation explorer (BFS)
- Member parser + person validator
- **PR31 ✅ Identity Foundation**
- **PR32 ✅ Homepage Recovery + Lab Discovery**

See [PROJECT_STATE.md](PROJECT_STATE.md) for PR32 validation metrics.

---

## Roadmap

See [ROADMAP.md](ROADMAP.md) for completed PRs and planned work (Homepage Override, Lab Override, OpenAlex Resolver).

---

## Long-Term Vision

This project is designed as a reusable Research Intelligence Platform.

Future applications include:

- Professor ranking
- University intelligence
- Academic knowledge graph
- Recruiting intelligence
- Faculty search
- Collaboration recommendation
- Research trend analysis
- Lab intelligence

---

## Roadmap

### PR7 (Current Demo)

Goal:

Produce a complete Top 100 Infrastructure Professor ranking from DBLP.

Deliverables:

- End-to-end pipeline
- Top 100 ranking
- Exported CSV / JSON
- Pipeline validation report

---

### Future

- OpenAlex integration
- Semantic Scholar integration
- Google Scholar enrichment
- University normalization
- Research topic clustering
- Hiring recommendation engine