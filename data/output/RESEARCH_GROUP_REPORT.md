# Research Group Intelligence Report (PR17)

Generated: 2026-07-07T02:46:04.549782+00:00
Schema version: **1.3** | Pipeline: **PR17**

## Summary

- Professors processed: **10**
- Research groups discovered: **8**
- Successful group page fetches: **3**
- Pages rejected by classifier: **5**
- Wrong-page rejections (PR16): **1**
- Current members extracted: **39**
- Former members (debug): **70**
- Current member ratio: **36%**
- Extraction provider: **heuristic**

## Navigation Intelligence

- Navigation provider: **heuristic**
- Navigation success rate: **80%**
- Average navigation confidence: **0.880**
- Average navigation depth: **2.1** hops
- Fallback rate: **100%**
- LLM-navigated: **0**

### Most Common Navigation Evidence

- `node_type:lab_page`: **5**
- `anchor_lab:lab`: **5**
- `anchor_group+:lab`: **5**
- `node_type:people_page`: **3**
- `anchor_member:students`: **2**
- `anchor_group+:student`: **2**
- `group_pattern:/~`: **2**
- `url_member:/people`: **2**
- `group_pattern:/people/`: **2**
- `url_member:/students`: **1**

## Multi-Page Discovery (PR17)

- Professors using multi-page discovery: **8**
- Average parsed pages per professor: **1.25**
- Average successful pages per professor: **0.38**
- Average merged members per professor: **13.0**
- Deduplication rate: **64.2%**
- Members found on multiple pages: **0**

### Member Source Distribution

- 1_pages: **109** members

## Homepage Resolution

- Resolution attempts: **10**
- Upgrades to personal homepage: **1** (10%)
- Professors without canonical upgrade: **9**

- **Ravi Netravali**: https://www.cs.princeton.edu/people/profile/ravian → https://www.cs.princeton.edu/~ravian (link_upgrade:Homepage)

## Precision Statistics

- Average members per professor: **3.9**
- Median members per professor: **0**
- Healthy range: **5-20**
- Professors in healthy range: **3**
- Rejected pages: **9**
- Rejected candidates: **3**

### Member Count Histogram

- 0: **7**
- 6-20: **3**

### Most Common Rejection Reasons

- **No member sections found on page**: 5
- **does not look like a person name**: 3
- **no suitable group page in HomepageGraph**: 2
- **Rejected as research_group (confidence=0.35)**: 1
- **Page title 'Owolabi Legunsen' does not match target professor 'Tianyin Xu'; likely a different person's homepage**: 1

## Role Distribution

- **PhD Student**: 34
- **Professor**: 5

## Identity Coverage

- Members with any identity: **8** (20%)
- Homepage: **8** (20%)
- GitHub: **0** (0%)
- Google Scholar: **0** (0%)
- LinkedIn: **0** (0%)

## Language Signal Distribution

- Members with language signal: **23** (59%)
- Likely Chinese Surname: **23**

_Note: Language signals are probabilistic recruiting hints — not nationality, ethnicity, or citizenship classifications._

## Manual Review Cases

**7** professors flagged:

- **Ravi Netravali** (0 members, https://sysml.cs.princeton.edu/): page_rejected_by_classifier; All candidate pages failed
- **Arvind Krishnamurthy** (0 members, no group page): group_page_not_found; No suitable group page found in HomepageGraph
- **Vincent Liu 0001** (0 members, https://dsl.cis.upenn.edu/): page_rejected_by_classifier; All candidate pages failed
- **Rachit Agarwal 0001** (0 members, https://www.cs.cornell.edu/~ragarwal/collaborators.html): page_rejected_by_classifier; All candidate pages failed
- **Tianyin Xu** (0 members, https://www.cs.cornell.edu/~legunsen): page_rejected_by_classifier; All candidate pages failed
- **Aditya Akella** (0 members, http://utns.cs.utexas.edu/): page_rejected_by_classifier; All candidate pages failed
- **Peng Huang 0005** (0 members, no group page): group_page_not_found; No suitable group page found in HomepageGraph

## Output

- `research_group_graph.json` — ResearchGroupGraph per professor (Top 10)
- `NAVIGATION_DEBUG.json` — full navigation decision log per professor
- Precision-first extraction: false positives rejected over false negatives
- PR17: multi-page discovery merges up to 3 candidate pages per professor

Total graphs written: **10**
