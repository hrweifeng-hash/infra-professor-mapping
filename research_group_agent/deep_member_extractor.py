"""Deep member page extraction for multi-hop navigation targets — M5-PR2.

Extracts members from deep laboratory pages discovered by M5-PR1 navigation
where prior passes (section lists, heading cards, paragraphs) miss content.

Supported layouts:
  - Definition lists (dl/dt/dd)
  - Bootstrap cards, grid layouts, media objects, profile tiles
  - Accordion / tab panels inside member sections
  - Table-based member directories
  - Repeated profile-card grids (img alt + profile links)
  - Member blocks without explicit section headings (standalone threshold)

Public API:
  DeepMemberExtractor – fourth-pass member extraction
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import TYPE_CHECKING
from urllib.parse import urljoin

from homepage_agent.models import Hyperlink
from research_group_agent.models import MemberRole, MemberStatus
from research_group_agent.precision_constants import SKIP_CONTAINER_TAGS
from research_group_agent.section_detector import SectionDetector

if TYPE_CHECKING:
    from research_group_agent.parser import MemberPageEntry

_WHITESPACE = re.compile(r"\s+")
_NAME_PATTERN = re.compile(
    r"^[A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z]+)+$"
)

_MIN_DEEP_BLOCKS = 3
_MIN_PROFILE_CARDS = 3

_ROLE_KEYWORDS: tuple[str, ...] = (
    "professor",
    "postdoc",
    "post-doc",
    "postdoctoral",
    "phd",
    "ph.d",
    "doctoral",
    "graduate student",
    "master",
    "m.s.",
    "research staff",
    "research scientist",
    "researcher",
    "visiting",
    "visitor",
    "alumni",
    "former",
    "undergraduate",
    "student",
    "staff",
    "fellow",
    "intern",
    "affiliated",
)

_ADVISOR_RE = re.compile(
    r"\b(?:advisor|adviser|supervisor|mentor)\s*[:\-]\s*([A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z]+)+)",
    re.IGNORECASE,
)

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

_SKIP_CLASS_ID_RE = re.compile(
    r"\b(?:sidebar|widget|footer|breadcrumb|pagination|menu|navbar|nav\-|social|share|sponsor|banner)\b",
    re.IGNORECASE,
)

_MEMBER_CONTAINER_CLASS_RE = re.compile(
    r"\b(?:card|person|people|member|profile|tile|media|panel|accordion|tab\-pane|grid|row|col|student|researcher|postdoc|team)\b",
    re.IGNORECASE,
)


@dataclass
class _DeepBlock:
    name: str
    raw_text: str
    profile_url: str | None = None
    role_hint: str | None = None
    advisor_hint: str | None = None
    email: str | None = None
    github_url: str | None = None
    section_name: str = "deep_member"
    section_role: MemberRole = MemberRole.UNKNOWN
    member_status: MemberStatus = MemberStatus.CURRENT
    in_member_section: bool = False
    links: list[Hyperlink] = field(default_factory=list)


def _looks_like_name(text: str) -> bool:
    text = text.strip()
    if len(text) < 4 or len(text) > 50:
        return False
    if any(char.isdigit() for char in text):
        return False
    if _NAME_PATTERN.match(text):
        return True
    parts = text.split()
    return len(parts) >= 2 and all(part and part[0].isupper() for part in parts)


def _extract_role_hint(text: str) -> str | None:
    lower = text.lower()
    for keyword in _ROLE_KEYWORDS:
        if keyword in lower:
            return keyword
    return None


def _extract_advisor_hint(text: str) -> str | None:
    match = _ADVISOR_RE.search(text)
    return match.group(1).strip() if match else None


def _extract_email(text: str) -> str | None:
    match = _EMAIL_RE.search(text)
    return match.group(0) if match else None


def _extract_github_url(links: list[Hyperlink]) -> str | None:
    for link in links:
        if "github.com" in (link.absolute_url or "").lower():
            return link.absolute_url
    return None


def _best_profile_url(name: str, links: list[Hyperlink]) -> str | None:
    for link in links:
        anchor = link.anchor_text.strip()
        if anchor and _looks_like_name(anchor):
            return link.absolute_url
    for link in links:
        url = (link.absolute_url or "").lower()
        if any(host in url for host in ("github.com", ".edu", "~")):
            return link.absolute_url
    return links[0].absolute_url if links else None


def _extract_name_and_url(raw: str, links: list[Hyperlink]) -> tuple[str | None, str | None]:
    for link in links:
        anchor = link.anchor_text.strip()
        if anchor and _looks_like_name(anchor):
            return anchor, link.absolute_url

    for separator in ("–", "-", "|", ","):
        if separator in raw:
            candidate = raw.split(separator, 1)[0].strip()
            if _looks_like_name(candidate):
                return candidate, _best_profile_url(candidate, links)

    match = re.match(r"^([A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z]+)+)", raw)
    if match and _looks_like_name(match.group(1)):
        return match.group(1), _best_profile_url(match.group(1), links)

    return None, None


class _DeepMemberParser(HTMLParser):
    """Collect member blocks from deep page layouts."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._detector = SectionDetector()
        self._base_url = ""
        self._skip_depth = 0
        self._container_skip_depth = 0
        self._ignore_depth = 0

        self._section_name = ""
        self._section_role = MemberRole.UNKNOWN
        self._member_status = MemberStatus.CURRENT
        self._section_is_member = False

        self._current_href: str | None = None
        self._current_anchor: list[str] = []
        self._pending_heading_tag: str | None = None
        self._pending_heading_parts: list[str] = []

        self._block_tag: str | None = None
        self._block_text: list[str] = []
        self._block_links: list[Hyperlink] = []
        self._block_class_id = ""
        self._blocks: list[tuple[str, list[str], list[Hyperlink], str, bool]] = []

        self._in_dt = False
        self._dt_text: list[str] = []
        self._dt_links: list[Hyperlink] = []
        self._dd_text: list[str] = []
        self._dd_links: list[Hyperlink] = []
        self._in_dd = False

        self._table_cells: list[str] = []
        self._table_links: list[Hyperlink] = []
        self._in_tr = False
        self._in_td = False

        self._profile_cards: list[tuple[str, str | None]] = []
        self._in_profile_link = False
        self._profile_href: str | None = None
        self._profile_img_alt: str | None = None

    def set_base_url(self, url: str) -> None:
        self._base_url = url

    def _should_ignore_attrs(self, attrs: list[tuple[str, str | None]]) -> bool:
        attr_map = {key: (value or "") for key, value in attrs}
        haystack = f"{attr_map.get('class', '')} {attr_map.get('id', '')}".lower()
        return bool(_SKIP_CLASS_ID_RE.search(haystack))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: (value or "") for key, value in attrs}
        class_id = f"{attr_map.get('class', '')} {attr_map.get('id', '')}"

        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return

        if tag in SKIP_CONTAINER_TAGS:
            self._container_skip_depth += 1
            return

        if self._should_ignore_attrs(attrs):
            self._ignore_depth += 1
            return

        if self._skip_depth or self._container_skip_depth or self._ignore_depth:
            return

        if tag in {"h1", "h2", "h3", "h4"}:
            self._flush_block()
            self._pending_heading_tag = tag
            self._pending_heading_parts = []
            return

        if tag == "dt":
            self._in_dt = True
            self._dt_text = []
            self._dt_links = []
            return

        if tag == "dd":
            self._flush_dt()
            self._in_dd = True
            self._dd_text = []
            self._dd_links = []
            return

        if tag == "tr":
            self._in_tr = True
            self._table_cells = []
            self._table_links = []
            return

        if tag == "td" and self._in_tr:
            self._in_td = True
            return

        if tag in {"div", "article", "section", "li", "p"}:
            self._flush_block()
            self._block_tag = tag
            self._block_text = []
            self._block_links = []
            self._block_class_id = class_id

        href = attr_map.get("href", "")
        if tag == "a" and href:
            self._current_href = href
            self._current_anchor = []
            if "#" in href:
                self._in_profile_link = True
                self._profile_href = href
                self._profile_img_alt = None

        if tag == "img" and self._in_profile_link:
            alt = attr_map.get("alt", "").strip()
            if alt and _looks_like_name(alt):
                self._profile_img_alt = alt

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
            return

        if tag in SKIP_CONTAINER_TAGS and self._container_skip_depth:
            self._container_skip_depth -= 1
            return

        if self._ignore_depth and tag in {"div", "section", "aside", "nav", "footer", "header"}:
            self._ignore_depth -= 1
            return

        if self._skip_depth or self._container_skip_depth or self._ignore_depth:
            return

        if tag in {"h1", "h2", "h3", "h4"} and self._pending_heading_tag == tag:
            heading = _WHITESPACE.sub(" ", "".join(self._pending_heading_parts)).strip()
            match = self._detector.detect_from_heading(heading)
            self._section_name = match.section_name
            self._section_role = match.role
            self._section_is_member = match.is_member
            self._member_status = match.member_status
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
                if self._in_td:
                    self._table_links.append(link)
                elif self._in_dd:
                    self._dd_links.append(link)
                elif self._in_dt:
                    self._dt_links.append(link)
                else:
                    self._block_links.append(link)

            if self._in_profile_link and self._profile_img_alt:
                self._profile_cards.append(
                    (self._profile_img_alt, self._resolve_href(self._profile_href or ""))
                )
            elif self._in_profile_link and self._current_anchor:
                anchor = _WHITESPACE.sub(" ", " ".join(self._current_anchor)).strip()
                if _looks_like_name(anchor):
                    self._profile_cards.append(
                        (anchor, self._resolve_href(self._profile_href or ""))
                    )

            self._current_href = None
            self._current_anchor = []
            self._in_profile_link = False
            self._profile_href = None
            self._profile_img_alt = None

        if tag == "dt" and self._in_dt:
            self._in_dt = False
            return

        if tag == "dd" and self._in_dd:
            self._flush_dd()
            self._in_dd = False
            return

        if tag == "td" and self._in_td:
            cell = _WHITESPACE.sub(" ", " ".join(self._block_text)).strip()
            if cell:
                self._table_cells.append(cell)
            self._block_text = []
            self._block_links = []
            self._in_td = False
            return

        if tag == "tr" and self._in_tr:
            self._flush_table_row()
            self._in_tr = False
            return

        if tag in {"div", "article", "section", "li", "p"} and self._block_tag == tag:
            self._flush_block()
            self._block_tag = None
            self._block_class_id = ""

    def handle_data(self, data: str) -> None:
        if self._skip_depth or self._container_skip_depth or self._ignore_depth:
            return
        stripped = data.strip()
        if not stripped:
            return

        if self._pending_heading_tag is not None:
            self._pending_heading_parts.append(data)

        if self._current_href is not None:
            self._current_anchor.append(data)

        if self._in_dt:
            self._dt_text.append(data)
        elif self._in_dd:
            self._dd_text.append(data)
        elif self._in_td:
            self._block_text.append(data)
        elif self._block_tag:
            self._block_text.append(data)

    def _resolve_href(self, href: str) -> str | None:
        href = href.strip()
        if not href or href.startswith(("#", "javascript:", "tel:")):
            return None
        return urljoin(self._base_url, href)

    def _flush_block(self) -> None:
        if not self._block_tag:
            return
        text = _WHITESPACE.sub(" ", " ".join(self._block_text)).strip()
        if text:
            self._blocks.append(
                (text, self._block_links[:], self._block_class_id, self._block_tag, self._section_is_member)
            )

    def _flush_dt(self) -> None:
        if not self._dt_text:
            return
        dt_text = _WHITESPACE.sub(" ", " ".join(self._dt_text)).strip()
        plain_match = self._detector.detect_from_plain_text(dt_text)
        if plain_match:
            self._section_name = plain_match.section_name
            self._section_role = plain_match.role
            self._section_is_member = plain_match.is_member
            self._member_status = plain_match.member_status
            return
        # Defer name emission until paired dd content is available.

    def _flush_dd(self) -> None:
        text = _WHITESPACE.sub(" ", " ".join(self._dd_text)).strip()
        if not text:
            return
        dt_text = _WHITESPACE.sub(" ", " ".join(self._dt_text)).strip()
        combined = f"{dt_text} {text}".strip()
        links = list(self._dt_links) + list(self._dd_links)
        if self._section_is_member or _looks_like_name(dt_text):
            self._blocks.append(
                (combined, links, "definition-list", "dd", self._section_is_member or bool(dt_text))
            )
        self._dt_text = []
        self._dt_links = []

    def _flush_table_row(self) -> None:
        if not self._table_cells:
            return
        combined = " | ".join(self._table_cells)
        if self._section_is_member or _MEMBER_CONTAINER_CLASS_RE.search(combined.lower()):
            self._blocks.append(
                (combined, self._table_links[:], "table-row", "tr", self._section_is_member)
            )

    def finalize(self) -> tuple[list[_DeepBlock], list[tuple[str, str | None]]]:
        self._flush_block()
        blocks: list[_DeepBlock] = []
        seen: set[str] = set()

        for raw, links, class_id, tag, in_section in self._blocks:
            if not in_section and not _MEMBER_CONTAINER_CLASS_RE.search(class_id):
                continue

            name, profile_url = _extract_name_and_url(raw, links)
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)

            role_hint = _extract_role_hint(raw)
            blocks.append(
                _DeepBlock(
                    name=name,
                    raw_text=raw,
                    profile_url=profile_url,
                    role_hint=role_hint,
                    advisor_hint=_extract_advisor_hint(raw),
                    email=_extract_email(raw),
                    github_url=_extract_github_url(links),
                    section_name=self._section_name or "deep_member",
                    section_role=self._section_role,
                    member_status=self._member_status,
                    in_member_section=in_section,
                    links=list(links),
                )
            )

        profile_cards: list[tuple[str, str | None]] = []
        for name, url in self._profile_cards:
            key = name.lower()
            if key not in seen:
                profile_cards.append((name, url))
        return blocks, profile_cards


