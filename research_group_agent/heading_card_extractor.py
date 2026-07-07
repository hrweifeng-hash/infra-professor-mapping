"""Heading-card member extraction for modern lab pages — PR21.

Detects the pattern where each lab member is represented as an individual
H3/H4 heading (with an optional profile link) followed by short role text.
This layout is common on Bootstrap / React card-based lab pages such as
RISE Lab, Sky Computing, CSL Illinois, and Vijay Chidambaram's group page.

Activation conditions (prevents false positives on documentation pages):

  In-section mode (parent member section detected):
    Any name-like H3/H4 heading found after a heading such as "Current Members"
    or "PhD Students" is emitted immediately — the section heading provides
    sufficient context.

  Standalone mode (no parent member section):
    Only activated when ≥ _MIN_HEADING_CARDS consecutive H3/H4 headings look
    like person names AND ≥ _MIN_NAME_RATIO fraction have either a profile link
    or a role-keyword in the immediately following block.
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

# Minimum consecutive name-like H3/H4 headings required to activate standalone mode.
_MIN_HEADING_CARDS = 3

# Fraction of standalone cards that must have a profile URL or role hint.
_MIN_NAME_RATIO = 0.60


# ── Pattern helpers ───────────────────────────────────────────────────────────

_WHITESPACE = re.compile(r"\s+")

_NAME_PATTERN = re.compile(
    r"^[A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z]+)+$"
)

# Role keywords for detecting role text in blocks that follow a heading card.
_ROLE_KEYWORDS: tuple[str, ...] = (
    "professor",
    "postdoc",
    "post-doc",
    "phd",
    "ph.d",
    "doctoral",
    "master",
    "m.s.",
    "research scientist",
    "research staff",
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

# Words that mark a heading as a *section title* rather than a person name.
# When a heading word appears in this set (without a hyperlink), the heading
# is treated as a documentation/navigation section — not a member card.
_SECTION_INDICATOR_WORDS: frozenset[str] = frozenset({
    "research",
    "system", "systems",
    "network", "networks",
    "distributed",
    "machine", "learning",
    "computing", "cloud",
    "security",
    "area", "areas",
    "topic", "topics",
    "project", "projects",
    "output", "overview",
    "approach", "approaches",
    "related", "recent",
    "work", "works",
    "current", "former",
    "past", "previous",
    "affiliated",
    "open", "source",
    "data", "neural",
    "vision", "software",
    "hardware", "language",
    "natural", "processing",
    "architecture",
    "embedded", "wireless",
    "mobile", "parallel",
    "quantum",
    "theory", "algorithms",
    "design", "analysis",
    "optimization",
    "infrastructure", "platform",
    "service", "services",
    "application", "applications",
    "introduction", "abstract",
    "motivation", "background",
    "conclusion", "summary",
    "future", "acknowledgments",
    "seminar", "workshop",
    "publication", "publications",
    "paper", "papers",
})


# ── Internal dataclass ────────────────────────────────────────────────────────


@dataclass
class _HeadingCard:
    """Intermediate representation of a single heading-card candidate."""

    name: str
    profile_url: str | None
    section_role: MemberRole
    member_status: MemberStatus
    in_member_section: bool
    role_hint: str | None = None


# ── Private helpers ───────────────────────────────────────────────────────────


def _looks_like_name(text: str) -> bool:
    """Return True if text looks like a person name."""
    text = text.strip()
    if len(text) < 4 or len(text) > 50:
        return False
    if any(char.isdigit() for char in text):
        return False
    if _NAME_PATTERN.match(text):
        return True
    parts = text.split()
    return len(parts) >= 2 and all(part[0].isupper() for part in parts if part)


def _heading_looks_like_name(text: str, links: list[Hyperlink]) -> bool:
    """Return True when an H3/H4 heading should be treated as a person name card.

    Decision logic:
      1. Text must pass ``_looks_like_name()``.
      2. Text must not contain a known ``SKIP_SECTION_KEYWORDS`` phrase.
      3. If the heading contains a hyperlink → True (strong signal; section
         headings almost never carry a navigational link inside them).
      4. Without a link → apply the ``_SECTION_INDICATOR_WORDS`` filter and
         require ≤ 4 words.
    """
    if not _looks_like_name(text):
        return False

    normalized = _WHITESPACE.sub(" ", text).strip().lower()

    # Reject known skip sections (e.g. "Research Areas", "Publications")
    for kw in SKIP_SECTION_KEYWORDS:
        if kw in normalized:
            return False

    # Heading contains a link → almost certainly a profile card
    if links:
        return True

    # No link: apply strict word-based filter
    words = normalized.split()
    if any(w in _SECTION_INDICATOR_WORDS for w in words):
        return False
    if len(words) > 4:
        return False

    return True


def _extract_role_hint(text: str) -> str | None:
    """Return the first matching role keyword found in text, or None."""
    lower = text.lower()
    for kw in _ROLE_KEYWORDS:
        if kw in lower:
            return kw
    return None


def _best_profile_url(name: str, links: list[Hyperlink]) -> str | None:
    """Select the most likely profile URL from a heading's link list."""
    for link in links:
        if _looks_like_name(link.anchor_text.strip()):
            return link.absolute_url
    if links:
        return links[0].absolute_url
    return None


