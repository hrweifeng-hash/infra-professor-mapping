# Infra Professor Mapping

Research intelligence platform for discovering and ranking infrastructure / systems professors from major CS conferences, with automated homepage navigation, lab discovery, and research-group member extraction.

**Last updated:** 2026-07-13 · **Pipeline version:** PR32

## Quick links

| Document | Description |
|----------|-------------|
| [docs/README.md](docs/README.md) | Platform overview |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Layered architecture + research-group pipeline |
| [docs/PROJECT_STATE.md](docs/PROJECT_STATE.md) | Current status, validation results, next steps |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Completed PRs and planned work |
| [docs/pr32_homepage_recovery_lab_discovery.md](docs/pr32_homepage_recovery_lab_discovery.md) | PR32 design + validation |
| [docs/identity_foundation.md](docs/identity_foundation.md) | PR31 identity layer |

## Research group pipeline (PR32)

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

## Validation (Top-100 US infrastructure professors)

```bash
python3.11 tools/pr32_navigation_validation.py
python3.11 tools/pr32_navigation_validation.py --skip-pipeline
```

Corrected **PR30 → PR32** benchmark (matched cohort, N=100):

| Metric | PR30 | PR32 | Delta |
|--------|-----:|-----:|------:|
| Navigation success | 42 | 49 | +7 |
| Current members | 980 | 1,259 | +279 |
| Improved professors | — | 21 | — |
| Regressed professors | — | 4 | — |
| Unchanged professors | — | 75 | — |

See [docs/PROJECT_STATE.md](docs/PROJECT_STATE.md) for full metrics and conclusions.

## Tests

```bash
python3.11 -m pytest tests/test_pr32_navigation.py tests/test_pr32_validation_tooling.py tests/test_identity_foundation.py -v
```

## DBLP ranking pipeline (legacy)

```bash
python main.py
```

See [docs/HANDOFF.md](docs/HANDOFF.md) for DBLP pipeline details (PR7–PR11).
