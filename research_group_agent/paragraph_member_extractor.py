"""Paragraph-based member extraction for legacy academic homepages — PR23.

Detects the pattern where each lab member is listed as a short ``<p>``
element containing a person name and a role keyword, without section
headings, UL/LI lists, tables, or heading cards.  Common on older
professor homepages (e.g. Tianyin Xu, flat paragraph blocks).

Activation conditions (prevents false positives on news/publication pages):

  In-section mode (parent member section detected):
    Any ``<p>`` with both a name-like pattern and a role keyword is emitted
    immediately — the section heading provides sufficient context.

  Standalone mode (no parent member section):
    Only activated when ≥ _MIN_PARAGRAPH_MEMBERS short ``<p>`` elements
    contain both a name-like pattern and a role keyword.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import TYPE_CHECKING
from urllib.parse import urljoin

from homepage_agent.models import Hyperlink
from research_group_agent.models import MemberRole, MemberStatus
from research_group_agent.precision_constants import (
    SKIP_CONTAINER_TAGS,
    SKIP_SECTION_KEYWORDS,
)
from research_group_agent.section_detector import SectionDetector

if TYPE_CHECKING:
    from research_group_agent.parser import MemberPageEntry


# ── Thresholds ────────────────────────────────────────────────────────────────

_MIN_PARAGRAPH_MEMBERS = 3
_MAX_PARAGRAPH_LENGTH = 250


# ── Pattern helpers ───────────────────────────────────────────────────────────

_WHITESPACE = re.compile(r"\s+")

_NAME_PATTERN = re.compile(
    r"^[A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z]+)+$"
)

_ROLE_KEYWORDS: tuple[str, ...] = (
    "phd student",
    "phd candidate",
    "ph.d student",
    "ph.d candidate",
    "ph.d.",
    "graduate student",
    "postdoctoral researcher",
    "postdoc research fellow",
    "postdoctoral fellow",
    "postdoc",
    "post-doc",
    "research scientist",
    "master student",
    "ms student",
    "m.s. student",
    "research assistant",
    "undergraduate student",
    "visiting student",
    "research staff",
    "professor",
    "doctoral",
    "phd",
    "ph.d",
    "master",
    "m.s.",
    "visiting",
    "visitor",
    "alumni",
    "former",
    "undergraduate",
    "student",
    "faculty",
    "staff",
    "associate",
    "fellow",
    "intern",
    "researcher",
)

_SKIP_SECTION_PHRASES: tuple[str, ...] = SKIP_SECTION_KEYWORDS + (
    "blog",
    "blogs",
)

_PUBLICATION_INDICATORS: tuple[str, ...] = (
    "best paper",
    "honorable mention",
    "doi.org",
    "arxiv",
    ".pdf",
    "dissertation",
    "the morning paper",
    "spotlighted by",
    "featured by",
    "presented at",
    "accepted at",
    "published in",
    "journal of",
    "conference on",
    "symposium on",
    "proceedings",
)

_YEAR_PREFIX = re.compile(r"^\d{4}\b")


@dataclass
class _ParagraphCandidate:
    name: str
    profile_url: str | None
    role_hint: str | None
    raw_text: str
    section_role: MemberRole
    member_status: MemberStatus
    in_member_section: bool


def _looks_like_name(text: str) -> bool:
    text = text.strip()
    if len(text) < 4 or len(text) > 50:
        return False
    if any(char.isdigit() for char in text):
        return False
    if _NAME_PATTERN.match(text):
        return True
    parts = text.split()
    return len(parts) >= 2 and all(part[0].isupper() for part in parts if part)


def _extract_role_hint(text: str) -> str | None:
    """Return the longest matching role keyword found in text, or None."""
    lower = text.lower()
    for kw in sorted(_ROLE_KEYWORDS, key=len, reverse=True):
        if kw in lower:
            return kw
    return None


def _name_region_before_role(text: str, role_hint: str) -> str:
    """Return the substring before the first role keyword occurrence."""
    lower = text.lower()
    pos = lower.find(role_hint)
    if pos <= 0:
        return text.strip()
    return text[:pos].strip().rstrip(",–-|(").strip()


def _section_is_skip(text: str) -> bool:
    normalized = _WHITESPACE.sub(" ", text).strip().lower()
    return any(kw in normalized for kw in _SKIP_SECTION_PHRASES)


def _looks_like_publication(text: str) -> bool:
    lower = text.lower()
    if _YEAR_PREFIX.match(text.strip()):
        return True
    if text.count(",") >= 4:
        return True
    return any(ind in lower for ind in _PUBLICATION_INDICATORS)


def _best_profile_url(name: str, links: list[Hyperlink]) -> str | None:
    for link in links:
        if _looks_like_name(link.anchor_text.strip()):
            return link.absolute_url
    if links:
        return links[0].absolute_url
    return None


def _extract_name_role_url(
    text: str,
    links: list[Hyperlink],
) -> tuple[str | None, str | None, str | None]:
    text = _WHITESPACE.sub(" ", text).strip()
    if not text:
        return None, None, None

    role_hint = _extract_role_hint(text)
    if role_hint is None:
        return None, None, None

    for link in links:
        anchor = link.anchor_text.strip()
        if anchor and _looks_like_name(anchor):
            return anchor, role_hint, link.absolute_url

    paren_match = re.match(r"^(.+?)\s*\(([^)]+)\)\s*$", text)
    if paren_match:
        candidate = paren_match.group(1).strip()
        role_in_paren = _extract_role_hint(paren_match.group(2))
        if _looks_like_name(candidate) and role_in_paren:
            url = links[0].absolute_url if links else None
            return candidate, role_in_paren, url

    name_region = _name_region_before_role(text, role_hint)

    lines = [line.strip() for line in re.split(r"[\n\r]+", name_region) if line.strip()]
    if len(lines) >= 2:
        first = lines[0]
        if _looks_like_name(first):
            url = links[0].absolute_url if links else None
            return first, role_hint, url

    if _looks_like_name(name_region):
        url = links[0].absolute_url if links else None
        return name_region, role_hint, url

    for separator in (",", "–", "-", "|"):
        if separator in name_region:
            candidate = name_region.split(separator, 1)[0].strip()
            if _looks_like_name(candidate):
                url = links[0].absolute_url if links else None
                return candidate, role_hint, url

    match = re.match(
        r"^([A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z]+)+)",
        name_region,
    )
    if match and _looks_like_name(match.group(1)):
        url = links[0].absolute_url if links else None
        return match.group(1), role_hint, url

    return None, None, None


class _ParagraphMemberParser(HTMLParser):
    """Collect short ``<p>`` elements with name + role keyword patterns."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._detector = SectionDetector()
        self._base_url = ""

        self._skip_depth = 0
        self._container_skip_depth = 0

        self._section_is_member = False
        self._section_is_skip = False
        self._section_role = MemberRole.UNKNOWN
        self._member_status = MemberStatus.UNKNOWN

        self._pending_h_tag: str | None = None
        self._pending_h_parts: list[str] = []

        self._in_paragraph = False
        self._p_parts: list[str] = []
        self._p_links: list[Hyperlink] = []

        self._current_href: str | None = None
        self._current_anchor: list[str] = []

        self.candidates: list[_ParagraphCandidate] = []

    def set_base_url(self, url: str) -> None:
        self._base_url = url

    def handle_starttag(self, tag: str, attrs: list[tuple]) -> None:
        attr_map = {k: (v or "") for k, v in attrs}

        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        if tag in SKIP_CONTAINER_TAGS:
            self._container_skip_depth += 1
            return
        if self._skip_depth or self._container_skip_depth:
            return

        if tag in {"h1", "h2", "h3", "h4"}:
            self._flush_paragraph()
            self._pending_h_tag = tag
            self._pending_h_parts = []
            return

        if tag == "p":
            self._flush_paragraph()
            self._in_paragraph = True
            self._p_parts = []
            self._p_links = []
            return

        href = attr_map.get("href", "")
        if tag == "a" and href and self._in_paragraph:
            self._current_href = href
            self._current_anchor = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if tag in SKIP_CONTAINER_TAGS and self._container_skip_depth:
            self._container_skip_depth -= 1
            return
        if self._skip_depth or self._container_skip_depth:
            return

        if tag in {"h1", "h2", "h3", "h4"} and self._pending_h_tag == tag:
            text = _WHITESPACE.sub(" ", "".join(self._pending_h_parts)).strip()
            self._process_heading(text)
            self._pending_h_tag = None
            self._pending_h_parts = []
            return

        if tag == "a" and self._current_href:
            anchor = _WHITESPACE.sub(" ", "".join(self._current_anchor)).strip()
            absolute = self._resolve_href(self._current_href)
            if absolute and self._in_paragraph:
                self._p_links.append(
                    Hyperlink(
                        anchor_text=anchor,
                        href=self._current_href,
                        absolute_url=absolute,
                    )
                )
            self._current_href = None
            self._current_anchor = []

        if tag == "p" and self._in_paragraph:
            self._flush_paragraph()
            self._in_paragraph = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth or self._container_skip_depth:
            return
        if not data.strip():
            return

        if self._pending_h_tag is not None:
            self._pending_h_parts.append(data)

        if self._current_href is not None:
            self._current_anchor.append(data)

        if self._in_paragraph:
            self._p_parts.append(data)

    def _process_heading(self, text: str) -> None:
        if _section_is_skip(text):
            self._section_is_skip = True
            self._section_is_member = False
            self._section_role = MemberRole.UNKNOWN
            self._member_status = MemberStatus.UNKNOWN
            return

        match = self._detector.detect_from_heading(text)
        if match.is_member:
            self._section_is_member = True
            self._section_is_skip = False
            self._section_role = match.role
            self._member_status = match.member_status
        else:
            self._section_is_skip = False
            self._section_is_member = False
            self._section_role = MemberRole.UNKNOWN
            self._member_status = MemberStatus.UNKNOWN

    def _flush_paragraph(self) -> None:
        if not self._in_paragraph:
            return

        raw = _WHITESPACE.sub(" ", " ".join(self._p_parts)).strip()
        self._p_parts = []
        links = list(self._p_links)
        self._p_links = []

        if not raw:
            return
        if len(raw) > _MAX_PARAGRAPH_LENGTH:
            return
        if self._section_is_skip:
            return
        if _looks_like_publication(raw):
            return

        name, role_hint, profile_url = _extract_name_role_url(raw, links)
        if not name or not role_hint:
            return

        if profile_url is None:
            profile_url = _best_profile_url(name, links)

        self.candidates.append(
            _ParagraphCandidate(
                name=name,
                profile_url=profile_url,
                role_hint=role_hint,
                raw_text=raw,
                section_role=self._section_role,
                member_status=self._member_status,
                in_member_section=self._section_is_member,
            )
        )

    def _resolve_href(self, href: str) -> str | None:
        href = href.strip()
        if not href or href.startswith(("#", "mailto:", "javascript:", "tel:")):
            return None
        return urljoin(self._base_url, href)


