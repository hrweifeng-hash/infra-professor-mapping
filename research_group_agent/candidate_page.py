"""PR19 — CandidatePage discovery and ranking.

Expands member page discovery beyond the three node types used in PR17/18
(LAB_PAGE, RESEARCH_GROUP_PAGE, PEOPLE_PAGE) to cover all HomepageGraph nodes
plus the canonical homepage itself, with fine-grained detection of Students,
Members, Team, Alumni, and Projects pages.

PR22 addition: NavigationGuard
  Penalises candidates that are likely wrong-navigation targets (collaborator
  homepages, department directories, publication/teaching/CV pages, GitHub
  product pages).  Uses structural URL signals only — no hardcoded names.

PR25 addition: Navigation Quality Improvement
  NavigationGuard expanded with stronger additive penalties; CandidatePageRanker
  applies configurable positive-signal bonuses and guard penalties with full
  explainability logging (base / bonus / penalty / final / matched rules).

PR30 addition: Navigation Evidence Ranking
  NavigationEvidence captures ownership and member-content signals from parsed
  HTML (MemberPageParser only — no MemberExtractor).  CandidatePageRanker
  combines page-type, ownership, member evidence, anchor bonus, graph confidence,
  and directory penalties into a deterministic score.

Public API:
  CandidatePage              – value object describing one ranked candidate
  CandidatePageGenerator     – enumerate candidates from a HomepageGraph
  CandidatePageRanker        – score and return the top-N with evidence
  NavigationGuard            – wrong-navigation penalty heuristics
  NavigationEvidence         – lightweight ownership + member-content signals
  NavigationEvidenceAnalyzer – build evidence from HTML or URL heuristics
  RankingBonusConfig         – configurable additive ranking bonuses
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from homepage_agent.models import FetchStatus, HomepageGraph, NodeCategory

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Page-type constants
# ─────────────────────────────────────────────────────────────────────────────

PAGE_TYPE_HOMEPAGE = "homepage"
PAGE_TYPE_PEOPLE = "people"
PAGE_TYPE_MEMBERS = "members"
PAGE_TYPE_STUDENTS = "students"
PAGE_TYPE_TEAM = "team"
PAGE_TYPE_LAB = "lab"
PAGE_TYPE_LAB_HOME = "lab_home"
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
    ("lab home", PAGE_TYPE_LAB_HOME),
    ("lab homepage", PAGE_TYPE_LAB_HOME),
    ("lab member", PAGE_TYPE_LAB),
    ("research group", PAGE_TYPE_GROUP),
    ("group", PAGE_TYPE_GROUP),
)

# Base score for each page type used by CandidatePageRanker (0–1 scale)
# PR32: LAB_HOME ranks above team/members; professor homepage boosted via
# PR22 homepage preference when member content is detected (base stays low).
_PAGE_TYPE_PRIORITY: dict[str, float] = {
    PAGE_TYPE_LAB: 0.90,
    PAGE_TYPE_LAB_HOME: 0.88,
    PAGE_TYPE_GROUP: 0.86,
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
# PR30: Navigation evidence models
# ─────────────────────────────────────────────────────────────────────────────

class NavigationOwnership(str, Enum):
    """Estimated page ownership for ranking."""

    PROFESSOR_HOMEPAGE = "professor"
    PROFESSOR_SUBPAGE = "professor_subpage"
    LAB_HOMEPAGE = "lab"
    DEPARTMENT = "department"
    UNIVERSITY = "university"
    UNKNOWN = "unknown"


_OWNERSHIP_SCORES: dict[NavigationOwnership, float] = {
    NavigationOwnership.PROFESSOR_HOMEPAGE: 0.40,
    NavigationOwnership.PROFESSOR_SUBPAGE: 0.35,
    NavigationOwnership.LAB_HOMEPAGE: 0.20,
    NavigationOwnership.DEPARTMENT: -0.30,
    NavigationOwnership.UNIVERSITY: -0.60,
    NavigationOwnership.UNKNOWN: 0.0,
}

# Section-heading keywords that indicate current member rosters.
_CURRENT_MEMBER_KEYWORDS: tuple[str, ...] = (
    "current students",
    "current student",
    "phd students",
    "ph.d. students",
    "phd student",
    "graduate students",
    "postdocs",
    "postdoctoral",
    "group members",
    "research team",
    "lab members",
    "team members",
    "current members",
)

# Title / visible-text patterns suggesting institution-wide directories.
_DIRECTORY_TITLE_PATTERNS: tuple[str, ...] = (
    "faculty directory",
    "faculty listing",
    "all faculty",
    "department directory",
    "people directory",
    "staff directory",
    "university directory",
    "our faculty",
    "faculty and staff",
)

# URL path segments suggesting department / university landing pages.
_DEPARTMENT_PATH_HINTS: tuple[str, ...] = (
    "/faculty?",
    "/faculty-listing",
    "/all-faculty",
    "/people/faculty",
    "/people/staff",
    "/people/directory",
    "/directory/faculty",
    "/directory/people",
    "/department",
    "/dept/",
    "/academics",
    "/admissions",
    "/undergraduate",
    "/graduate-program",
)

_UNIVERSITY_PATH_HINTS: tuple[str, ...] = (
    "/about-us",
    "/about/",
    "/university",
    "/college/",
    "/school-of-",
)

_PERSONAL_PATH_HINTS: tuple[str, ...] = (
    "/~",
    "/homes/",
    "/home/",
    "/users/",
    "/people/",
)

_LAB_PATH_HINTS: tuple[str, ...] = (
    "/lab",
    "/group",
    "research-group",
    "research_group",
    "/team",
    "/members",
    "/students",
)

_GITHUB_REPO_ROOT_RE = re.compile(
    r"^https?://github\.com/[^/]+/?$",
    re.IGNORECASE,
)

_TEMPLATE_PAGE_HINTS: tuple[str, ...] = (
    "template",
    "placeholder",
    "under construction",
    "coming soon",
)

_CACHE_DIRS: tuple[Path, ...] = (
    Path("data/cache/research_groups"),
    Path("data/cache/homepages"),
)


def _cache_key(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def _read_cached_html(url: str) -> str | None:
    """Return cached HTML for *url* when available (no network)."""
    normalized = (url or "").strip()
    if not normalized:
        return None
    if not normalized.startswith(("http://", "https://")):
        normalized = f"https://{normalized}"
    key = _cache_key(normalized)
    for cache_dir in _CACHE_DIRS:
        html_path = cache_dir / f"{key}.html"
        if html_path.exists():
            return html_path.read_text(encoding="utf-8", errors="replace")
    return None


@dataclass
class NavigationEvidence:
    """
    Lightweight ownership and member-content signals for candidate ranking.

    Built from parsed HTML (MemberPageParser) when available, supplemented
    by URL / anchor heuristics.  Does NOT invoke MemberExtractor.
    """

    ownership: NavigationOwnership = NavigationOwnership.UNKNOWN
    member_sections: int = 0
    repeated_profiles: int = 0
    heading_cards: int = 0
    paragraph_members: int = 0
    current_student_keywords: int = 0
    is_directory_page: bool = False
    directory_reason: str = ""
    html_available: bool = False

    @property
    def total_member_signals(self) -> int:
        return (
            self.member_sections
            + min(self.repeated_profiles, 12)
            + min(self.heading_cards, 12)
            + min(self.paragraph_members, 12)
            + self.current_student_keywords
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ownership": self.ownership.value,
            "member_sections": self.member_sections,
            "repeated_profiles": self.repeated_profiles,
            "heading_cards": self.heading_cards,
            "paragraph_members": self.paragraph_members,
            "current_student_keywords": self.current_student_keywords,
            "total_member_signals": self.total_member_signals,
            "is_directory_page": self.is_directory_page,
            "directory_reason": self.directory_reason,
            "html_available": self.html_available,
        }


class NavigationEvidenceAnalyzer:
    """
    Build NavigationEvidence from HTML and/or URL context.

    Uses MemberPageParser for structural member signals when HTML is supplied.
    Falls back to URL / anchor heuristics for ownership when HTML is absent.
    """

    def analyze(
        self,
        *,
        url: str,
        professor_homepage: str | None = None,
        anchor_text: str = "",
        page_type: str = "",
        html: str | None = None,
    ) -> NavigationEvidence:
        evidence = NavigationEvidence()
        url_lower = url.lower()
        path_lower = urlparse(url).path.lower()
        anchor_lower = anchor_text.lower()
        homepage_norm = (professor_homepage or "").rstrip("/").lower()
        url_norm = url.rstrip("/").lower()

        if html:
            evidence = self._enrich_from_html(evidence, html, url)

        evidence.is_directory_page, evidence.directory_reason = self._detect_directory(
            url_lower=url_lower,
            path_lower=path_lower,
            anchor_lower=anchor_lower,
            evidence=evidence,
            html=html,
            professor_homepage=professor_homepage,
        )
        evidence.ownership = self._infer_ownership(
            url_lower=url_lower,
            path_lower=path_lower,
            anchor_lower=anchor_lower,
            page_type=page_type,
            homepage_norm=homepage_norm,
            url_norm=url_norm,
            evidence=evidence,
        )
        return evidence

    def _enrich_from_html(
        self,
        evidence: NavigationEvidence,
        html: str,
        url: str,
    ) -> NavigationEvidence:
        from research_group_agent.models import MemberStatus
        from research_group_agent.parser import MemberPageParser

        evidence.html_available = True
        try:
            parsed = MemberPageParser().parse(html, base_url=url)
        except Exception:  # noqa: BLE001
            return evidence

        evidence.member_sections = sum(
            1
            for section in parsed.sections
            if section.is_member_section
            and section.member_status == MemberStatus.CURRENT
            and section.entry_count > 0
        )
        evidence.repeated_profiles = len(parsed.repeated_profiles)
        evidence.heading_cards = parsed.heading_card_count
        evidence.paragraph_members = parsed.paragraph_member_count

        keyword_hits = 0
        for section in parsed.sections:
            name_lower = section.name.lower()
            if any(kw in name_lower for kw in _CURRENT_MEMBER_KEYWORDS):
                keyword_hits += 1
        visible_lower = (parsed.visible_text or "").lower()
        for kw in _CURRENT_MEMBER_KEYWORDS:
            if kw in visible_lower:
                keyword_hits += 1
        evidence.current_student_keywords = min(keyword_hits, 8)
        return evidence

    def _infer_ownership(
        self,
        *,
        url_lower: str,
        path_lower: str,
        anchor_lower: str,
        page_type: str,
        homepage_norm: str,
        url_norm: str,
        evidence: NavigationEvidence,
    ) -> NavigationOwnership:
        if homepage_norm and url_norm == homepage_norm:
            return NavigationOwnership.PROFESSOR_HOMEPAGE

        parsed = urlparse(url_lower)
        homepage_parsed = urlparse(homepage_norm) if homepage_norm else None
        same_host = bool(
            homepage_parsed
            and parsed.netloc
            and homepage_parsed.netloc
            and parsed.netloc == homepage_parsed.netloc
        )

        if _GITHUB_REPO_ROOT_RE.match(url_lower.rstrip("/")):
            return NavigationOwnership.UNKNOWN

        if same_host and page_type in {
            PAGE_TYPE_MEMBERS,
            PAGE_TYPE_STUDENTS,
            PAGE_TYPE_PEOPLE,
            PAGE_TYPE_TEAM,
            PAGE_TYPE_LAB,
            PAGE_TYPE_LAB_HOME,
            PAGE_TYPE_GROUP,
        }:
            if not evidence.is_directory_page:
                if page_type in {PAGE_TYPE_LAB, PAGE_TYPE_LAB_HOME, PAGE_TYPE_GROUP}:
                    return NavigationOwnership.LAB_HOMEPAGE
                return NavigationOwnership.PROFESSOR_SUBPAGE

        if any(hint in path_lower or hint in url_lower for hint in _UNIVERSITY_PATH_HINTS):
            if evidence.total_member_signals < 3:
                return NavigationOwnership.UNIVERSITY

        if evidence.is_directory_page or any(
            hint in path_lower or hint in url_lower for hint in _DEPARTMENT_PATH_HINTS
        ):
            if evidence.total_member_signals < 4:
                return NavigationOwnership.DEPARTMENT

        if homepage_parsed and parsed.netloc and homepage_parsed.netloc:
            hp_path = homepage_parsed.path.rstrip("/")
            is_personal_homepage = any(h in hp_path for h in _PERSONAL_PATH_HINTS)
            if is_personal_homepage and parsed.netloc == homepage_parsed.netloc:
                if path_lower.startswith(hp_path) and url_norm != homepage_norm:
                    return NavigationOwnership.PROFESSOR_SUBPAGE
                if any(h in path_lower for h in _PERSONAL_PATH_HINTS):
                    return NavigationOwnership.PROFESSOR_SUBPAGE

        if any(h in path_lower for h in _PERSONAL_PATH_HINTS):
            if page_type in {
                PAGE_TYPE_HOMEPAGE,
                PAGE_TYPE_MEMBERS,
                PAGE_TYPE_STUDENTS,
                PAGE_TYPE_PEOPLE,
                PAGE_TYPE_TEAM,
            }:
                return NavigationOwnership.PROFESSOR_SUBPAGE

        if any(h in path_lower or h in anchor_lower for h in _LAB_PATH_HINTS):
            if evidence.total_member_signals >= 2 or page_type in {
                PAGE_TYPE_LAB,
                PAGE_TYPE_GROUP,
                PAGE_TYPE_MEMBERS,
                PAGE_TYPE_STUDENTS,
                PAGE_TYPE_TEAM,
                PAGE_TYPE_PEOPLE,
            }:
                return NavigationOwnership.LAB_HOMEPAGE

        if page_type in {PAGE_TYPE_LAB, PAGE_TYPE_GROUP} and evidence.total_member_signals >= 2:
            return NavigationOwnership.LAB_HOMEPAGE

        if evidence.total_member_signals >= 4 and page_type != PAGE_TYPE_OTHER:
            return NavigationOwnership.LAB_HOMEPAGE

        return NavigationOwnership.UNKNOWN

    def _detect_directory(
        self,
        *,
        url_lower: str,
        path_lower: str,
        anchor_lower: str,
        evidence: NavigationEvidence,
        html: str | None,
        professor_homepage: str | None = None,
    ) -> tuple[bool, str]:
        homepage_parsed = urlparse((professor_homepage or "").lower())
        page_parsed = urlparse(url_lower)
        same_host = bool(
            homepage_parsed.netloc
            and page_parsed.netloc
            and homepage_parsed.netloc == page_parsed.netloc
        )

        if same_host and evidence.total_member_signals >= 2:
            return False, ""

        if any(hint in path_lower or hint in url_lower for hint in _DEPARTMENT_PATH_HINTS):
            if evidence.total_member_signals < 4:
                return True, "department_path"

        normalized = path_lower.rstrip("/")
        if normalized.endswith("/directory") or normalized == "/directory":
            if evidence.total_member_signals < 4:
                return True, "generic_directory"

        combined = f"{path_lower} {anchor_lower}"
        if "/people" in path_lower and not any(
            kw in combined for kw in _MEMBER_SIGNAL_KEYWORDS
        ):
            if evidence.total_member_signals < 3 and not same_host:
                return True, "people_without_members"

        if html:
            html_lower = html.lower()
            if any(pat in html_lower for pat in _DIRECTORY_TITLE_PATTERNS):
                if evidence.total_member_signals < 5:
                    return True, "directory_title"
            if any(pat in html_lower for pat in _TEMPLATE_PAGE_HINTS):
                if evidence.total_member_signals < 2:
                    return True, "template_page"

        return False, ""


def _compute_member_evidence_score(evidence: NavigationEvidence) -> float:
    """Convert member-content signals into a bounded additive score."""
    score = 0.0
    score += min(evidence.member_sections * 0.05, 0.15)
    score += min(max(evidence.repeated_profiles - 2, 0) * 0.03, 0.12)
    score += min(max(evidence.heading_cards - 2, 0) * 0.04, 0.12)
    score += min(max(evidence.paragraph_members - 2, 0) * 0.03, 0.09)
    score += min(evidence.current_student_keywords * 0.05, 0.15)
    if evidence.total_member_signals >= 6:
        score += 0.05
    return round(min(score, 0.35), 3)


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
    navigation_evidence: NavigationEvidence | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "url": self.url,
            "page_type": self.page_type,
            "anchor_text": self.anchor_text,
            "score": round(self.score, 3),
            "evidence": list(self.evidence),
            "source_node_type": self.source_node_type,
            "graph_confidence": round(self.graph_confidence, 3),
        }
        if self.navigation_evidence is not None:
            result["navigation_evidence"] = self.navigation_evidence.to_dict()
        return result


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
# PR25: Configurable ranking bonuses
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class RankingBonusConfig:
    """
    Configurable additive bonuses for member-relevant URL and anchor signals.

    Bonuses are checked in priority order (longer phrases first); the first
    match in each category (URL, anchor) contributes to the total bonus, which
    is capped at *max_total_bonus*.
    """

    url_bonuses: tuple[tuple[str, float], ...] = (
        ("research group", 0.25),
        ("research-group", 0.25),
        ("research_group", 0.25),
        ("current members", 0.25),
        ("graduate students", 0.22),
        ("phd students", 0.22),
        ("phd student", 0.22),
        ("people", 0.25),
        ("members", 0.22),
        ("students", 0.20),
        ("group", 0.18),
        ("lab", 0.18),
        ("team", 0.15),
    )
    anchor_bonuses: tuple[tuple[str, float], ...] = (
        ("research group", 0.25),
        ("current members", 0.25),
        ("graduate students", 0.22),
        ("phd students", 0.22),
        ("phd student", 0.22),
        ("current member", 0.20),
        ("people", 0.20),
        ("members", 0.20),
        ("students", 0.18),
        ("group", 0.15),
        ("lab", 0.15),
        ("team", 0.12),
    )
    max_total_bonus: float = 0.35


# ─────────────────────────────────────────────────────────────────────────────
# CandidatePageRanker
# ─────────────────────────────────────────────────────────────────────────────

class CandidatePageRanker:
    """
    Score and rank CandidatePages using deterministic, explainable rules.

    PR30 scoring model (capped at 1.0):
      page_type_score   = page-type priority
      ownership_score   = NavigationEvidence ownership weight
      member_evidence   = parsed member-content signals
      anchor_score      = configurable URL / anchor bonuses
      graph_score       = graph-confidence bonus
      directory_penalty = NavigationGuard + semantic directory penalties
      final = sum(above) − directory_penalty

    When *enable_navigation_evidence* is True (default), the ranker builds
    NavigationEvidence from cached HTML (when available) or URL heuristics.
    Pass *html_by_url* or *html_provider* to supply HTML explicitly.
    Set to False to restore PR25-only scoring.

    Every candidate is logged at INFO with component scores and matched rules.
    """

    _DIRECTORY_EVIDENCE_PENALTY = 0.25

    def __init__(
        self,
        navigation_guard: NavigationGuard | None = None,
        bonus_config: RankingBonusConfig | None = None,
        enable_navigation_evidence: bool = True,
        evidence_analyzer: NavigationEvidenceAnalyzer | None = None,
        html_provider: Callable[[str], str | None] | None = None,
    ):
        self.navigation_guard = navigation_guard or NavigationGuard()
        self.bonus_config = bonus_config or RankingBonusConfig()
        self.enable_navigation_evidence = enable_navigation_evidence
        self.evidence_analyzer = evidence_analyzer or NavigationEvidenceAnalyzer()
        self._html_provider = html_provider

    def rank(
        self,
        candidates: list[CandidatePage],
        top_n: int = DEFAULT_RANKER_TOP_N,
        min_score: float = _MIN_SCORE,
        professor_homepage: str | None = None,
        html_by_url: dict[str, str] | None = None,
    ) -> list[CandidatePage]:
        """
        Score every candidate, filter by min_score, deduplicate, and return
        the top *top_n* results sorted by score descending.
        """
        homepage = professor_homepage or self._infer_professor_homepage(candidates)
        scored = [
            self._score(
                c,
                professor_homepage=homepage,
                html_by_url=html_by_url,
            )
            for c in candidates
        ]
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

    @classmethod
    def _infer_professor_homepage(cls, candidates: list[CandidatePage]) -> str | None:
        for candidate in candidates:
            if candidate.page_type == PAGE_TYPE_HOMEPAGE:
                return candidate.url
        for candidate in candidates:
            if candidate.graph_confidence >= 1.0:
                return candidate.url
        return None

    def _resolve_html(
        self,
        url: str,
        html_by_url: dict[str, str] | None,
    ) -> str | None:
        if html_by_url:
            key = url.rstrip("/")
            if key in html_by_url:
                return html_by_url[key]
            for cached_url, html in html_by_url.items():
                if cached_url.rstrip("/") == key:
                    return html

        if self._html_provider is not None:
            return self._html_provider(url)

        if not self.enable_navigation_evidence:
            return None

        cached = _read_cached_html(url)
        if cached:
            return cached

        return None

    def _resolve_evidence(
        self,
        candidate: CandidatePage,
        professor_homepage: str | None,
        html_by_url: dict[str, str] | None,
    ) -> NavigationEvidence:
        if candidate.navigation_evidence is not None:
            return candidate.navigation_evidence

        if not self.enable_navigation_evidence:
            return NavigationEvidence()

        html = self._resolve_html(candidate.url, html_by_url)
        return self.evidence_analyzer.analyze(
            url=candidate.url,
            professor_homepage=professor_homepage,
            anchor_text=candidate.anchor_text,
            page_type=candidate.page_type,
            html=html,
        )

    def _compute_bonus(
        self,
        url_lower: str,
        path_lower: str,
        anchor_lower: str,
    ) -> tuple[float, list[str]]:
        """Return (total_bonus, matched_rule_labels)."""
        bonus = 0.0
        matched: list[str] = []

        for kw, amount in self.bonus_config.url_bonuses:
            if kw in url_lower or kw in path_lower:
                bonus += amount
                matched.append(f"url:{kw}")
                break

        for kw, amount in self.bonus_config.anchor_bonuses:
            if kw in anchor_lower:
                bonus += amount
                matched.append(f"anchor:{kw}")
                break

        capped = min(bonus, self.bonus_config.max_total_bonus)
        return round(capped, 3), matched

    def _score(
        self,
        candidate: CandidatePage,
        *,
        professor_homepage: str | None = None,
        html_by_url: dict[str, str] | None = None,
    ) -> CandidatePage:
        evidence: list[str] = []
        url_lower = candidate.url.lower()
        path_lower = urlparse(candidate.url).path.lower()
        anchor_lower = candidate.anchor_text.lower()

        nav_evidence = self._resolve_evidence(
            candidate,
            professor_homepage=professor_homepage,
            html_by_url=html_by_url,
        )

        # Page-type base score
        type_score = _PAGE_TYPE_PRIORITY.get(candidate.page_type, 0.15)
        evidence.append(f"type:{candidate.page_type}:{type_score:.2f}")

        # PR30 ownership score (dominates URL heuristics when HTML available)
        ownership_score = _OWNERSHIP_SCORES.get(nav_evidence.ownership, 0.0)
        evidence.append(
            f"ownership:{nav_evidence.ownership.value}:{ownership_score:+.2f}"
        )

        # PR30 member-content evidence from parsed HTML
        member_evidence_score = 0.0
        if self.enable_navigation_evidence:
            member_evidence_score = _compute_member_evidence_score(nav_evidence)
            if member_evidence_score > 0:
                evidence.append(
                    f"member_evidence:signals={nav_evidence.total_member_signals}:"
                    f"+{member_evidence_score:.2f}"
                )
            if nav_evidence.html_available:
                evidence.append("nav_evidence:html_parsed")

        # Graph confidence bonus
        graph_score = round(candidate.graph_confidence * 0.10, 3)
        if graph_score > 0:
            evidence.append(f"graph_confidence:{candidate.graph_confidence:.2f}")

        # PR25 positive-signal anchor / URL bonuses
        anchor_score, bonus_rules = self._compute_bonus(url_lower, path_lower, anchor_lower)
        for rule in bonus_rules:
            evidence.append(f"rank_bonus:{rule}")

        # NavigationGuard URL penalties + PR30 semantic directory penalty
        guard_penalty, penalty_rules = self.navigation_guard.compute_penalty(
            candidate,
            navigation_evidence=nav_evidence if self.enable_navigation_evidence else None,
        )
        directory_penalty = 0.0
        if self.enable_navigation_evidence and nav_evidence.is_directory_page:
            directory_penalty = self._DIRECTORY_EVIDENCE_PENALTY
            penalty_rules = list(penalty_rules) + [
                f"nav_evidence:directory:{nav_evidence.directory_reason}"
            ]
        for rule in penalty_rules:
            evidence.append(rule)

        total_penalty = round(guard_penalty + directory_penalty, 3)
        final = max(
            0.0,
            min(
                1.0,
                type_score
                + ownership_score
                + member_evidence_score
                + anchor_score
                + graph_score
                - total_penalty,
            ),
        )
        final = round(final, 3)

        label = urlparse(candidate.url).path.rstrip("/").split("/")[-1] or "homepage"
        if not label.endswith(".html") and "." not in label:
            label = label + ".html" if label else candidate.url
        rules_summary = ", ".join(bonus_rules + penalty_rules) or "none"
        log_prefix = "[PR30]" if self.enable_navigation_evidence else "[PR25]"
        logger.info(
            "%s %s\n"
            "  type=%.2f ownership=%+.2f member_evidence=+%.2f\n"
            "  anchor=+%.2f graph=+%.2f penalty=-%.2f\n"
            "  final=%.2f\n"
            "  rules=%s",
            log_prefix,
            label,
            type_score,
            ownership_score,
            member_evidence_score,
            anchor_score,
            graph_score,
            total_penalty,
            final,
            rules_summary,
        )
        evidence.append(f"rank_type:{type_score:.2f}")
        evidence.append(f"rank_ownership:{ownership_score:+.2f}")
        evidence.append(f"rank_member_evidence:+{member_evidence_score:.2f}")
        evidence.append(f"rank_anchor:+{anchor_score:.2f}")
        evidence.append(f"rank_graph:+{graph_score:.2f}")
        evidence.append(f"rank_penalty:-{total_penalty:.2f}")
        evidence.append(f"rank_final:{final:.2f}")

        return CandidatePage(
            url=candidate.url,
            page_type=candidate.page_type,
            anchor_text=candidate.anchor_text,
            score=final,
            evidence=evidence,
            source_node_type=candidate.source_node_type,
            graph_confidence=candidate.graph_confidence,
            navigation_evidence=nav_evidence,
        )


# ─────────────────────────────────────────────────────────────────────────────
# PR22/PR25: NavigationGuard
# ─────────────────────────────────────────────────────────────────────────────

# Human-readable labels for navigation guard rejection categories
_GUARD_REJECTION_LABELS: dict[str, str] = {
    "teaching_page": "Teaching/course page",
    "cv_page": "CV or resume page",
    "publications_page": "Publications-only page",
    "github_product": "GitHub product page",
    "dept_directory": "Department directory",
    "faculty_directory": "Faculty directory",
    "staff_page": "Staff listing page",
    "administration_page": "Administration page",
    "general_department": "General department page",
    "people_without_members": "People listing without member keywords",
    "collaborator_personal": "Likely collaborator homepage",
}

# Member-relevant keywords that exempt a /people URL from the generic penalty
_MEMBER_SIGNAL_KEYWORDS: tuple[str, ...] = (
    "members", "students", "group", "lab", "team", "phd", "graduate",
    "current", "research-group", "research_group",
)


class NavigationGuard:
    """
    PR22/PR25 — wrong-navigation penalty heuristics for candidate ranking.

    Applies additive score penalties to candidates that are likely
    wrong-navigation targets.  Uses structural URL and anchor signals only;
    does NOT use hardcoded professor names.

    PR25 expands patterns for faculty, directory, staff, administration,
    people listings without member keywords, teaching, publications, CV,
    GitHub product pages, and general department pages.

    Penalty model (PR25)
    --------------------
    Penalties are additive subtractions from the candidate score.  The guard
    never removes candidates — downstream components still see penalised
    entries with reduced scores.

    Primary API
    -----------
    compute_penalty(candidate) → (penalty_amount, evidence_rules)
    filter(candidates)         → apply penalties to pre-scored candidates
    """

    # (url_pattern, category) checked in order; first match wins
    _REJECT_PATTERNS: tuple[tuple[str, str], ...] = (
        # Teaching / course pages
        ("/teaching", "teaching_page"),
        ("/courses", "teaching_page"),
        ("/course/", "teaching_page"),
        ("/class/", "teaching_page"),
        ("/lectures", "teaching_page"),
        ("lecture-notes", "teaching_page"),
        ("/syllabus", "teaching_page"),
        ("/syllabi", "teaching_page"),
        # CV / resume pages
        ("/cv", "cv_page"),
        ("/resume", "cv_page"),
        ("/vita", "cv_page"),
        ("/curriculum-vitae", "cv_page"),
        # Publication-only pages
        ("/publications", "publications_page"),
        ("/papers", "publications_page"),
        ("/pubs", "publications_page"),
        ("/publication-list", "publications_page"),
        ("/research-interests", "publications_page"),
        ("/research_interests", "publications_page"),
        # GitHub product / marketing pages (not personal repos)
        ("github.com/features", "github_product"),
        ("github.com/pricing", "github_product"),
        ("github.com/enterprise", "github_product"),
        ("github.com/about", "github_product"),
        ("github.com/explore", "github_product"),
        ("github.com/topics", "github_product"),
        ("github.com/solutions", "github_product"),
        # Faculty / department directory patterns
        ("/faculty?", "faculty_directory"),
        ("facultytype=", "faculty_directory"),
        ("/people/faculty", "faculty_directory"),
        ("/faculty-listing", "faculty_directory"),
        ("/all-faculty", "faculty_directory"),
        ("/staff/", "staff_page"),
        ("/administration", "administration_page"),
        ("/admin/", "administration_page"),
        ("/academics", "general_department"),
        ("/admissions", "general_department"),
        ("/ugrad/", "general_department"),
        ("/undergraduate", "general_department"),
        ("/graduate-program", "general_department"),
        ("/grad-program", "general_department"),
        ("/department", "general_department"),
        ("/dept/", "general_department"),
    )

    # PR25: additive penalty amounts per category (configurable via subclass)
    _PENALTY_AMOUNTS: dict[str, float] = {
        "teaching_page": 0.40,
        "cv_page": 0.35,
        "publications_page": 0.35,
        "github_product": 0.45,
        "dept_directory": 0.40,
        "faculty_directory": 0.40,
        "staff_page": 0.35,
        "administration_page": 0.35,
        "general_department": 0.30,
        "people_without_members": 0.25,
        "collaborator_personal": 0.35,
    }

    def compute_penalty(
        self,
        candidate: CandidatePage,
        navigation_evidence: NavigationEvidence | None = None,
    ) -> tuple[float, list[str]]:
        """
        Return (additive_penalty_amount, evidence_rule_strings) for *candidate*.

        The penalty is subtracted from the score by CandidatePageRanker.
        When *navigation_evidence* is supplied (PR30), semantic directory
        signals can add an extra penalty beyond URL pattern matching.
        Returns (0.0, []) when no penalty applies.
        """
        penalty_info = self._check_penalty(candidate)
        rules: list[str] = []
        amount = 0.0

        if penalty_info is not None:
            category, matched_pattern = penalty_info
            amount = self._PENALTY_AMOUNTS.get(category, 0.30)
            label = _GUARD_REJECTION_LABELS.get(category, category)
            rules.append(f"nav_guard:{category}:{matched_pattern}")
            logger.info(
                "[PR25] NavigationGuard penalty: %s (pattern=%s, penalty=-%.2f) for %s",
                label,
                matched_pattern,
                amount,
                candidate.url,
            )

        if navigation_evidence is not None:
            semantic_penalty, semantic_rules = self._semantic_penalty(navigation_evidence)
            amount += semantic_penalty
            rules.extend(semantic_rules)

        return round(amount, 3), rules

    def _semantic_penalty(
        self,
        evidence: NavigationEvidence,
    ) -> tuple[float, list[str]]:
        """PR30 — extra penalties from parsed page semantics."""
        penalty = 0.0
        rules: list[str] = []

        if evidence.ownership == NavigationOwnership.UNIVERSITY:
            penalty += 0.15
            rules.append("nav_evidence:ownership_university")

        if evidence.ownership == NavigationOwnership.DEPARTMENT and evidence.total_member_signals < 3:
            penalty += 0.10
            rules.append("nav_evidence:ownership_department_sparse")

        if evidence.is_directory_page and evidence.total_member_signals >= 5:
            # Large roster pages are almost always department-scale listings.
            penalty += 0.20
            rules.append(
                f"nav_evidence:large_directory:{evidence.total_member_signals}_signals"
            )

        return round(penalty, 3), rules

    def filter(
        self,
        candidates: list[CandidatePage],
    ) -> list[CandidatePage]:
        """
        Apply navigation-guard penalties to a list of pre-scored candidates.

        Returns a new list where penalised candidates have reduced scores and
        explanatory evidence entries.  Candidates that do not match any
        rejection pattern are returned unchanged.  Never removes candidates.
        """
        result: list[CandidatePage] = []
        for candidate in candidates:
            penalty, rules = self.compute_penalty(candidate)
            if penalty <= 0:
                result.append(candidate)
                continue

            new_score = max(0.0, round(candidate.score - penalty, 3))
            result.append(
                CandidatePage(
                    url=candidate.url,
                    page_type=candidate.page_type,
                    anchor_text=candidate.anchor_text,
                    score=new_score,
                    evidence=list(candidate.evidence) + rules,
                    source_node_type=candidate.source_node_type,
                    graph_confidence=candidate.graph_confidence,
                )
            )
        return result

    def _check_penalty(
        self, candidate: CandidatePage
    ) -> tuple[str, str] | None:
        """Return (category, matched_pattern) if the candidate should be penalised."""
        url_lower = candidate.url.lower()
        path_lower = urlparse(candidate.url).path.lower()
        anchor_lower = candidate.anchor_text.lower()

        for pattern, category in self._REJECT_PATTERNS:
            if pattern in url_lower:
                return category, pattern

        if self._is_generic_directory_listing(path_lower):
            return "dept_directory", "/directory"

        if self._is_people_without_members(url_lower, path_lower, anchor_lower):
            return "people_without_members", "/people"

        if self._is_collaborator_personal(path_lower, anchor_lower):
            return "collaborator_personal", "personal_page_structure"

        return None

    @classmethod
    def _is_generic_directory_listing(cls, path_lower: str) -> bool:
        """Penalise bare department directory pages, not member sub-listings."""
        normalized = path_lower.rstrip("/")
        return normalized.endswith("/directory") or normalized == "/directory"

    @classmethod
    def _is_people_without_members(
        cls,
        url_lower: str,
        path_lower: str,
        anchor_lower: str,
    ) -> bool:
        """Penalise /people URLs that lack member-relevant keywords."""
        if "/people" not in path_lower and "/people" not in url_lower:
            return False
        combined = f"{path_lower} {anchor_lower}"
        return not any(kw in combined for kw in _MEMBER_SIGNAL_KEYWORDS)

    @classmethod
    def _is_collaborator_personal(
        cls,
        path_lower: str,
        anchor_lower: str,
    ) -> bool:
        """Penalise URLs that look like another professor's personal page."""
        if "/people/" in path_lower:
            remainder = path_lower.split("/people/", 1)[-1].strip("/")
            if remainder and "/" not in remainder:
                if not any(kw in anchor_lower for kw in _MEMBER_SIGNAL_KEYWORDS):
                    return True
        if "/faculty/" in path_lower and "/directory/faculty/" not in path_lower:
            remainder = path_lower.split("/faculty/", 1)[-1].strip("/")
            if remainder and "/" not in remainder:
                if not any(kw in anchor_lower for kw in _MEMBER_SIGNAL_KEYWORDS):
                    return True
        return False
