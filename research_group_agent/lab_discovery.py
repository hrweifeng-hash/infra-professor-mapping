"""PR32 — Lab Discovery.

Discover research lab homepages from professor homepage HTML.

Input:  professor homepage HTML
Output: LabCandidate pages (as CandidatePage with page_type=lab_home)

Detection signals:
  - Anchor text: Lab, Laboratory, Research Group, Group, Center, Institute, …
  - Surrounding text: "I lead OrderLab", "member of the NetLab", …
  - Navigation menu items: Lab, Team, People, Members, Researchers, Personnel
  - URL signals: lab, group, center, systems, research, team

Public API:
  LabCandidate    – value object for a discovered lab
  LabDiscovery    – inspect HTML and return CandidatePage objects
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from research_group_agent.candidate_page import (
    CandidatePage,
    PAGE_TYPE_LAB_HOME,
)
from research_group_agent.people_page_discovery import _AllLinksExtractor

SOURCE_NODE_TYPE = "lab_discovery"

# High-confidence lab anchor text patterns (checked in priority order).
_LAB_ANCHOR_PATTERNS: tuple[tuple[str, float], ...] = (
    ("research group", 0.95),
    ("research lab", 0.95),
    ("laboratory", 0.92),
    (" ai lab", 0.90),
    (" ml lab", 0.90),
    ("systems lab", 0.90),
    (" lab", 0.88),
    ("lab ", 0.88),
    ("center", 0.85),
    ("centre", 0.85),
    ("institute", 0.85),
    (" group", 0.82),
    ("group ", 0.82),
)

# Navigation menu signals — high confidence when in nav-like context.
_NAV_ANCHOR_SIGNALS: tuple[str, ...] = (
    "lab",
    "team",
    "people",
    "members",
    "researchers",
    "personnel",
)

# URL path / host sub-strings that increase lab confidence.
_URL_LAB_SIGNALS: tuple[tuple[str, float], ...] = (
    ("orderlab", 0.95),
    ("netlab", 0.95),
    ("symbioticlab", 0.95),
    ("systems", 0.88),
    ("research", 0.82),
    ("center", 0.85),
    ("centre", 0.85),
    ("institute", 0.85),
    ("/lab", 0.90),
    ("lab.", 0.88),
    (".lab.", 0.88),
    ("/group", 0.85),
    ("/team", 0.80),
)

# Surrounding-text patterns indicating lab membership or leadership.
_SURROUNDING_PATTERNS: tuple[str, ...] = (
    "i lead ",
    "i am a member of ",
    "member of the ",
    "director of ",
    "head of ",
    "research group:",
    "our lab",
    "our group",
    "my lab",
    "my group",
)

# Maximum lab candidates per professor homepage.
_MAX_LAB_CANDIDATES = 8

# Minimum confidence to emit a candidate.
_MIN_CONFIDENCE = 0.70


@dataclass
class LabCandidate:
    """A discovered research lab homepage."""

    url: str
    anchor_text: str
    confidence: float
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "anchor_text": self.anchor_text,
            "confidence": round(self.confidence, 3),
            "evidence": list(self.evidence),
        }


class LabDiscovery:
    """
    Discover research lab homepages from professor homepage HTML.

    Returns CandidatePage objects with page_type=PAGE_TYPE_LAB_HOME for
    integration into the existing candidate ranking pipeline.
    """

    def discover(
        self,
        html: str,
        base_url: str,
        *,
        already_seen: set[str] | None = None,
    ) -> list[CandidatePage]:
        """
        Scan *html* for lab links and return deduplicated CandidatePages.

        Args:
            html:         Raw HTML of the professor homepage.
            base_url:     Absolute URL of the homepage (for link resolution).
            already_seen: Normalized URLs already in the candidate pool.
        """
        seen = set(already_seen or set())
        raw_links = _AllLinksExtractor.extract(html, base_url)
        lab_candidates: list[LabCandidate] = []

        for anchor_text, url in raw_links:
            candidate = self._score_link(anchor_text, url, html)
            if candidate is None:
                continue
            key = url.rstrip("/")
            if key in seen:
                continue
            seen.add(key)
            lab_candidates.append(candidate)

        lab_candidates.sort(key=lambda c: c.confidence, reverse=True)
        lab_candidates = lab_candidates[:_MAX_LAB_CANDIDATES]

        return [
            CandidatePage(
                url=lc.url,
                page_type=PAGE_TYPE_LAB_HOME,
                anchor_text=lc.anchor_text,
                source_node_type=SOURCE_NODE_TYPE,
                graph_confidence=lc.confidence,
                evidence=["lab_discovery"] + lc.evidence,
            )
            for lc in lab_candidates
        ]

    def discover_labs(
        self,
        html: str,
        base_url: str,
        *,
        already_seen: set[str] | None = None,
    ) -> list[LabCandidate]:
        """Return raw LabCandidate objects (for reporting / testing)."""
        pages = self.discover(html, base_url, already_seen=already_seen)
        return [
            LabCandidate(
                url=p.url,
                anchor_text=p.anchor_text,
                confidence=p.graph_confidence,
                evidence=list(p.evidence),
            )
            for p in pages
        ]

    def _score_link(
        self,
        anchor_text: str,
        url: str,
        html: str,
    ) -> LabCandidate | None:
        anchor_lower = anchor_text.lower().strip()
        url_lower = url.lower()
        evidence: list[str] = []
        confidence = 0.0

        # Anchor text signals
        for pattern, score in _LAB_ANCHOR_PATTERNS:
            if pattern in anchor_lower or (
                pattern.strip() and pattern.strip() in anchor_lower
            ):
                confidence = max(confidence, score)
                evidence.append(f"anchor:{pattern.strip()}")
                break

        # Navigation menu signals
        if any(signal == anchor_lower or f" {signal}" in f" {anchor_lower}" for signal in _NAV_ANCHOR_SIGNALS):
            nav_boost = 0.82
            if anchor_lower in ("lab", "our lab", "the lab", "research lab"):
                nav_boost = 0.90
            confidence = max(confidence, nav_boost)
            evidence.append(f"nav_signal:{anchor_lower}")

        # URL signals
        for signal, score in _URL_LAB_SIGNALS:
            if signal in url_lower:
                confidence = max(confidence, score)
                evidence.append(f"url:{signal}")
                break

        # Surrounding text context
        if self._has_surrounding_context(html, anchor_text):
            confidence = max(confidence, 0.85)
            evidence.append("surrounding_text")

        if confidence < _MIN_CONFIDENCE:
            return None

        return LabCandidate(
            url=url,
            anchor_text=anchor_text,
            confidence=min(confidence, 1.0),
            evidence=evidence,
        )

    @staticmethod
    def _has_surrounding_context(html: str, anchor_text: str) -> bool:
        """Check whether visible text near the anchor mentions lab membership."""
        if not anchor_text.strip():
            return False

        # Strip tags for coarse text search
        visible = re.sub(r"<[^>]+>", " ", html).lower()
        visible = re.sub(r"\s+", " ", visible)

        anchor_lower = anchor_text.lower().strip()
        if not anchor_lower:
            return False

        idx = visible.find(anchor_lower)
        if idx < 0:
            return any(pattern in visible for pattern in _SURROUNDING_PATTERNS)

        window = visible[max(0, idx - 120): idx + len(anchor_lower) + 120]
        return any(pattern in window for pattern in _SURROUNDING_PATTERNS)
