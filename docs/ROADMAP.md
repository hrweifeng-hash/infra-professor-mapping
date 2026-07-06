## PR7 — Demo Release (Top 100 Infrastructure Professors)

### Objective

Deliver a production-ready demo that generates a high-quality ranking of top Infrastructure professors from major systems conferences.

The primary goal of PR7 is to produce a stakeholder-ready deliverable rather than introducing new architecture.

---

### Goals

#### 1. Top 100 Professor Ranking

Generate a ranked list of the Top 100 Infrastructure professors.

Output should include:

- Name
- University
- Research Areas
- Publication Count
- Conference Distribution
- Overall Score
- Priority

---

#### 2. Ranking Quality

Improve ranking quality using the existing DBLP publication data.

Validate:

- publication counts
- venue weights
- duplicate removal
- conference coverage

Ranking should produce reasonable results for major Infrastructure researchers.

---

#### 3. Export

Generate demo-ready outputs.

Formats:

- Excel (.xlsx)
- CSV

Exports should be human-readable and suitable for presentation.

---

#### 4. Data Quality Validation

Run the full pipeline on the real DBLP dataset.

Verify:

- no duplicate professors
- correct publication counts
- exporter correctness
- ranking consistency
- Top 100 manual sanity check

---

#### 5. Pipeline Stability

Verify the complete execution pipeline.

```
DBLP XML

↓

DatasetPipeline

↓

ConferencePipeline

↓

ProfessorRegistry

↓

IntelligencePipeline

↓

RankingEngine

↓

Exporter
```

Pipeline should complete successfully without manual intervention.

---

### Deliverables

- Top_Professors.xlsx
- Top_Professors.csv
- Validation report
- Demo-ready ranking
- Updated README

---

### Success Criteria

- Full pipeline completes successfully.
- Top 100 ranking is generated.
- Export contains valid professor information.
- No duplicate professors.
- Publication statistics are correct.
- Ranking is suitable for stakeholder demonstration.

---

### Out of Scope

The following features are intentionally deferred to later PRs:

- OpenAlex integration
- Semantic Scholar integration
- Google Scholar citations
- Homepage crawling
- Identity resolution
- Lab mapping
- University ranking
- Recruiting intelligence
- HM scoring

PR7 focuses exclusively on delivering a stable, demo-quality ranking based on DBLP.