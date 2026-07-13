"""PR32 — Homepage Recovery.

Lightweight recovery of real professor homepages when the stored URL no longer
points at the active homepage.

Supported patterns:
  - HTTP redirects (via fetcher final_url)
  - Meta refresh (<meta http-equiv="refresh" ...>)
  - Canonical link (<link rel="canonical" ...>)
  - "Moved" pages (text patterns + destination links)

Public API:
  HomepageRecoveryCandidate – one recovered URL with method and confidence
  HomepageRecoveryResult    – aggregate recovery outcome
  HomepageRecovery            – detect and rank recovery candidates
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

# Recovery method constants
METHOD_HTTP_REDIRECT = "http_redirect"
METHOD_META_REFRESH = "meta_refresh"
METHOD_CANONICAL = "canonical"
METHOD_MOVED_PAGE = "moved_page"

# Confidence scores for each recovery method (high-confidence candidates).
_METHOD_CONFIDENCE: dict[str, float] = {
    METHOD_HTTP_REDIRECT: 0.95,
    METHOD_META_REFRESH: 0.92,
    METHOD_CANONICAL: 0.88,
    METHOD_MOVED_PAGE: 0.85,
}

# Visible-text patterns indicating the page has moved.
_MOVED_TEXT_PATTERNS: tuple[str, ...] = (
    "i moved to",
    "please visit",
    "new homepage",
    "homepage has moved",
    "home page has moved",
    "former homepage",
    "relocated",
    "now at",
    "my new site",
    "my new website",
    "page has moved",
    "site has moved",
    "this page is obsolete",
)

# Anchor text hints on moved pages.
_MOVED_LINK_ANCHORS: tuple[str, ...] = (
    "new homepage",
    "new home page",
    "new website",
    "new site",
    "click here",
    "visit my",
    "my homepage",
    "my website",
    "here",
)

_META_REFRESH_RE = re.compile(
    r'<meta[^>]+http-equiv\s*=\s*["\']?refresh["\']?[^>]*>',
    re.IGNORECASE,
)
_META_CONTENT_URL_RE = re.compile(
    r'content\s*=\s*["\']?\s*\d+\s*;\s*(?:url\s*=\s*)?([^"\'>\s]+)',
    re.IGNORECASE,
)
_CANONICAL_RE = re.compile(
    r'<link[^>]+rel\s*=\s*["\']canonical["\'][^>]*>',
    re.IGNORECASE,
)
_HREF_RE = re.compile(r'href\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)

_IGNORE_HREF_PREFIXES = ("#", "javascript:", "mailto:", "tel:")


@dataclass
class HomepageRecoveryCandidate:
    """A single recovered homepage URL."""

    url: str
    method: str
    confidence: float
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "method": self.method,
            "confidence": round(self.confidence, 3),
            "evidence": list(self.evidence),
        }


@dataclass
class HomepageRecoveryResult:
    """Outcome of homepage recovery for one URL."""

    original_url: str
    recovered_url: str | None = None
    method: str | None = None
    candidates: list[HomepageRecoveryCandidate] = field(default_factory=list)

    @property
    def was_recovered(self) -> bool:
        if not self.recovered_url:
            return False
        return self.recovered_url.rstrip("/") != self.original_url.rstrip("/")

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_url": self.original_url,
            "recovered_url": self.recovered_url,
            "method": self.method,
            "was_recovered": self.was_recovered,
            "candidates": [c.to_dict() for c in self.candidates],
        }


class _LinkExtractor(HTMLParser):
    """Collect anchor hrefs from HTML."""

    def __init__(self, base_url: str) -> None:
        super().__init__()
        self._base_url = base_url
        self._current_href: str | None = None
        self._current_anchor: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            attr_dict = dict(attrs)
            href = attr_dict.get("href") or ""
            if href and not href.startswith(_IGNORE_HREF_PREFIXES):
                self._current_href = href
                self._current_anchor = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._current_href is not None:
            anchor = " ".join(self._current_anchor).strip()
            absolute = urljoin(self._base_url, self._current_href)
            if absolute.startswith(("http://", "https://")):
                self.links.append((anchor, absolute))
            self._current_href = None
            self._current_anchor = []

    def handle_data(self, data: str) -> None:
        if self._current_href is not None:
            self._current_anchor.append(data)


class HomepageRecovery:
    """
    Detect real professor homepages from redirect signals and moved-page content.

    Does not fetch URLs — callers supply HTML and optional final_url from the
    fetcher.  Returns ranked high-confidence candidates; the best candidate
    becomes ``recovered_url`` when it differs from the original.
    """

    def recover(
        self,
        url: str,
        html: str,
        *,
        final_url: str | None = None,
    ) -> HomepageRecoveryResult:
        """
        Analyze *url* / *html* and return recovery candidates.

        Args:
            url:       Original requested URL.
            html:      Fetched HTML body.
            final_url: Post-redirect URL from the fetcher (HTTP redirect recovery).
        """
        result = HomepageRecoveryResult(original_url=url)
        candidates: list[HomepageRecoveryCandidate] = []
        seen: set[str] = set()

        def _add(candidate: HomepageRecoveryCandidate) -> None:
            key = candidate.url.rstrip("/")
            if key in seen:
                return
            seen.add(key)
            candidates.append(candidate)

        # HTTP redirect — fetcher already followed redirects.
        if final_url:
            normalized_final = final_url.rstrip("/")
            normalized_orig = url.rstrip("/")
            if normalized_final and normalized_final != normalized_orig:
                _add(
                    HomepageRecoveryCandidate(
                        url=final_url,
                        method=METHOD_HTTP_REDIRECT,
                        confidence=_METHOD_CONFIDENCE[METHOD_HTTP_REDIRECT],
                        evidence=[f"redirect:{url}→{final_url}"],
                    )
                )

        base = final_url or url

        # Meta refresh
        meta_url = self._extract_meta_refresh(html, base)
        if meta_url:
            _add(
                HomepageRecoveryCandidate(
                    url=meta_url,
                    method=METHOD_META_REFRESH,
                    confidence=_METHOD_CONFIDENCE[METHOD_META_REFRESH],
                    evidence=["meta_refresh"],
                )
            )

        # Canonical link — use when it points to a different host or path.
        canonical_url = self._extract_canonical(html, base)
        if canonical_url and self._is_meaningful_canonical(url, canonical_url):
            _add(
                HomepageRecoveryCandidate(
                    url=canonical_url,
                    method=METHOD_CANONICAL,
                    confidence=_METHOD_CONFIDENCE[METHOD_CANONICAL],
                    evidence=["canonical_link"],
                )
            )

        # Moved-page text patterns + destination links
        if self._has_moved_text(html):
            extractor = _LinkExtractor(base)
            try:
                extractor.feed(html)
            except Exception:
                pass
            for anchor, link_url in extractor.links:
                if not self._is_plausible_homepage_link(link_url, url):
                    continue
                anchor_lower = anchor.lower()
                evidence = ["moved_page_text"]
                if any(hint in anchor_lower for hint in _MOVED_LINK_ANCHORS):
                    evidence.append(f"anchor:{anchor_lower[:40]}")
                _add(
                    HomepageRecoveryCandidate(
                        url=link_url,
                        method=METHOD_MOVED_PAGE,
                        confidence=_METHOD_CONFIDENCE[METHOD_MOVED_PAGE],
                        evidence=evidence,
                    )
                )

        candidates.sort(key=lambda c: c.confidence, reverse=True)
        result.candidates = candidates

        if candidates:
            best = candidates[0]
            result.recovered_url = best.url
            result.method = best.method

        return result

    @staticmethod
    def _extract_meta_refresh(html: str, base_url: str) -> str | None:
        for tag_match in _META_REFRESH_RE.finditer(html):
            tag = tag_match.group(0)
            url_match = _META_CONTENT_URL_RE.search(tag)
            if url_match:
                resolved = urljoin(base_url, url_match.group(1).strip())
                if resolved.startswith(("http://", "https://")):
                    return resolved
        return None

    @staticmethod
    def _extract_canonical(html: str, base_url: str) -> str | None:
        for tag_match in _CANONICAL_RE.finditer(html):
            href_match = _HREF_RE.search(tag_match.group(0))
            if href_match:
                resolved = urljoin(base_url, href_match.group(1).strip())
                if resolved.startswith(("http://", "https://")):
                    return resolved
        return None

    @staticmethod
    def _has_moved_text(html: str) -> bool:
        visible = re.sub(r"<[^>]+>", " ", html).lower()
        visible = re.sub(r"\s+", " ", visible)
        return any(pattern in visible for pattern in _MOVED_TEXT_PATTERNS)

    @staticmethod
    def _is_meaningful_canonical(original: str, canonical: str) -> bool:
        """Canonical is useful when it differs meaningfully from the original."""
        orig_norm = original.rstrip("/").lower()
        canon_norm = canonical.rstrip("/").lower()
        if orig_norm == canon_norm:
            return False

        orig_parsed = urlparse(original)
        canon_parsed = urlparse(canonical)

        # Same host, trivial path difference (index page) — skip
        if (
            orig_parsed.netloc.lower() == canon_parsed.netloc.lower()
            and orig_parsed.path.rstrip("/") in ("", "/")
            and canon_parsed.path.rstrip("/") in ("", "/")
        ):
            return False

        return True

    @staticmethod
    def _is_plausible_homepage_link(link_url: str, original_url: str) -> bool:
        """Filter out social media, PDFs, and same stale URL."""
        if link_url.rstrip("/") == original_url.rstrip("/"):
            return False

        lower = link_url.lower()
        if any(
            host in lower
            for host in (
                "facebook.com",
                "twitter.com",
                "x.com",
                "linkedin.com",
                "instagram.com",
                "youtube.com",
                "scholar.google",
            )
        ):
            return False

        if any(ext in lower for ext in (".pdf", ".doc", ".ppt")):
            return False

        return link_url.startswith(("http://", "https://"))
