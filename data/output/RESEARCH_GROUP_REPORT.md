# Research Group Intelligence Report (PR17)

Generated: 2026-07-07T02:59:25.777275+00:00
Schema version: **1.3** | Pipeline: **PR17**

## Summary

- Professors processed: **100**
- Research groups discovered: **42**
- Successful group page fetches: **16**
- Pages rejected by classifier: **26**
- Wrong-page rejections (PR16): **4**
- Current members extracted: **151**
- Former members (debug): **297**
- Current member ratio: **34%**
- Extraction provider: **heuristic**

## Navigation Intelligence

- Navigation provider: **heuristic**
- Navigation success rate: **42%**
- Average navigation confidence: **0.831**
- Average navigation depth: **2.1** hops
- Fallback rate: **100%**
- LLM-navigated: **0**

### Most Common Navigation Evidence

- `node_type:lab_page`: **25**
- `anchor_lab:lab`: **25**
- `anchor_group+:lab`: **25**
- `node_type:people_page`: **11**
- `anchor_member:students`: **8**
- `anchor_group+:student`: **8**
- `node_type:research_group_page`: **6**
- `anchor_group+:group`: **6**
- `url_member:/students`: **4**
- `group_pattern:/students`: **4**

## Multi-Page Discovery (PR17)

- Professors using multi-page discovery: **42**
- Average parsed pages per professor: **1.38**
- Average successful pages per professor: **0.38**
- Average merged members per professor: **9.4**
- Deduplication rate: **66.3%**
- Members found on multiple pages: **0**

### Member Source Distribution

- 1_pages: **448** members

## Homepage Resolution

- Resolution attempts: **100**
- Upgrades to personal homepage: **8** (8%)
- Professors without canonical upgrade: **92**

- **Ravi Netravali**: https://www.cs.princeton.edu/people/profile/ravian → https://www.cs.princeton.edu/~ravian (link_upgrade:Homepage)
- **Ming Liu 0027**: https://mgliu.sites.cs.wisc.edu/index.html → https://pages.cs.wisc.edu/~mgliu/teaching.html (link_upgrade:Teaching)
- **Yang Wang 0009**: https://cse.osu.edu/people/wang.7564 → https://yangwang83.github.io/ (link_upgrade:Personal website)
- **Manya Ghobadi**: http://people.csail.mit.edu/ghobadi/ → http://www.cs.utoronto.ca/~monia/tcptrickle.html (link_upgrade:demo)
- **Christina Delimitrou**: https://people.csail.mit.edu/delimitrou/ → http://csl.stanford.edu/~christos/ (link_upgrade:Christos Kozyrakis)
- **Jian Huang 0006**: http://jianh.web.engr.illinois.edu/ → https://platformxlab.github.io (link_upgrade:Systems Platform and Intelligence Lab (Illinois PlatformX))
- **Song Han 0003**: https://songhan.mit.edu/ → https://svg-project.github.io/v1/ (link_upgrade:Sparse VideoGen)
- **Cheng Tan 0005**: https://www.khoury.northeastern.edu/people/cheng-tan/ → https://naizhengtan.github.io/ (link_upgrade:https://naizhengtan.github.io/)

## Precision Statistics

- Average members per professor: **1.5**
- Median members per professor: **0**
- Healthy range: **5-20**
- Professors in healthy range: **11**
- Rejected pages: **100**
- Rejected candidates: **61**

### Member Count Histogram

- 0: **84**
- 1-5: **5**
- 6-20: **11**

### Most Common Rejection Reasons

- **no suitable group page in HomepageGraph**: 58
- **No member sections found on page**: 29
- **missing personal profile URL or role evidence**: 28
- **does not look like a person name**: 19
- **exceeded member cap (20)**: 11
- **fetch failed**: 5
- **name matches non-person pattern**: 2
- **Rejected as research_group (confidence=0.35)**: 2
- **contains non-person keyword**: 1
- **Page title 'Owolabi Legunsen' does not match target professor 'Tianyin Xu'; likely a different person's homepage**: 1
- **Rejected as faculty_directory (confidence=0.28)**: 1
- **Rejected as faculty_directory (confidence=0.31)**: 1
- **Page title 'Anja Kalaba' does not match target professor 'Amit Levy 0001'; likely a different person's homepage**: 1
- **Page title 'Wisconsin Multifacet Project' does not match target professor 'Michael M. Swift'; likely a different person's homepage**: 1
- **Page title 'Graduated Students' does not match target professor 'Todd D. Millstein'; likely a different person's homepage**: 1

