"""Heuristic navigator provider — no external API calls."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from homepage_agent.models import (
    ConfidenceScore,
    HomepageDocument,
    Hyperlink,
    NavigationDecision,
    NodeCategory,
)
from homepage_agent.providers.base import NavigatorProvider

# (category, keyword patterns for anchor text, keyword patterns for URL path)
_CATEGORY_RULES: list[tuple[NodeCategory, tuple[str, ...], tuple[str, ...]]] = [
    (
        NodeCategory.PEOPLE_PAGE,
        ("people", "members", "team", "students", "group members", "personnel"),
        ("people", "members", "team", "students", "personnel"),
    ),
    (
        NodeCategory.LAB_PAGE,
        ("lab", "our lab", "research lab"),
        ("lab", "research-lab"),
    ),
    (
        NodeCategory.RESEARCH_GROUP_PAGE,
        ("research group", "group", "research team"),
        ("group", "research-group", "research_team"),
    ),
    (
        NodeCategory.PROJECTS_PAGE,
        ("projects", "research projects", "project"),
        ("projects", "project"),
    ),
    (
        NodeCategory.PUBLICATIONS_PAGE,
        ("publications", "papers", "bibtex", "bibliography", "pubs"),
        ("publications", "papers", "pubs", "bib"),
    ),
    (
        NodeCategory.SOFTWARE_PAGE,
        ("software", "code", "github", "open source", "tools"),
        ("software", "code", "github", "tools"),
    ),
    (
        NodeCategory.TEACHING_PAGE,
        ("teaching", "courses", "classes", "course"),
        ("teaching", "courses", "classes"),
    ),
    (
        NodeCategory.NEWS_PAGE,
        ("news", "blog", "announcements", "updates"),
        ("news", "blog", "announcements"),
    ),
    (
        NodeCategory.CONTACT_PAGE,
        ("contact", "about", "about me", "reach"),
        ("contact", "about"),
    ),
]

_IGNORE_PATTERNS = (
    "twitter",
    "linkedin",
    "facebook",
    "instagram",
    "youtube",
    "scholar.google",
    "dblp",
    "orcid",
    "arxiv",
    "doi.org",
    ".pdf",
    "mailto:",
)


class StubNavigatorProvider(NavigatorProvider):
    """
    Heuristic link classifier using anchor text and URL path scoring.

    Serves as the default provider until an LLM backend is configured.
    """

    MIN_CONFIDENCE = 0.35

    @property
    def provider_name(self) -> str:
        return "heuristic"

    def classify_links(
        self,
        prompt: str,
        document: HomepageDocument,
        links: list[Hyperlink],
    ) -> list[NavigationDecision]:
        del prompt, document  # reserved for future LLM providers

        best_by_category: dict[NodeCategory, NavigationDecision] = {}

        for link in links:
            if self._should_ignore(link):
                continue

            for category, anchor_patterns, path_patterns in _CATEGORY_RULES:
                keyword_score, structure_score = self._score_link(
                    link,
                    anchor_patterns,
                    path_patterns,
                )
                confidence = ConfidenceScore.from_stub(keyword_score, structure_score)
                if confidence.final_score < self.MIN_CONFIDENCE:
                    continue

                reason = self._build_reason(
                    link,
                    anchor_patterns,
                    path_patterns,
                    keyword_score,
                    structure_score,
                )
                decision = NavigationDecision(
                    candidate_url=link.absolute_url,
                    candidate_type=category,
                    confidence=confidence,
                    reason=reason,
                    anchor_text=link.anchor_text or None,
                )

                current = best_by_category.get(category)
                if current is None or decision.final_confidence > current.final_confidence:
                    best_by_category[category] = decision

        return list(best_by_category.values())

    def _should_ignore(self, link: Hyperlink) -> bool:
        haystack = f"{link.absolute_url} {link.anchor_text}".lower()
        return any(pattern in haystack for pattern in _IGNORE_PATTERNS)

    def _score_link(
        self,
        link: Hyperlink,
        anchor_patterns: tuple[str, ...],
        path_patterns: tuple[str, ...],
    ) -> tuple[float, float]:
        anchor = (link.anchor_text or "").lower()
        path = urlparse(link.absolute_url).path.lower()

        keyword_score = max(
            (self._pattern_strength(anchor, pattern) for pattern in anchor_patterns),
            default=0.0,
        )
        structure_score = max(
            (self._pattern_strength(path, pattern) for pattern in path_patterns),
            default=0.0,
        )

        if keyword_score == 0.0 and structure_score == 0.0:
            return 0.0, 0.0

        if anchor == path.strip("/").split("/")[-1]:
            keyword_score = min(1.0, keyword_score + 0.05)

        return keyword_score, structure_score

    @staticmethod
    def _pattern_strength(text: str, pattern: str) -> float:
        pattern = pattern.lower()
        if not pattern or not text:
            return 0.0

        if pattern in text:
            if text.strip() == pattern:
                return 1.0
            if re.search(rf"\b{re.escape(pattern)}\b", text):
                return 0.9
            return 0.75

        return 0.0

    @staticmethod
    def _build_reason(
        link: Hyperlink,
        anchor_patterns: tuple[str, ...],
        path_patterns: tuple[str, ...],
        keyword_score: float,
        structure_score: float,
    ) -> str:
        anchor = (link.anchor_text or "").lower()
        path = urlparse(link.absolute_url).path.lower()

        matched_anchor = next(
            (pattern for pattern in anchor_patterns if pattern in anchor),
            None,
        )
        matched_path = next(
            (pattern for pattern in path_patterns if pattern in path),
            None,
        )

        parts = []
        if matched_anchor:
            parts.append(f"anchor matched '{matched_anchor}'")
        if matched_path:
            parts.append(f"path matched '{matched_path}'")
        parts.append(f"keyword={keyword_score:.2f}")
        parts.append(f"structure={structure_score:.2f}")
        return "; ".join(parts)
