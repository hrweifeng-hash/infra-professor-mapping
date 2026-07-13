"""M5-PR1 — Multi-level navigation data models.

Deterministic navigation graph models for bounded BFS exploration of
laboratory websites before member extraction.

Public API:
  NavigationNode       – vertex in the navigation graph
  NavigationEdge       – directed link between pages
  NavigationStatistics – exploration counters and aggregates
  VisitStatus          – node visit lifecycle
  normalize_navigation_url – canonical URL key for deduplication
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from urllib.parse import urlparse, urlunparse

FRAMEWORK_VERSION = "M5-PR1"

# Configurable exploration limits (module-level defaults).
MAX_NAVIGATION_DEPTH = 3
MAX_NAVIGATION_PAGES = 150

# Positive anchor-text signals (lower-cased sub-string match).
POSITIVE_ANCHOR_SIGNALS: tuple[str, ...] = (
    "current members",
    "graduate students",
    "phd students",
    "research group",
    "researchers",
    "personnel",
    "directory",
    "members",
    "students",
    "people",
    "group",
    "team",
    "lab",
)

# Positive URL path signals (lower-cased sub-string match).
POSITIVE_URL_SIGNALS: tuple[str, ...] = (
    "people",
    "members",
    "group",
    "team",
    "lab",
    "students",
    "personnel",
    "directory",
)

# Negative anchor/URL signals — links matching these are not followed.
NEGATIVE_SIGNALS: tuple[str, ...] = (
    "admissions",
    "courses",
    "teaching",
    "news",
    "events",
    "publications",
    "cv",
    "jobs",
    "donate",
    "contact",
    "privacy",
    "login",
)

# URL patterns / schemes to ignore entirely.
IGNORE_URL_PATTERNS: tuple[str, ...] = (
    "mailto:",
    "javascript:",
    "tel:",
    "#",
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".svg",
    ".ico",
    ".zip",
    ".tar",
    ".gz",
    "/archive",
    "/archives",
)

_DEFAULT_INDEX_PAGES = frozenset({
    "index.html",
    "index.htm",
    "index.php",
    "index.asp",
    "default.aspx",
    "default.htm",
    "main.html",
})

_DUPLICATE_SLASH_RE = re.compile(r"/{2,}")


class VisitStatus(str, Enum):
    PENDING = "pending"
    VISITED = "visited"
    SKIPPED = "skipped"
    CANDIDATE = "candidate"


@dataclass
class NavigationNode:
    """A page discovered during multi-level navigation."""

    url: str
    parent_url: str | None
    depth: int
    page_type: str
    anchor_text: str = ""
    discovered_from: str = ""
    visit_status: VisitStatus = VisitStatus.PENDING
    normalized_url: str = ""

    def __post_init__(self) -> None:
        if not self.normalized_url:
            self.normalized_url = normalize_navigation_url(self.url)

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "parent_url": self.parent_url,
            "depth": self.depth,
            "page_type": self.page_type,
            "anchor_text": self.anchor_text,
            "discovered_from": self.discovered_from,
            "visit_status": self.visit_status.value,
            "normalized_url": self.normalized_url,
        }


@dataclass
class NavigationEdge:
    """A hyperlink followed (or discovered) during exploration."""

    from_url: str
    to_url: str
    edge_type: str
    anchor_text: str = ""
    depth: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_url": self.from_url,
            "to_url": self.to_url,
            "edge_type": self.edge_type,
            "anchor_text": self.anchor_text,
            "depth": self.depth,
        }


@dataclass
class NavigationStatistics:
    """Aggregate counters produced by NavigationExplorer."""

    pages_visited: int = 0
    pages_skipped: int = 0
    loops_prevented: int = 0
    candidate_pages: int = 0
    maximum_depth: int = 0
    average_branching_factor: float = 0.0
    depth_distribution: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pages_visited": self.pages_visited,
            "pages_skipped": self.pages_skipped,
            "loops_prevented": self.loops_prevented,
            "candidate_pages": self.candidate_pages,
            "maximum_depth": self.maximum_depth,
            "average_branching_factor": round(self.average_branching_factor, 3),
            "depth_distribution": dict(self.depth_distribution),
        }


def normalize_navigation_url(url: str) -> str:
    """
    Canonical URL key for deduplication.

    Removes fragment, duplicate slashes, trailing slash, and default index pages.
    """
    url = (url or "").strip()
    if not url:
        return ""

    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return url.rstrip("/")

    path = _DUPLICATE_SLASH_RE.sub("/", parsed.path or "/")
    path = path.lower()
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    segments = path.rsplit("/", 1)
    if segments[-1].lower() in _DEFAULT_INDEX_PAGES:
        path = "/".join(segments[:-1]) or "/"
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/")

    normalized = urlunparse((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        path,
        "",
        parsed.query,
        "",
    ))
    return normalized.rstrip("/") if normalized.endswith("/") and path != "/" else normalized


def should_ignore_url(url: str) -> bool:
    """Return True when a URL should never be fetched or enqueued."""
    lower = url.lower()
    return any(pattern in lower for pattern in IGNORE_URL_PATTERNS)


def has_negative_signal(url: str, anchor_text: str) -> bool:
    haystack = f"{url} {anchor_text}".lower()
    return any(signal in haystack for signal in NEGATIVE_SIGNALS)


def match_positive_anchor(anchor_text: str) -> str | None:
    anchor = anchor_text.lower().strip()
    for signal in POSITIVE_ANCHOR_SIGNALS:
        if signal in anchor:
            return signal
    return None


def match_positive_url(url: str) -> str | None:
    path = urlparse(url).path.lower()
    haystack = f"{url.lower()} {path}"
    for signal in POSITIVE_URL_SIGNALS:
        if signal in haystack:
            return signal
    return None


def infer_page_type(url: str, anchor_text: str) -> str:
    """Map positive signals to semantic page types used by CandidatePageRanker."""
    from research_group_agent.candidate_page import (
        PAGE_TYPE_GROUP,
        PAGE_TYPE_LAB,
        PAGE_TYPE_MEMBERS,
        PAGE_TYPE_OTHER,
        PAGE_TYPE_PEOPLE,
        PAGE_TYPE_STUDENTS,
        PAGE_TYPE_TEAM,
    )

    path = urlparse(url).path.lower()
    anchor = anchor_text.lower()

    if "student" in path or "student" in anchor:
        return PAGE_TYPE_STUDENTS
    if "member" in path or "member" in anchor:
        return PAGE_TYPE_MEMBERS
    if "people" in path or "people" in anchor or "personnel" in path:
        return PAGE_TYPE_PEOPLE
    if "team" in path or "team" in anchor:
        return PAGE_TYPE_TEAM
    if "research group" in anchor or "research-group" in path or "research_group" in path:
        return PAGE_TYPE_GROUP
    if "group" in path or "group" in anchor:
        return PAGE_TYPE_GROUP
    if "lab" in path or "lab" in anchor:
        return PAGE_TYPE_LAB
    if "directory" in path or "directory" in anchor:
        return PAGE_TYPE_PEOPLE
    return PAGE_TYPE_OTHER


def is_expandable_link(url: str, anchor_text: str) -> bool:
    """Return True when a link should be enqueued for BFS expansion."""
    if should_ignore_url(url):
        return False
    if has_negative_signal(url, anchor_text):
        return False
    return match_positive_anchor(anchor_text) is not None or match_positive_url(url) is not None


def is_candidate_page(url: str, anchor_text: str) -> bool:
    """Return True when a discovered URL is member-relevant enough to rank."""
    if should_ignore_url(url) or has_negative_signal(url, anchor_text):
        return False
    member_signals = (
        "people", "members", "current members", "students",
        "graduate students", "phd students", "researchers",
        "personnel", "directory", "team",
    )
    anchor = anchor_text.lower()
    path = urlparse(url).path.lower()
    for signal in member_signals:
        if signal in anchor or signal in path:
            return True
    return False
