"""PR20 — Second-hop people page discovery.

When a first-hop candidate page is successfully fetched but yields zero members
(either because PageClassifier rejected it or extraction found nothing), this
component scans the raw HTML for navigation links pointing to explicit
people/team/member/student sub-pages and returns new CandidatePage objects for
a single additional fetch attempt.

Key design choice
-----------------
``MemberPageParser`` intentionally skips ``<nav>``, ``<header>``, and
``<footer>`` elements to avoid false positives in member extraction.  Those
elements are exactly where people-page navigation links live, so this module
uses its own lightweight ``html.parser`` scan over the *raw HTML* rather than
relying on ``ParsedMemberPage.all_links``.

Design constraints:
  - Follows at most one additional hop (second-hop pages are never inspected
    for further navigation links).
  - Stays within the same host as the originating page.
  - Deduplicates against a caller-supplied set of already-tried URLs.
  - Does not modify parser, validator, or ranking logic.

Public API:
  PeoplePageDiscovery – inspect raw HTML and return CandidatePages
"""

from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from research_group_agent.candidate_page import (
    CandidatePage,
    PAGE_TYPE_ALUMNI,
    PAGE_TYPE_GROUP,
    PAGE_TYPE_LAB,
    PAGE_TYPE_MEMBERS,
    PAGE_TYPE_PEOPLE,
    PAGE_TYPE_STUDENTS,
    PAGE_TYPE_TEAM,
)


# ─────────────────────────────────────────────────────────────────────────────
# Pattern tables  (checked in priority order; first match wins per category)
# ─────────────────────────────────────────────────────────────────────────────

# URL path sub-strings → page_type.
# Matched against the lower-cased URL path component.
_PATH_HINTS: tuple[tuple[str, str], ...] = (
    ("/alumni",             PAGE_TYPE_ALUMNI),
    ("/former-members",     PAGE_TYPE_ALUMNI),
    ("/former_members",     PAGE_TYPE_ALUMNI),
    ("/past-members",       PAGE_TYPE_ALUMNI),
    ("/past_members",       PAGE_TYPE_ALUMNI),
    ("/graduates",          PAGE_TYPE_ALUMNI),
    ("/phd-students",       PAGE_TYPE_STUDENTS),
    ("/phd_students",       PAGE_TYPE_STUDENTS),
    ("/grad-students",      PAGE_TYPE_STUDENTS),
    ("/grad_students",      PAGE_TYPE_STUDENTS),
    ("/graduate-students",  PAGE_TYPE_STUDENTS),
    ("/lab-members",        PAGE_TYPE_MEMBERS),
    ("/lab_members",        PAGE_TYPE_MEMBERS),
    ("/group-members",      PAGE_TYPE_MEMBERS),
    ("/group_members",      PAGE_TYPE_MEMBERS),
    ("/students",           PAGE_TYPE_STUDENTS),
    ("/student",            PAGE_TYPE_STUDENTS),
    ("/postdocs",           PAGE_TYPE_MEMBERS),
    ("/postdoc",            PAGE_TYPE_MEMBERS),
    ("/researchers",        PAGE_TYPE_MEMBERS),
    ("/personnel",          PAGE_TYPE_MEMBERS),
    ("/members",            PAGE_TYPE_MEMBERS),
    ("/people",             PAGE_TYPE_PEOPLE),
    ("/team",               PAGE_TYPE_TEAM),
    ("/group",              PAGE_TYPE_GROUP),
    ("/lab",                PAGE_TYPE_LAB),
)

# Anchor text sub-strings → page_type.
# Matched against the lower-cased, stripped anchor text.
_ANCHOR_HINTS: tuple[tuple[str, str], ...] = (
    ("alumni",              PAGE_TYPE_ALUMNI),
    ("former student",      PAGE_TYPE_ALUMNI),
    ("former member",       PAGE_TYPE_ALUMNI),
    ("past student",        PAGE_TYPE_ALUMNI),
    ("past member",         PAGE_TYPE_ALUMNI),
    ("graduated",           PAGE_TYPE_ALUMNI),
    ("current student",     PAGE_TYPE_STUDENTS),
    ("phd student",         PAGE_TYPE_STUDENTS),
    ("ph.d. student",       PAGE_TYPE_STUDENTS),
    ("graduate student",    PAGE_TYPE_STUDENTS),
    ("grad student",        PAGE_TYPE_STUDENTS),
    ("students",            PAGE_TYPE_STUDENTS),
    ("postdoc",             PAGE_TYPE_MEMBERS),
    ("lab members",         PAGE_TYPE_MEMBERS),
    ("group members",       PAGE_TYPE_MEMBERS),
    ("current member",      PAGE_TYPE_MEMBERS),
    ("members",             PAGE_TYPE_MEMBERS),
    ("researchers",         PAGE_TYPE_MEMBERS),
    ("personnel",           PAGE_TYPE_MEMBERS),
    ("people",              PAGE_TYPE_PEOPLE),
    ("our team",            PAGE_TYPE_TEAM),
    ("our group",           PAGE_TYPE_GROUP),
    ("our lab",             PAGE_TYPE_LAB),
    ("lab member",          PAGE_TYPE_LAB),
    ("team",                PAGE_TYPE_TEAM),
)

