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

### Completed

- Streaming DBLP parser
- Conference extraction
- Author aggregation
- Professor profile generation
- Professor deduplication
- Intelligence pipeline
- Ranking engine
- Export framework
- End-to-end pipeline validation

---

### Current Output

Current pipeline is capable of producing:

- Ranked professor list
- Publication statistics
- Conference statistics
- Structured professor profiles

Target demo output:

- Top 100 Infrastructure Professors
- University distribution
- Research area statistics

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