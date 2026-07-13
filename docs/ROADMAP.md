# Roadmap

**Last updated:** 2026-07-13

---

## Completed — Research group intelligence

| PR | Status | Deliverable |
|----|--------|-------------|
| PR13–PR18 | ✅ | Homepage agent, group discovery, member extraction baseline |
| PR19–PR22 | ✅ | Candidate pages, people-page discovery, homepage-first detection |
| PR23–PR25 | ✅ | Navigation guard, ranking, BFS explorer integration |
| PR26–PR29 | ✅ | Department scope, adaptive caps, deep/paragraph layouts |
| PR30 | ✅ | Navigation evidence ranking |
| **PR31** | ✅ | **Identity Foundation** — candidate preservation layer |
| **PR32** | ✅ | **Homepage Recovery + Lab Discovery + validation overhaul** |

### PR32 validated impact (Top-100, PR30 → PR32)

- Navigation success: 42 → 49 (+7)
- Current members: 980 → 1,259 (+279)
- 21 improved / 4 regressed / 75 unchanged professors
- 27 homepage recoveries, 242 labs discovered

---

## Completed — DBLP ranking (PR0–PR11)

| PR | Status |
|----|--------|
| PR0–PR7 | ✅ Streaming DBLP, registry, intelligence, demo export |
| PR10 | ✅ US professor filtering + DBLP homepage enrichment |
| PR11 | ✅ Infrastructure affinity ranking + validation report |

See [HANDOFF.md](HANDOFF.md) for DBLP pipeline details.

---

## Next — High ROI

### PR33 (planned): Manual Homepage Override

Curated overrides for professor homepages that DBLP or canonical resolution get wrong. JSON or YAML resource file; applied before Homepage Recovery.

### PR34 (planned): Lab Override

Manual lab URL hints for professors where Lab Discovery misses the correct research group entry point.

### PR35 (planned): OpenAlex Resolver

Wire Identity Foundation to OpenAlex for homepage, affiliation, and ORCID enrichment. First external identity source on the preserved candidate graph.

---

## Deferred — Lower ROI near term

- Additional parser layout heuristics (diminishing returns vs navigation)
- Google Scholar integration (no stable API)
- Full recruiter dashboard / talent search modules

---

## Design principles

1. **Navigation before parsing** — reach the right page first (PR32 proved this).
2. **Preserve identity evidence (PR31)** — never discard parser output silently.
3. **Apples-to-apples validation** — matched cohort, consistent metrics, per-professor regression tables.
4. **One PR, one problem** — keep changes reviewable.