class ParagraphMemberExtractor:
    """
    Extract member entries from pages that list members as short ``<p>`` blocks.

    Designed as an *additional* extraction strategy: it runs after the main
    ``_SectionAwareParser`` and ``HeadingCardExtractor`` and only emits entries
    not already captured, preventing duplication.
    """

    def extract(
        self,
        html: str,
        base_url: str,
        already_seen: set[str],
    ) -> list[MemberPageEntry]:
        parser = _ParagraphMemberParser()
        parser.set_base_url(base_url)
        parser.feed(html)
        parser.close()

        if not parser.candidates:
            return []

        return self._build_entries(parser.candidates, already_seen)

    def _build_entries(
        self,
        candidates: list[_ParagraphCandidate],
        already_seen: set[str],
    ) -> list[MemberPageEntry]:
        in_section = [c for c in candidates if c.in_member_section]
        standalone = [c for c in candidates if not c.in_member_section]

        entries: list[MemberPageEntry] = []

        for candidate in in_section:
            key = candidate.name.lower()
            if key not in already_seen:
                already_seen.add(key)
                entries.append(self._candidate_to_entry(candidate))

        if len(standalone) >= _MIN_PARAGRAPH_MEMBERS:
            for candidate in standalone:
                key = candidate.name.lower()
                if key not in already_seen:
                    already_seen.add(key)
                    entries.append(
                        self._candidate_to_entry(candidate, default_current=True)
                    )

        return entries

    @staticmethod
    def _candidate_to_entry(
        candidate: _ParagraphCandidate,
        default_current: bool = False,
    ) -> MemberPageEntry:
        from research_group_agent.parser import MemberPageEntry  # noqa: PLC0415

        status = candidate.member_status
        if default_current and status == MemberStatus.UNKNOWN:
            status = MemberStatus.CURRENT

        return MemberPageEntry(
            name=candidate.name,
            raw_text=candidate.raw_text,
            profile_url=candidate.profile_url,
            role_hint=candidate.role_hint,
            section_name="paragraph",
            section_role=candidate.section_role,
            member_status=status,
            in_member_section=True,
        )
