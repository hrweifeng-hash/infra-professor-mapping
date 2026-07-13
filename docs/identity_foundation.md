# Identity Foundation (PR31)

**Status:** ✅ Complete (2026-07-13)

## Overview

PR31 introduces a permanent **Identity Layer** between parser output and the member graph export. The identity layer preserves every parsed candidate — including those rejected by the validator — so future identity enrichment (OpenAlex, DBLP, Google Scholar, Semantic Scholar, ORCID) can operate on structured evidence instead of re-parsing websites.

This is a **graph architecture improvement**, not a parser or validator change.

## Pipeline Architecture

```
Parser
  ↓
Identity Candidate  (persist everything)
  ↓
PersonValidator   (unchanged — still gates member export)
  ↓
Validated Group Member
  ↓
Talent Graph      (research_group_graph.json — unchanged)
```

Future enrichment plugs in after identity candidates are preserved:

```
Identity Candidate
  ↓
Identity Resolver  (OpenAlex / DBLP / ORCID — future)
  ↓
Resolved Identity
  ↓
Member Graph enrichment
```

## Identity Graph vs Member Graph

These are **different concepts**:

| Concept | Purpose | Contents |
|---------|---------|----------|
| **Identity Graph** | Preserve raw identity evidence from parser output | All candidates: verified, resolvable, partial, and invalid |
| **Member Graph** | Production talent export | Only precision-validated, capped, merged members |

The member graph optimizes for **precision** — false positives are worse than false negatives. The identity graph optimizes for **preservation** — nothing from the parser is discarded, because rejected candidates may still be resolvable via external APIs.

Example: a PhD student listed with only a name and section (no homepage) is rejected by `PersonValidator` today. Previously this person was lost entirely. Now they exist as a `RESOLVABLE` or `PARTIAL` identity candidate in `identity_candidates.json`.

## Validation States

Validation state is **metadata only** — it does not change production export logic.

| State | Meaning |
|-------|---------|
| `VERIFIED` | Exported in the current member graph |
| `RESOLVABLE` | Enough evidence for future resolver (email, GitHub, Scholar, affiliation, profile URL) |
| `PARTIAL` | Name + section/role only |
| `INVALID` | Parser noise, navigation artifacts, faculty, admin, obvious junk |

## Components

### `IdentityCandidate`

Lightweight dataclass preserving identity evidence:

- `id`, `name`, `role`, `section`, `status`
- `source_professor`, `source_page`, `source_domain`
- `email`, `homepage`, `github`, `scholar`, `linkedin`, `orcid`, `affiliation`
- `confidence`, `validation_state`, `rejection_reason`, `created_at`

### `IdentityRepository`

Independent from `MemberMerger`. Responsibilities:

- `collect()` — ingest candidates during pipeline run
- `merge()` / `deduplicate()` — merge evidence across pages (same professor + name)
- `export()` — write `identity_candidates.json`

### `IdentityResolver` (interface)

Plug-in point for external identity providers:

```python
class IdentityResolver(ABC):
    def resolve(self, candidate: IdentityCandidate) -> ResolvedIdentity: ...
```

`StubIdentityResolver` is provided. Future providers implement the same interface:

- OpenAlex
- DBLP
- Semantic Scholar
- Google Scholar
- ORCID

## Output

### `identity_candidates.json`

New additive artifact written alongside existing exports:

```json
{
  "schema_version": "1.0",
  "pipeline_version": "PR31",
  "total_candidates": 142,
  "validation_state_counts": {
    "VERIFIED": 38,
    "RESOLVABLE": 45,
    "PARTIAL": 32,
    "INVALID": 27
  },
  "candidates": [
    {
      "name": "John Smith",
      "role": "PhD Student",
      "section": "Current Students",
      "source_professor": "Ryan Huang",
      "source_page": "https://orderlab.systems/team",
      "validation_state": "RESOLVABLE",
      "email": "jsmith@university.edu",
      "github": "https://github.com/jsmith"
    }
  ]
}
```

### Unchanged exports

- `research_group_graph.json` — identical structure and export logic
- `homepage_graph.json` — unchanged

## Design Principles

1. **Do not modify parser behavior**
2. **Do not modify validator behavior**
3. **Do not modify navigation**
4. **Do not integrate OpenAlex yet**
5. **Keep identity layer independent from member graph**
6. **Infrastructure only — plug-and-play for future enrichment**

## Validation

Run the validation script:

```bash
python3.11 tools/identity_foundation_validation.py
```

Reports:

- Total parser candidates
- Counts by validation state (VERIFIED / RESOLVABLE / PARTIAL / INVALID)
- Exported members
- Identity graph size
- Verification that production exports are unchanged

## Package Layout

```
identity_foundation/
├── __init__.py
├── models.py          # IdentityCandidate, ValidationState, ResolvedIdentity
├── validation.py      # Validation-state classification
├── collector.py       # Parser → IdentityCandidate
├── repository.py      # collect / merge / deduplicate / export
└── resolver.py        # IdentityResolver interface + stub
```
