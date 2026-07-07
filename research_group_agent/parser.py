"""HTML parser for research group member pages — section-aware extraction.

PR16 improvements over PR15:
  - SectionDetector integration for heading-based and plain-text section inference
  - Plain-text section headers (e.g. "Current Ph.D. Students:") detected
    without requiring h1–h4 tags
  - Repeated profile-card detection: names extracted from <img alt="…"> inside
    <a href="…"> links when a high-confidence repeated pattern is detected
  - Modern HTML support: repeated <article>, <section>, <div class="card"> etc.
  - Lab-name headings no longer trigger false member sections

PR21 addition:
  - HeadingCardExtractor integration: extracts members from pages where each
    member is represented as an H3/H4 heading rather than a list item.
    Common on Bootstrap/React card-based lab pages (RISE Lab, Sky Computing,
    CSL Illinois, Vijay Chidambaram's group, etc.).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin

from homepage_agent.models import Hyperlink

from research_group_agent.models import MemberRole, MemberStatus
from research_group_agent.precision_constants import (
    SKIP_CONTAINER_TAGS,
)
from research_group_agent.section_detector import SectionDetector


_WHITESPACE = re.compile(r"\s+")

_NAME_PATTERN = re.compile(
    r"^[A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z]+)+$"
)

# Minimum number of repeated profile-like structures before treating them as
# a member list (Part 6: Repeated Profile Detection).
_MIN_REPEATED_PROFILES = 4

# CSS class patterns that suggest a person profile card.
_PROFILE_CARD_CLASS_RE = re.compile(
    r'\b(?:person|people|member|team|profile|card|faculty|student|staff|researcher)\b',
    re.IGNORECASE,
)

# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class PageSection:
    name: str
    role: MemberRole
    member_status: MemberStatus
    is_member_section: bool
    entry_count: int = 0
    detection_method: str = "heading"


@dataclass
class MemberPageEntry:
    name: str
    raw_text: str
    profile_url: str | None = None
    role_hint: str | None = None
    section_name: str | None = None
    section_role: MemberRole = MemberRole.UNKNOWN
    member_status: MemberStatus = MemberStatus.CURRENT
    in_member_section: bool = False
    links: list[Hyperlink] = field(default_factory=list)


@dataclass
class ParsedMemberPage:
    page_title: str
    entries: list[MemberPageEntry] = field(default_factory=list)
    all_links: list[Hyperlink] = field(default_factory=list)
    visible_text: str = ""
    sections: list[PageSection] = field(default_factory=list)
    # PR16 additions
    repeated_profiles: list[MemberPageEntry] = field(default_factory=list)
    inferred_section_count: int = 0
    profile_card_count: int = 0
    # PR21 addition
    heading_card_count: int = 0


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────


def _normalize_heading(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip().lower()


# ─────────────────────────────────────────────────────────────────────────────
# Core HTML parser
# ─────────────────────────────────────────────────────────────────────────────


class _SectionAwareParser(HTMLParser):
    """
    Stateful HTML parser that emits member-page entries grouped by section.

    PR16 additions:
      - Uses SectionDetector for heading classification (including lab-name check)
      - Tracks loose text (text between block elements) for plain-text section inference
      - Infers section context from text preceding <ul>/<ol> elements
      - Collects <img alt="Name"> from repeated profile links
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._detector = SectionDetector()

        # Output buffers
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.all_links: list[Hyperlink] = []

        # Parse state
        self._in_title = False
        self._skip_depth = 0
        self._container_skip_depth = 0

        # Section tracking
        self._current_section_name = ""
        self._current_section_role = MemberRole.UNKNOWN
        self._current_section_is_member = False
        self._current_member_status = MemberStatus.UNKNOWN
        self._current_section_method = "heading"
        self._section_counts: dict[str, int] = {}
        self._section_methods: dict[str, str] = {}

        # Block tracking (li / tr / p / div)
        self._block_tag: str | None = None
        self._block_text: list[str] = []
        self._block_links: list[Hyperlink] = []
        # Each block: (tag, text_parts, links, section_name, section_role,
        #              is_member, member_status, detection_method)
        self._blocks: list[tuple] = []

        # Loose text: text nodes OUTSIDE any tracked block element.
        # Used for plain-text section inference when a <ul>/<ol> follows.
        self._loose_text_parts: list[str] = []

        # Anchor tracking
        self._current_anchor: list[str] = []
        self._current_href: str | None = None
        self._base_url = ""

        # Heading accumulation
        self._pending_heading_tag: str | None = None
        self._pending_heading_parts: list[str] = []

        # Profile-card tracking (repeated profiles)
        # Stores (name, url) tuples collected from img[alt] inside profile-like links
        self._profile_card_entries: list[tuple[str, str | None]] = []
        self._in_profile_link = False
        self._profile_link_href: str | None = None
        self._profile_link_img_alt: str | None = None

    def set_base_url(self, base_url: str) -> None:
        self._base_url = base_url

    # ── HTMLParser callbacks ─────────────────────────────────────────────────

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: (value or "") for key, value in attrs}

        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return

        if tag in SKIP_CONTAINER_TAGS:
            self._container_skip_depth += 1
            return

        if self._skip_depth or self._container_skip_depth:
            return

        if tag == "title":
            self._in_title = True
            return

        if tag in {"h1", "h2", "h3", "h4"}:
            self._flush_block()
            self._loose_text_parts = []
            self._pending_heading_tag = tag
            self._pending_heading_parts = []
            return

        # Plain-text section inference: when a list begins, check preceding text
        if tag in {"ul", "ol"}:
            self._try_infer_section_before_list()
            return

        if tag in {"li", "tr", "p", "div"}:
            # Clear loose text when a new structural block starts
            self._loose_text_parts = []
            self._flush_block()
            self._block_tag = tag
            self._block_text = []
            self._block_links = []

        # Anchor / link handling
        href = attr_map.get("href", "")
        if tag == "a" and href:
            self._current_href = href
            self._current_anchor = []
            # Check for profile-card link pattern (href containing fragment like #name)
            if self._is_profile_card_link(href):
                self._in_profile_link = True
                self._profile_link_href = href
                self._profile_link_img_alt = None

        # Profile card: collect img alt text inside profile links
        if tag == "img" and self._in_profile_link:
            alt = attr_map.get("alt", "").strip()
            if alt and _looks_like_name(alt):
                self._profile_link_img_alt = alt

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
            return

        if tag in SKIP_CONTAINER_TAGS and self._container_skip_depth:
            self._container_skip_depth -= 1
            return

        if self._skip_depth or self._container_skip_depth:
            return

        if tag == "title":
            self._in_title = False
            return

        if tag in {"h1", "h2", "h3", "h4"} and self._pending_heading_tag == tag:
            heading_text = _WHITESPACE.sub(" ", "".join(self._pending_heading_parts)).strip()
            match = self._detector.detect_from_heading(heading_text)
            self._current_section_name = match.section_name
            self._current_section_role = match.role
            self._current_section_is_member = match.is_member
            self._current_member_status = match.member_status
            self._current_section_method = match.detection_method
            if match.section_name and match.section_name not in self._section_counts:
                self._section_counts[match.section_name] = 0
                self._section_methods[match.section_name] = match.detection_method
            self._pending_heading_tag = None
            self._pending_heading_parts = []
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
                self.all_links.append(link)
                self._block_links.append(link)

            # Finalize profile-card entry
            if self._in_profile_link and self._profile_link_img_alt:
                url = self._resolve_href(self._profile_link_href or "")
                self._profile_card_entries.append((self._profile_link_img_alt, url))

            self._current_href = None
            self._current_anchor = []
            self._in_profile_link = False
            self._profile_link_href = None
            self._profile_link_img_alt = None

        if tag in {"li", "tr", "p", "div"} and self._block_tag == tag:
            self._flush_block()
            self._block_tag = None

    def handle_data(self, data: str) -> None:
        if self._skip_depth or self._container_skip_depth:
            return

        stripped = data.strip()
        if not stripped:
            return

        if self._in_title:
            self.title_parts.append(data)
            return

        if self._pending_heading_tag is not None:
            self._pending_heading_parts.append(data)

        if self._current_href is not None:
            self._current_anchor.append(data)

        self.text_parts.append(data)

        if self._block_tag:
            self._block_text.append(data)
        else:
            # Text outside a tracked block — accumulate for section inference
            self._loose_text_parts.append(data)

    # ── Section inference helpers ────────────────────────────────────────────

    def _try_infer_section_before_list(self) -> None:
        """
        Called when <ul> or <ol> is encountered.

        Checks:
          1. Current block text (e.g. text inside a <div> or <p> preceding the list)
          2. Loose text nodes (text directly in the parent element, outside blocks)

        If either contains a plain-text section pattern, updates the current
        section context and clears the matched text to avoid treating the header
        as a member entry.
        """
        # Priority 1: check block text (text accumulated inside current div/p)
        if self._block_tag in {"div", "p"} and self._block_text:
            combined_block = _WHITESPACE.sub(" ", " ".join(self._block_text)).strip()
            match = self._detector.detect_from_plain_text(combined_block)
            if match:
                self._apply_inferred_section(match)
                # Clear block text so this header is NOT added as an entry
                self._block_text = []
                self._block_links = []
                return

        # Priority 2: check loose text (text between block elements)
        if self._loose_text_parts:
            combined_loose = _WHITESPACE.sub(" ", " ".join(self._loose_text_parts)).strip()
            match = self._detector.detect_from_plain_text(combined_loose)
            if match:
                self._apply_inferred_section(match)
                self._loose_text_parts = []
                return

    def _apply_inferred_section(self, match) -> None:
        """Apply a plain-text section match as the current section context."""
        self._current_section_name = match.section_name
        self._current_section_role = match.role
        self._current_section_is_member = match.is_member
        self._current_member_status = match.member_status
        self._current_section_method = match.detection_method
        if match.section_name and match.section_name not in self._section_counts:
            self._section_counts[match.section_name] = 0
            self._section_methods[match.section_name] = match.detection_method

    # ── Block helpers ────────────────────────────────────────────────────────

    def _flush_block(self) -> None:
        if not self._block_tag:
            return
        text = _WHITESPACE.sub(" ", " ".join(self._block_text)).strip()
        if text:
            self._blocks.append((
                self._block_tag,
                self._block_text[:],
                self._block_links[:],
                self._current_section_name,
                self._current_section_role,
                self._current_section_is_member,
                self._current_member_status,
                self._current_section_method,
            ))

    def _resolve_href(self, href: str) -> str | None:
        href = href.strip()
        if not href or href.startswith(("#", "mailto:", "javascript:", "tel:")):
            return None
        return urljoin(self._base_url, href)

    @staticmethod
    def _is_profile_card_link(href: str) -> bool:
        """
        Return True if this link looks like a profile-card link.

        Profile card links typically have the form:
          people.html#first-last
          /people#username
          #person-slug
        """
        href = href.strip().lower()
        # Fragment links pointing to people/person anchors
        if "#" in href:
            fragment = href.split("#", 1)[1]
            if fragment and re.match(r'^[a-z][a-z0-9-]+$', fragment):
                return True
        return False

    # ── Finalization ─────────────────────────────────────────────────────────

    def finalize(self) -> ParsedMemberPage:
        self._flush_block()
        title = _WHITESPACE.sub(" ", "".join(self.title_parts)).strip()
        visible = _WHITESPACE.sub(" ", " ".join(self.text_parts)).strip()

        entries: list[MemberPageEntry] = []
        seen: set[str] = set()

        for (
            _tag,
            block_text_parts,
            block_links,
            section_name,
            section_role,
            is_member,
            member_status,
            detection_method,
        ) in self._blocks:
            if not is_member:
                continue

            raw = _WHITESPACE.sub(" ", " ".join(block_text_parts)).strip()
            if not raw or len(raw) < 3:
                continue

            name, profile_url = self._extract_name_and_url(raw, block_links)
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())

            if section_name in self._section_counts:
                self._section_counts[section_name] += 1

            role_hint = self._extract_role_hint(raw)
            entries.append(
                MemberPageEntry(
                    name=name,
                    raw_text=raw,
                    profile_url=profile_url,
                    role_hint=role_hint,
                    section_name=section_name or None,
                    section_role=section_role,
                    member_status=member_status,
                    in_member_section=True,
                    links=list(block_links),
                )
            )

        # Build sections list
        sections: list[PageSection] = []
        for name, count in self._section_counts.items():
            match = self._detector.detect_from_heading(name)
            method = self._section_methods.get(name, "heading")
            sections.append(
                PageSection(
                    name=name,
                    role=match.role,
                    member_status=match.member_status,
                    is_member_section=match.is_member,
                    entry_count=count,
                    detection_method=method,
                )
            )

        # Repeated profile detection: collect unique names from profile-card links
        repeated_profiles = self._build_repeated_profiles(seen)
        inferred_count = sum(
            1 for s in sections if s.detection_method == "plain_text"
        )

        return ParsedMemberPage(
            page_title=title,
            entries=entries,
            all_links=self.all_links,
            visible_text=visible,
            sections=sections,
            repeated_profiles=repeated_profiles,
            inferred_section_count=inferred_count,
            profile_card_count=len(self._profile_card_entries),
        )

    def _build_repeated_profiles(
        self,
        already_seen: set[str],
    ) -> list[MemberPageEntry]:
        """
        Build MemberPageEntry items from repeated profile-card img[alt] data.

        Only triggers when >= _MIN_REPEATED_PROFILES unique names were collected,
        suggesting the page uses a repeated card layout for its people section.
        """
        if len(self._profile_card_entries) < _MIN_REPEATED_PROFILES:
            return []

        seen_names: dict[str, str | None] = {}
        for name, url in self._profile_card_entries:
            key = name.lower()
            if key not in seen_names:
                seen_names[key] = url

        # Only emit profiles not already captured by section-based extraction
        profiles: list[MemberPageEntry] = []
        for name, url in seen_names.items():
            display_name = name.title()
            if display_name.lower() not in already_seen:
                profiles.append(
                    MemberPageEntry(
                        name=display_name,
                        raw_text=display_name,
                        profile_url=url,
                        section_name="profile_card",
                        section_role=MemberRole.UNKNOWN,
                        member_status=MemberStatus.CURRENT,
                        in_member_section=True,
                    )
                )

        return profiles

    @staticmethod
    def _extract_name_and_url(
        raw: str,
        links: list[Hyperlink],
    ) -> tuple[str | None, str | None]:
        # Prefer link anchor text that looks like a name
        for link in links:
            anchor = link.anchor_text.strip()
            if anchor and _looks_like_name(anchor):
                return anchor, link.absolute_url

        # Try splitting on common separators
        for separator in ("–", "-", "|", ","):
            if separator in raw:
                candidate = raw.split(separator, 1)[0].strip()
                if _looks_like_name(candidate):
                    url = links[0].absolute_url if links else None
                    return candidate, url

        # Try a leading name pattern
        match = re.match(r"^([A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z]+)+)", raw)
        if match and _looks_like_name(match.group(1)):
            url = links[0].absolute_url if links else None
            return match.group(1), url

        return None, None

    @staticmethod
    def _extract_role_hint(raw: str) -> str | None:
        lower = raw.lower()
        role_keywords = (
            "professor",
            "postdoc",
            "post-doc",
            "phd",
            "ph.d",
            "doctoral",
            "master",
            "m.s.",
            "research staff",
            "research scientist",
            "visitor",
            "alumni",
            "former",
            "undergraduate",
            "student",
        )
        for keyword in role_keywords:
            if keyword in lower:
                return keyword
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Public helpers
# ─────────────────────────────────────────────────────────────────────────────


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


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────


class MemberPageParser:
    """Convert research group page HTML into section-aware member entries."""

    def parse(self, html: str, base_url: str) -> ParsedMemberPage:
        parser = _SectionAwareParser()
        parser.set_base_url(base_url)
        parser.feed(html)
        parser.close()
        result = parser.finalize()

        # PR21: heading-card extraction for modern card-based layouts.
        # Runs as a second pass on the same HTML so the existing parser is
        # completely unchanged.  Only entries not already captured are added.
        from research_group_agent.heading_card_extractor import HeadingCardExtractor  # noqa: PLC0415
        already_seen: set[str] = {e.name.lower() for e in result.entries}
        already_seen.update(e.name.lower() for e in result.repeated_profiles)
        heading_entries = HeadingCardExtractor().extract(html, base_url, already_seen)
        if heading_entries:
            result.entries.extend(heading_entries)
            result.heading_card_count = len(heading_entries)

        return result
