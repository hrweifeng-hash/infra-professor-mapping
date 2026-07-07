"""PR19 — CandidatePage discovery and ranking.

Expands member page discovery beyond the three node types used in PR17/18
(LAB_PAGE, RESEARCH_GROUP_PAGE, PEOPLE_PAGE) to cover all HomepageGraph nodes
plus the canonical homepage itself, with fine-grained detection of Students,
Members, Team, Alumni, and Projects pages.

Public API:
  CandidatePage              – value object describing one ranked candidate
  CandidatePageGenerator     – enumerate candidates from a HomepageGraph
  CandidatePageRanker        – score and return the top-N with evidence
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from homepage_agent.models import FetchStatus, HomepageGraph, NodeCategory


# ─────────────────────────────────────────────────────────────────────────────
# Page-type constants
# ─────────────────────────────────────────────────────────────────────────────

PAGE_TYPE_HOMEPAGE = "homepage"
PAGE_TYPE_PEOPLE = "people"
PAGE_TYPE_MEMBERS = "members"
PAGE_TYPE_STUDENTS = "students"
PAGE_TYPE_TEAM = "team"
PAGE_TYPE_LAB = "lab"
PAGE_TYPE_GROUP = "group"
PAGE_TYPE_ALUMNI = "alumni"
PAGE_TYPE_PROJECTS = "projects"
PAGE_TYPE_OTHER = "other"

# Mapping from HomepageGraph NodeCategory → semantic page type
_NODE_TYPE_TO_PAGE_TYPE: dict[str, str] = {
    NodeCategory.HOMEPAGE.value: PAGE_TYPE_HOMEPAGE,
    NodeCategory.PEOPLE_PAGE.value: PAGE_TYPE_PEOPLE,
    NodeCategory.LAB_PAGE.value: PAGE_TYPE_LAB,
    NodeCategory.RESEARCH_GROUP_PAGE.value: PAGE_TYPE_GROUP,
    NodeCategory.PROJECTS_PAGE.value: PAGE_TYPE_PROJECTS,
    NodeCategory.SOFTWARE_PAGE.value: PAGE_TYPE_OTHER,
    NodeCategory.TEACHING_PAGE.value: PAGE_TYPE_OTHER,
    NodeCategory.NEWS_PAGE.value: PAGE_TYPE_OTHER,
    NodeCategory.CONTACT_PAGE.value: PAGE_TYPE_OTHER,
    NodeCategory.PUBLICATIONS_PAGE.value: PAGE_TYPE_OTHER,
}

# URL path patterns → page_type (checked in priority order; first match wins)
_URL_TYPE_HINTS: tuple[tuple[str, str], ...] = (
    ("alumni", PAGE_TYPE_ALUMNI),
    ("former", PAGE_TYPE_ALUMNI),
    ("graduates", PAGE_TYPE_ALUMNI),
    ("past-member", PAGE_TYPE_ALUMNI),
    ("past_member", PAGE_TYPE_ALUMNI),
    ("students", PAGE_TYPE_STUDENTS),
    ("student", PAGE_TYPE_STUDENTS),
    ("/phd", PAGE_TYPE_STUDENTS),
    ("members", PAGE_TYPE_MEMBERS),
    ("/people", PAGE_TYPE_PEOPLE),
    ("/team", PAGE_TYPE_TEAM),
    ("/group", PAGE_TYPE_GROUP),
    ("/lab", PAGE_TYPE_LAB),
    ("research-group", PAGE_TYPE_GROUP),
    ("research_group", PAGE_TYPE_GROUP),
)

# Anchor text patterns → page_type (checked in priority order; first match wins)
_ANCHOR_TYPE_HINTS: tuple[tuple[str, str], ...] = (
    ("alumni", PAGE_TYPE_ALUMNI),
    ("former student", PAGE_TYPE_ALUMNI),
    ("former member", PAGE_TYPE_ALUMNI),
    ("past student", PAGE_TYPE_ALUMNI),
    ("graduated", PAGE_TYPE_ALUMNI),
    ("current student", PAGE_TYPE_STUDENTS),
    ("phd student", PAGE_TYPE_STUDENTS),
    ("ph.d. student", PAGE_TYPE_STUDENTS),
    ("students", PAGE_TYPE_STUDENTS),
    ("current member", PAGE_TYPE_MEMBERS),
    ("members", PAGE_TYPE_MEMBERS),
    ("people", PAGE_TYPE_PEOPLE),
    ("team", PAGE_TYPE_TEAM),
    ("our lab", PAGE_TYPE_LAB),
    ("lab member", PAGE_TYPE_LAB),
    ("research group", PAGE_TYPE_GROUP),
    ("group", PAGE_TYPE_GROUP),
)

# Base score for each page type used by CandidatePageRanker (0–1 scale)
_PAGE_TYPE_PRIORITY: dict[str, float] = {
    PAGE_TYPE_LAB: 0.90,
    PAGE_TYPE_GROUP: 0.88,
    PAGE_TYPE_MEMBERS: 0.85,
    PAGE_TYPE_PEOPLE: 0.82,
    PAGE_TYPE_STUDENTS: 0.78,
    PAGE_TYPE_TEAM: 0.75,
    PAGE_TYPE_ALUMNI: 0.60,
    PAGE_TYPE_PROJECTS: 0.45,
    PAGE_TYPE_HOMEPAGE: 0.35,
    PAGE_TYPE_OTHER: 0.15,
}

# Minimum score for a candidate to be returned by CandidatePageRanker
_MIN_SCORE = 0.30

# Default maximum top-N returned by CandidatePageRanker
DEFAULT_RANKER_TOP_N = 5


# ─────────────────────────────────────────────────────────────────────────────
# CandidatePage
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CandidatePage:
    """
    A ranked candidate page for member discovery.

    Attributes:
        url              – absolute URL of the page
        page_type        – semantic type (lab, group, people, students, …)
        anchor_text      – link text that led to this URL (may be empty)
        score            – final ranking score in [0, 1]; higher is better
        evidence         – human-readable list of scoring signals
        source_node_type – HomepageGraph NodeCategory that produced this URL
        graph_confidence – confidence of the source GraphNode (0 if synthetic)
    """

    url: str
    page_type: str
    anchor_text: str = ""
    score: float = 0.0
    evidence: list[str] = field(default_factory=list)
    source_node_type: str = ""
    graph_confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "page_type": self.page_type,
            "anchor_text": self.anchor_text,
            "score": round(self.score, 3),
            "evidence": list(self.evidence),
            "source_node_type": self.source_node_type,
            "graph_confidence": round(self.graph_confidence, 3),
        }


# ─────────────────────────────────────────────────────────────────────────────
# CandidatePageGenerator
# ─────────────────────────────────────────────────────────────────────────────

class CandidatePageGenerator:
    """
    Enumerate candidate pages from a HomepageGraph.

    Covers: Homepage, Students, People, Members, Team, Group, Lab, Alumni,
    Projects and similar pages discovered from ALL graph_nodes (not just the
    three node types used by the legacy navigator).

    Returns an empty list when the HomepageGraph was not fetched successfully.
    Deduplicates candidates by normalized URL.
    """

    def generate(self, homepage_graph: HomepageGraph) -> list[CandidatePage]:
        """
        Return a deduplicated list of candidate pages ordered by discovery.

        The canonical homepage is always the first candidate (if available).
        All graph_nodes follow in graph order.
        """
        if homepage_graph.fetch_status != FetchStatus.SUCCESS:
            return []

        candidates: list[CandidatePage] = []
        seen: set[str] = set()

        # Always offer the canonical homepage as a fallback candidate
        canonical = homepage_graph.canonical_homepage or homepage_graph.homepage_url
        if canonical:
            key = canonical.rstrip("/")
            seen.add(key)
            candidates.append(
                CandidatePage(
                    url=canonical,
                    page_type=PAGE_TYPE_HOMEPAGE,
                    anchor_text="",
                    source_node_type=NodeCategory.HOMEPAGE.value,
                    graph_confidence=1.0,
                )
            )

        # Add every classified graph node (expands to ALL NodeCategory values)
        for node in homepage_graph.graph_nodes:
            key = node.url.rstrip("/")
            if key in seen:
                continue
            seen.add(key)

            page_type = self._infer_page_type(
                node_type=node.node_type,
                url=node.url,
                anchor_text=node.anchor_text or "",
            )
            candidates.append(
                CandidatePage(
                    url=node.url,
                    page_type=page_type,
                    anchor_text=node.anchor_text or "",
                    source_node_type=node.node_type,
                    graph_confidence=node.confidence_value,
                )
            )

        return candidates

    @classmethod
    def _infer_page_type(cls, node_type: str, url: str, anchor_text: str) -> str:
        """
        Infer the semantic page type from node_type, URL patterns, and anchor text.

        URL path patterns are checked before anchor text; node_type is the
        fallback when no pattern matches.
        """
        url_lower = url.lower()
        path_lower = urlparse(url).path.lower()
        anchor_lower = anchor_text.lower()

        for pattern, detected_type in _URL_TYPE_HINTS:
            if pattern in url_lower or pattern in path_lower:
                return detected_type

        for pattern, detected_type in _ANCHOR_TYPE_HINTS:
            if pattern in anchor_lower:
                return detected_type

        return _NODE_TYPE_TO_PAGE_TYPE.get(node_type, PAGE_TYPE_OTHER)


# ─────────────────────────────────────────────────────────────────────────────
# CandidatePageRanker
# ─────────────────────────────────────────────────────────────────────────────

class CandidatePageRanker:
    """
    Score and rank CandidatePages using deterministic, explainable rules.

    Scoring is additive (capped at 1.0):
      1. Page-type priority       — base score determined by semantic type
      2. URL keyword bonus        — +0.15 if URL contains a member-relevant term
      3. Anchor text bonus        — +0.10 if anchor text contains a relevant term
      4. Graph confidence bonus   — +0.10 × graph_confidence from the source node
      5. Department penalty       — −0.25 if URL looks like a department directory

    Only candidates with score ≥ min_score are returned; duplicates are
    removed by normalized URL; results are sorted by score descending.
    """

    _URL_BONUS_KEYWORDS: tuple[str, ...] = (
        "students", "members", "people", "team", "group",
        "lab", "alumni", "research-group", "research_group",
    )
    _ANCHOR_BONUS_KEYWORDS: tuple[str, ...] = (
        "students", "members", "people", "team", "group",
        "lab", "alumni", "research group", "our lab",
    )
    _DEPT_PENALTY_PATTERNS: tuple[str, ...] = (
        "/faculty?", "facultytype=", "/people/faculty",
        "/academics", "/admissions", "/ugrad/",
        "/undergraduate", "/graduate-program",
    )

    def rank(
        self,
        candidates: list[CandidatePage],
        top_n: int = DEFAULT_RANKER_TOP_N,
        min_score: float = _MIN_SCORE,
    ) -> list[CandidatePage]:
        """
        Score every candidate, filter by min_score, deduplicate, and return
        the top *top_n* results sorted by score descending.
        """
        scored = [self._score(c) for c in candidates]
        scored = [c for c in scored if c.score >= min_score]
        scored.sort(key=lambda c: c.score, reverse=True)

        seen: set[str] = set()
        results: list[CandidatePage] = []
        for candidate in scored:
            key = candidate.url.rstrip("/")
            if key not in seen:
                seen.add(key)
                results.append(candidate)
            if len(results) >= top_n:
                break

        return results

    def _score(self, candidate: CandidatePage) -> CandidatePage:
        evidence: list[str] = []
        url_lower = candidate.url.lower()
        path_lower = urlparse(candidate.url).path.lower()
        anchor_lower = candidate.anchor_text.lower()

        # 1. Base score from page-type priority
        type_score = _PAGE_TYPE_PRIORITY.get(candidate.page_type, 0.15)
        evidence.append(f"type:{candidate.page_type}:{type_score:.2f}")

        # 2. URL keyword bonus (max +0.15, first match wins)
        url_bonus = 0.0
        for kw in self._URL_BONUS_KEYWORDS:
            if kw in url_lower or kw in path_lower:
                url_bonus = 0.15
                evidence.append(f"url_keyword:{kw}")
                break

        # 3. Anchor text bonus (max +0.10, first match wins)
        anchor_bonus = 0.0
        for kw in self._ANCHOR_BONUS_KEYWORDS:
            if kw in anchor_lower:
                anchor_bonus = 0.10
                evidence.append(f"anchor_keyword:{kw}")
                break

        # 4. Graph confidence bonus (proportional, max +0.10)
        conf_bonus = round(candidate.graph_confidence * 0.10, 3)
        if conf_bonus > 0:
            evidence.append(f"graph_confidence:{candidate.graph_confidence:.2f}")

        # 5. Department / directory penalty (flat −0.25, first match wins)
        penalty = 0.0
        for pattern in self._DEPT_PENALTY_PATTERNS:
            if pattern in url_lower:
                penalty = 0.25
                evidence.append(f"dept_penalty:{pattern}")
                break

        score = max(0.0, min(1.0, type_score + url_bonus + anchor_bonus + conf_bonus - penalty))
        score = round(score, 3)

        return CandidatePage(
            url=candidate.url,
            page_type=candidate.page_type,
            anchor_text=candidate.anchor_text,
            score=score,
            evidence=evidence,
            source_node_type=candidate.source_node_type,
            graph_confidence=candidate.graph_confidence,
        )