class DeepMemberExtractor:
    """
    Extract members from deep laboratory page layouts.

    Runs as a fourth pass after section, heading-card, and paragraph extractors.
    """

    def extract(
        self,
        html: str,
        base_url: str,
        already_seen: set[str],
        *,
        repeated_profiles: list[MemberPageEntry] | None = None,
    ) -> list[MemberPageEntry]:
        from research_group_agent.parser import MemberPageEntry  # noqa: PLC0415

        parser = _DeepMemberParser()
        parser.set_base_url(base_url)
        parser.feed(html)
        parser.close()
        blocks, profile_cards = parser.finalize()

        entries: list[MemberPageEntry] = []
        in_section = [b for b in blocks if b.in_member_section]
        standalone = [b for b in blocks if not b.in_member_section]

        for block in in_section:
            entry = self._to_entry(block, already_seen)
            if entry:
                entries.append(entry)

        if len(standalone) >= _MIN_DEEP_BLOCKS:
            qualified = [
                b for b in standalone
                if b.profile_url or b.role_hint or b.email or b.github_url
            ]
            if len(qualified) >= _MIN_DEEP_BLOCKS:
                for block in qualified:
                    entry = self._to_entry(block, already_seen)
                    if entry:
                        entries.append(entry)

        if repeated_profiles:
            for item in repeated_profiles:
                key = item.name.lower()
                if key in already_seen:
                    continue
                already_seen.add(key)
                item.section_name = item.section_name or "profile_card"
                entries.append(item)

        if len(profile_cards) >= _MIN_PROFILE_CARDS:
            for name, url in profile_cards:
                key = name.lower()
                if key in already_seen:
                    continue
                already_seen.add(key)
                entries.append(
                    MemberPageEntry(
                        name=name,
                        raw_text=name,
                        profile_url=url,
                        section_name="profile_card",
                        section_role=MemberRole.UNKNOWN,
                        member_status=MemberStatus.CURRENT,
                        in_member_section=True,
                    )
                )

        return entries

    def _to_entry(
        self,
        block: _DeepBlock,
        already_seen: set[str],
    ) -> MemberPageEntry | None:
        from research_group_agent.parser import MemberPageEntry  # noqa: PLC0415

        key = block.name.lower()
        if key in already_seen:
            return None
        already_seen.add(key)

        raw = block.raw_text
        if block.advisor_hint:
            raw = f"{raw} | advisor: {block.advisor_hint}"
        if block.email:
            raw = f"{raw} | {block.email}"

        return MemberPageEntry(
            name=block.name,
            raw_text=raw,
            profile_url=block.profile_url,
            role_hint=block.role_hint,
            section_name=block.section_name or "deep_member",
            section_role=block.section_role,
            member_status=block.member_status,
            in_member_section=True,
            links=list(block.links),
        )