## Role Distribution

- **PhD Student**: 126
- **Professor**: 19
- **Postdoc**: 4
- **Research Staff**: 2

## Identity Coverage

- Members with any identity: **48** (32%)
- Homepage: **40** (26%)
- GitHub: **1** (1%)
- Google Scholar: **0** (0%)
- LinkedIn: **7** (5%)

## Language Signal Distribution

- Members with language signal: **69** (46%)
- Likely Chinese Surname: **69**

_Note: Language signals are probabilistic recruiting hints — not nationality, ethnicity, or citizenship classifications._

## Manual Review Cases

**89** professors flagged:

- **Ravi Netravali** (0 members, https://sysml.cs.princeton.edu/): page_rejected_by_classifier; All candidate pages failed
- **Arvind Krishnamurthy** (0 members, no group page): group_page_not_found; No suitable group page found in HomepageGraph
- **Vincent Liu 0001** (0 members, https://dsl.cis.upenn.edu/): page_rejected_by_classifier; All candidate pages failed
- **Rachit Agarwal 0001** (0 members, https://www.cs.cornell.edu/~ragarwal/collaborators.html): page_rejected_by_classifier; All candidate pages failed
- **Tianyin Xu** (0 members, https://www.cs.cornell.edu/~legunsen): page_rejected_by_classifier; All candidate pages failed
- **Aditya Akella** (0 members, http://utns.cs.utexas.edu/): page_rejected_by_classifier; All candidate pages failed
- **Peng Huang 0005** (0 members, no group page): group_page_not_found; No suitable group page found in HomepageGraph
- **Ang Chen 0001** (0 members, no group page): group_page_not_found; No suitable group page found in HomepageGraph
- **Remzi H. Arpaci-Dusseau** (0 members, no group page): group_page_not_found; No suitable group page found in HomepageGraph
- **Gregory R. Ganger** (0 members, https://www.pdl.cmu.edu/): page_rejected_by_classifier; All candidate pages failed
- **Sylvia Ratnasamy** (0 members, no group page): group_page_not_found; No suitable group page found in HomepageGraph
- **Peter R. Pietzuch** (0 members, http://www.cl.cam.ac.uk/): page_rejected_by_classifier; All candidate pages failed
- **Ming Liu 0027** (0 members, no group page): group_page_not_found; No suitable group page found in HomepageGraph
- **Ramesh Govindan** (0 members, no group page): group_page_not_found; No suitable group page found in HomepageGraph
- **T. S. Eugene Ng** (0 members, no group page): group_page_not_found; No suitable group page found in HomepageGraph
- **Yifan Qiao 0002** (0 members, https://sky.cs.berkeley.edu/): page_rejected_by_classifier; All candidate pages failed
- **Alex C. Snoeren** (0 members, http://www.sysnet.ucsd.edu): page_rejected_by_classifier; All candidate pages failed
- **Sam H. Noh** (0 members, no group page): group_page_not_found; No suitable group page found in HomepageGraph
- **Shuai Mu 0001** (0 members, no group page): group_page_not_found; No suitable group page found in HomepageGraph
- **M. Frans Kaashoek** (0 members, http://www.csail.mit.edu/): page_rejected_by_classifier; All candidate pages failed
- ... and 69 more

## Output

- `research_group_graph.json` — ResearchGroupGraph per professor (Top 10)
- `NAVIGATION_DEBUG.json` — full navigation decision log per professor
- Precision-first extraction: false positives rejected over false negatives
- PR17: multi-page discovery merges up to 3 candidate pages per professor

Total graphs written: **100**