# Maximum second-hop candidates generated per first-hop page.
_MAX_SECOND_HOP_PER_PAGE = 5


# ─────────────────────────────────────────────────────────────────────────────
# Lightweight all-links extractor
# ─────────────────────────────────────────────────────────────────────────────

class _AllLinksExtractor(HTMLParser):
    """
    Collect every ``<a href="…">`` from an HTML string, including links inside
    ``<nav>``, ``<header>``, and ``<footer>`` elements that MemberPageParser
    intentionally skips.
    """

    def __init__(self, base_url: str) -> None:
        super().__init__()
        self._base_url = base_url
        self._current_href: str | None = None
        self._current_anchor: list[str] = []
        self.links: list[tuple[str, str]] = []  # (anchor_text, absolute_url)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            attr_dict = dict(attrs)
            href = attr_dict.get("href") or ""
            if href and not href.startswith(("#", "javascript:", "mailto:")):
                self._current_href = href
                self._current_anchor = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._current_href is not None:
            anchor = " ".join(self._current_anchor).strip()
            try:
                absolute = urljoin(self._base_url, self._current_href)
            except Exception:
                absolute = ""
            if absolute.startswith(("http://", "https://")):
                self.links.append((anchor, absolute))
            self._current_href = None
            self._current_anchor = []

    def handle_data(self, data: str) -> None:
        if self._current_href is not None:
            self._current_anchor.append(data)

    @classmethod
    def extract(cls, html: str, base_url: str) -> list[tuple[str, str]]:
        """Return a list of (anchor_text, absolute_url) pairs from the HTML."""
        extractor = cls(base_url)
        try:
            extractor.feed(html)
        except Exception:
            pass
        return extractor.links


# ─────────────────────────────────────────────────────────────────────────────
# PeoplePageDiscovery
# ─────────────────────────────────────────────────────────────────────────────

class PeoplePageDiscovery:
    """
    Discover people/team/member sub-pages from raw fetched HTML.

    Scans ALL anchor tags in the HTML (including those inside ``<nav>``,
    ``<header>``, and ``<footer>`` which ``MemberPageParser`` skips) for links
    that match common people/team/member/student URL path patterns or anchor
    text patterns.

    Responsibilities:
      - Inspect every hyperlink in the raw HTML
      - Match against people-page URL path patterns and anchor text patterns
      - Restrict to the same host as the originating page
      - Normalize URLs and remove duplicates (against caller's already_seen set)
      - Return new CandidatePage objects with source_node_type="second_hop"

    Caller is responsible for:
      - Only invoking this when member count == 0
      - Not invoking this recursively on second-hop results
    """

    def discover(
        self,
        html: str,
        base_url: str,
        already_seen: set[str],
    ) -> list[CandidatePage]:
        """
        Return CandidatePage objects for people-page navigation links not yet tried.

        Args:
            html:         Raw HTML string of the first-hop page.
            base_url:     Absolute URL of the first-hop page; used for URL
                          resolution and host filtering.
            already_seen: Set of already-tried normalized URLs (url.rstrip("/")).
                          Updated in-place as candidates are accepted.

        Returns:
            Deduplicated list of CandidatePage objects ordered by discovery.
            At most _MAX_SECOND_HOP_PER_PAGE entries.
        """
        try:
            base_host = urlparse(base_url).netloc.lower()
        except Exception:
            return []

        all_links = _AllLinksExtractor.extract(html, base_url)
        candidates: list[CandidatePage] = []

        for anchor_text, url in all_links:
            if len(candidates) >= _MAX_SECOND_HOP_PER_PAGE:
                break

            try:
                parsed_url = urlparse(url)
            except Exception:
                continue

            # Restrict to same host as the originating page
            if parsed_url.netloc.lower() != base_host:
                continue

            path = parsed_url.path.lower()
            anchor = anchor_text.lower().strip()

            path_type = _match_path(path)
            anchor_type = _match_anchor(anchor) if not path_type else None
            page_type = path_type or anchor_type

            if page_type is None:
                continue

            key = url.rstrip("/")
            if key in already_seen:
                continue
            already_seen.add(key)

            evidence: list[str] = []
            if path_type:
                evidence.append(f"path_match:{path_type}")
            if anchor_type:
                evidence.append(f"anchor_match:{anchor_type}")

            candidates.append(
                CandidatePage(
                    url=url,
                    page_type=page_type,
                    anchor_text=anchor,
                    score=0.0,
                    evidence=evidence,
                    source_node_type="second_hop",
                    graph_confidence=0.0,
                )
            )

        return candidates


# ─────────────────────────────────────────────────────────────────────────────
# Pattern matching helpers
# ─────────────────────────────────────────────────────────────────────────────

def _match_path(path: str) -> str | None:
    """Return the page_type for the first matching path pattern, or None."""
    for pattern, page_type in _PATH_HINTS:
        if pattern in path:
            return page_type
    return None


def _match_anchor(anchor: str) -> str | None:
    """Return the page_type for the first matching anchor pattern, or None."""
    for pattern, page_type in _ANCHOR_HINTS:
        if pattern in anchor:
            return page_type
    return None