# ── HTML parser ───────────────────────────────────────────────────────────────


class _HeadingCardParser(HTMLParser):
    """
    Dedicated second-pass HTML parser for heading-card extraction.

    Unlike ``_SectionAwareParser``, which resets section context whenever a
    non-matching heading is encountered, this parser:

      • Buffers name-like H3/H4 headings as candidate ``_HeadingCard`` items.
      • Preserves the current member-section context across name headings.
      • Attaches role hints from the block element immediately following each
        heading card (typically a ``<p>`` or ``<div>`` with "PhD Student" etc.).
      • Resets section context only on H1/H2 headings that do not match member
        keywords — H3/H4 headings that fail the name check reset nothing while
        still inside a member section.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._detector = SectionDetector()
        self._base_url = ""

        # Skip / container state
        self._skip_depth = 0
        self._container_skip_depth = 0

        # Section context
        self._section_is_member = False
        self._section_role = MemberRole.UNKNOWN
        self._member_status = MemberStatus.UNKNOWN

        # Heading accumulation
        self._pending_h_tag: str | None = None
        self._pending_h_parts: list[str] = []
        self._pending_h_links: list[Hyperlink] = []

        # Block accumulation (for role text)
        self._block_tag: str | None = None
        self._block_text: list[str] = []
        # True when the immediately preceding heading was a card candidate
        self._last_was_card = False

        # Anchor accumulation
        self._current_href: str | None = None
        self._current_anchor: list[str] = []

        # Output
        self.cards: list[_HeadingCard] = []

    def set_base_url(self, url: str) -> None:
        self._base_url = url

    # ── HTMLParser callbacks ─────────────────────────────────────────────────

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
            self._flush_block()
            self._pending_h_tag = tag
            self._pending_h_parts = []
            self._pending_h_links = []
            return

        if tag in {"p", "div", "li", "span"}:
            self._flush_block()
            self._block_tag = tag
            self._block_text = []

        href = attr_map.get("href", "")
        if tag == "a" and href:
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
            self._process_heading(tag, text)
            self._pending_h_tag = None
            self._pending_h_parts = []
            return

        if tag == "a" and self._current_href:
            anchor = _WHITESPACE.sub(" ", "".join(self._current_anchor)).strip()
            absolute = self._resolve_href(self._current_href)
            if absolute:
                link = Hyperlink(
                    anchor_text=anchor,
                    href=self._current_href,
                    absolute_url=absolute,
                )
                if self._pending_h_tag is not None:
                    self._pending_h_links.append(link)
            self._current_href = None
            self._current_anchor = []

        if tag in {"p", "div", "li", "span"} and self._block_tag == tag:
            self._flush_block()
            self._block_tag = None

    def handle_data(self, data: str) -> None:
        if self._skip_depth or self._container_skip_depth:
            return
        if not data.strip():
            return

        if self._pending_h_tag is not None:
            self._pending_h_parts.append(data)

        if self._current_href is not None:
            self._current_anchor.append(data)

        # Do NOT add heading text to block text — the outer container block
        # (e.g. <div class="card">) would otherwise absorb the name from the
        # heading and flush it before the actual role <p> is processed, causing
        # _last_was_card to be reset prematurely.
        if self._block_tag and self._pending_h_tag is None:
            self._block_text.append(data)

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _process_heading(self, tag: str, text: str) -> None:
        """Classify a heading element and update parser state."""
        match = self._detector.detect_from_heading(text)

        if match.is_member:
            # Known member section (e.g. "Current Members", "PhD Students")
            self._section_is_member = True
            self._section_role = match.role
            self._member_status = match.member_status
            self._last_was_card = False

        elif tag in {"h3", "h4"} and _heading_looks_like_name(text, self._pending_h_links):
            # Heading looks like a person name → buffer as card candidate.
            # The current member-section context is intentionally preserved.
            profile_url = _best_profile_url(text, self._pending_h_links)
            self.cards.append(
                _HeadingCard(
                    name=text,
                    profile_url=profile_url,
                    section_role=self._section_role,
                    member_status=self._member_status,
                    in_member_section=self._section_is_member,
                )
            )
            self._last_was_card = True

        else:
            # Non-member, non-name heading.
            # H1/H2 always resets section context; H3/H4 only resets when
            # outside a member section (to avoid breaking card runs inside
            # sub-sections like "Faculty" inside "People").
            if tag in {"h1", "h2"}:
                self._section_is_member = False
                self._section_role = MemberRole.UNKNOWN
                self._member_status = MemberStatus.UNKNOWN
            self._last_was_card = False

    def _flush_block(self) -> None:
        """Flush accumulated block text, attaching role hint to the last card."""
        if not self._block_tag or not self._block_text:
            return
        text = _WHITESPACE.sub(" ", " ".join(self._block_text)).strip()
        if text and self._last_was_card and self.cards:
            hint = _extract_role_hint(text)
            if hint and self.cards[-1].role_hint is None:
                self.cards[-1].role_hint = hint
        # Only consume the "last_was_card" flag once — the first block after
        # the heading carries the role text; subsequent blocks are not role text.
        self._last_was_card = False

    def _resolve_href(self, href: str) -> str | None:
        href = href.strip()
        if not href or href.startswith(("#", "mailto:", "javascript:", "tel:")):
            return None
        return urljoin(self._base_url, href)


# ── Public extractor ──────────────────────────────────────────────────────────


class HeadingCardExtractor:
    """
    Extract member entries from pages that use a heading-card member layout.

    Designed as an *additional* extraction strategy: it runs after the main
    ``_SectionAwareParser`` and only emits entries not already captured,
    preventing duplication.

    Usage::

        extractor = HeadingCardExtractor()
        already_seen: set[str] = {e.name.lower() for e in existing_entries}
        new_entries = extractor.extract(html, base_url, already_seen)
    """

    def extract(
        self,
        html: str,
        base_url: str,
        already_seen: set[str],
    ) -> list[MemberPageEntry]:
        """
        Parse *html* for heading-card patterns.

        Parameters
        ----------
        html:
            Raw HTML string of the page.
        base_url:
            Absolute URL of the page (used to resolve relative hrefs).
        already_seen:
            Lowercase name keys already captured by the main parser.
            **Updated in-place** with newly extracted names.

        Returns
        -------
        list[MemberPageEntry]
            New member entries (not in *already_seen*), ready to be merged
            into ``ParsedMemberPage.entries``.
        """
        parser = _HeadingCardParser()
        parser.set_base_url(base_url)
        parser.feed(html)
        parser.close()

        if not parser.cards:
            return []

        return self._build_entries(parser.cards, already_seen)

    # ── Private methods ──────────────────────────────────────────────────────

    def _build_entries(
        self,
        cards: list[_HeadingCard],
        already_seen: set[str],
    ) -> list[MemberPageEntry]:
        """Convert card candidates to ``MemberPageEntry`` items, applying thresholds."""
        in_section = [c for c in cards if c.in_member_section]
        standalone = [c for c in cards if not c.in_member_section]

        entries: list[MemberPageEntry] = []

        # ── In-section cards: section heading provides context; emit directly ──
        for card in in_section:
            key = card.name.lower()
            if key not in already_seen:
                already_seen.add(key)
                entries.append(self._card_to_entry(card))

        # ── Standalone cards: threshold required to avoid false positives ──────
        if len(standalone) >= _MIN_HEADING_CARDS:
            confirmed = [c for c in standalone if c.profile_url or c.role_hint]
            ratio = len(confirmed) / len(standalone)
            if ratio >= _MIN_NAME_RATIO:
                for card in standalone:
                    key = card.name.lower()
                    if key not in already_seen:
                        already_seen.add(key)
                        entries.append(self._card_to_entry(card, default_current=True))

        return entries

    @staticmethod
    def _card_to_entry(
        card: _HeadingCard,
        default_current: bool = False,
    ) -> MemberPageEntry:
        # Lazy import avoids circular dependency with parser.py
        from research_group_agent.parser import MemberPageEntry  # noqa: PLC0415

        status = card.member_status
        if default_current and status == MemberStatus.UNKNOWN:
            status = MemberStatus.CURRENT

        return MemberPageEntry(
            name=card.name,
            raw_text=card.name,
            profile_url=card.profile_url,
            role_hint=card.role_hint,
            section_name="heading_card",
            section_role=card.section_role,
            member_status=status,
            in_member_section=True,
        )
