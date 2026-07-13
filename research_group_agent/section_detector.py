"""
SectionDetector — classify section boundaries in research group pages.

Supports three detection strategies:
  1. Heading hierarchy  — h1–h4 elements with keyword matching
  2. Plain-text inference — bold/text blocks that look like section markers
  3. DOM proximity — repeated structural patterns indicating member lists

Used by MemberPageParser to improve coverage over heading-only detection.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from research_group_agent.models import MemberRole, MemberStatus
from research_group_agent.precision_constants import (
    ALUMNI_SECTION_KEYWORDS,
    CURRENT_SECTION_KEYWORDS,
    LAB_NAME_SUFFIX_WORDS,
    MEMBER_OVERRIDE_WORDS,
    SKIP_SECTION_KEYWORDS,
)

_WHITESPACE = re.compile(r"\s+")

# Maximum character length for a plain-text string to qualify as a section header.
# Longer strings are likely prose paragraphs, not headings.
_MAX_PLAIN_SECTION_LENGTH = 350

# Plain-text section header patterns (ordered: most specific first).
# Each tuple: (compiled regex, MemberRole, MemberStatus)
_PLAIN_SECTION_PATTERNS: list[tuple[re.Pattern, MemberRole, MemberStatus]] = [
    # ── Current member patterns ──────────────────────────────────────────────
    (re.compile(r'\bcurrent\s+(?:ph\.?d\.?|doctoral|graduate|master)?\s*students?\b', re.I),
     MemberRole.PHD_STUDENT, MemberStatus.CURRENT),
    (re.compile(r'\bph\.?d\.?\s+students?\b', re.I),
     MemberRole.PHD_STUDENT, MemberStatus.CURRENT),
    (re.compile(r'\bdoctoral\s+students?\b', re.I),
     MemberRole.PHD_STUDENT, MemberStatus.CURRENT),
    (re.compile(r'\bgraduate\s+students?\b', re.I),
     MemberRole.PHD_STUDENT, MemberStatus.CURRENT),
    (re.compile(r'\bmaster(?:\'?s)?\s+students?\b', re.I),
     MemberRole.MASTER_STUDENT, MemberStatus.CURRENT),
    (re.compile(r'\bpostdoc(?:toral)?\s*(?:researchers?|fellows?|associates?|members?)?\b', re.I),
     MemberRole.POSTDOC, MemberStatus.CURRENT),
    (re.compile(r'\bcurrent\s+(?:lab|group|research)?\s*members?\b', re.I),
     MemberRole.UNKNOWN, MemberStatus.CURRENT),
    (re.compile(r'\blab\s+members?\b', re.I),
     MemberRole.UNKNOWN, MemberStatus.CURRENT),
    (re.compile(r'\bgroup\s+members?\b', re.I),
     MemberRole.UNKNOWN, MemberStatus.CURRENT),
    (re.compile(r'\bteam\s+members?\b', re.I),
     MemberRole.UNKNOWN, MemberStatus.CURRENT),
    (re.compile(r'\bresearch\s+(?:staff|team)\b', re.I),
     MemberRole.RESEARCH_STAFF, MemberStatus.CURRENT),
    (re.compile(r'\bour\s+team\b', re.I),
     MemberRole.UNKNOWN, MemberStatus.CURRENT),
    # Single-word / short-phrase exact-ish patterns
    (re.compile(r'^(?:current\s+)?people\s*:?\s*$', re.I),
     MemberRole.UNKNOWN, MemberStatus.CURRENT),
    (re.compile(r'^(?:current\s+)?students?\s*:?\s*$', re.I),
     MemberRole.PHD_STUDENT, MemberStatus.CURRENT),
    (re.compile(r'^researchers?\s*:?\s*$', re.I),
     MemberRole.UNKNOWN, MemberStatus.CURRENT),
    (re.compile(r'^postdocs?\s*:?\s*$', re.I),
     MemberRole.POSTDOC, MemberStatus.CURRENT),
    (re.compile(r'^collaborators?\s*:?\s*$', re.I),
     MemberRole.UNKNOWN, MemberStatus.CURRENT),
    # Sprint 2A — exact plain-text member section labels (optional colon)
    (re.compile(r'^current\s+students?\s*:?\s*$', re.I),
     MemberRole.PHD_STUDENT, MemberStatus.CURRENT),
    (re.compile(r'^graduate\s+students?\s*:?\s*$', re.I),
     MemberRole.PHD_STUDENT, MemberStatus.CURRENT),
    (re.compile(r'^ph\.?d\.?\s+students?\s*:?\s*$', re.I),
     MemberRole.PHD_STUDENT, MemberStatus.CURRENT),
    (re.compile(r'^former\s+members?\s*:?\s*$', re.I),
     MemberRole.ALUMNI, MemberStatus.ALUMNI),
    (re.compile(r'^alumni\s*:?\s*$', re.I),
     MemberRole.ALUMNI, MemberStatus.ALUMNI),
    (re.compile(r'\b(?:research\s+team|people\s+directory|student\s+directory|lab\s+members?)\b', re.I),
     MemberRole.UNKNOWN, MemberStatus.CURRENT),
    (re.compile(r'\baffiliated\s+students?\b', re.I),
     MemberRole.PHD_STUDENT, MemberStatus.CURRENT),
    (re.compile(r'\bvisitors?\b', re.I),
     MemberRole.VISITOR, MemberStatus.CURRENT),
    (re.compile(r'^(?:current\s+)?faculty\s*:?\s*$', re.I),
     MemberRole.PROFESSOR, MemberStatus.CURRENT),
    # ── Alumni / former member patterns ─────────────────────────────────────
    (re.compile(r'\bgradu(?:ated?|al)\s+(?:ph\.?d\.?\s+)?students?\b', re.I),
     MemberRole.ALUMNI, MemberStatus.ALUMNI),
    (re.compile(r'\bpast\s+(?:members?|students?|postdocs?|researchers?)\b', re.I),
     MemberRole.ALUMNI, MemberStatus.ALUMNI),
    (re.compile(r'\bformer\s+(?:members?|students?|postdocs?|researchers?)\b', re.I),
     MemberRole.ALUMNI, MemberStatus.ALUMNI),
    (re.compile(r'\balumni?\b', re.I),
     MemberRole.ALUMNI, MemberStatus.ALUMNI),
    (re.compile(r'\bprevious\s+(?:members?|students?)\b', re.I),
     MemberRole.ALUMNI, MemberStatus.ALUMNI),
    (re.compile(r'\bph\.?d\.?\s+alumni?\b', re.I),
     MemberRole.ALUMNI, MemberStatus.ALUMNI),
]


def _normalize(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip().lower()


def is_lab_name_heading(normalized: str) -> bool:
    """
    Return True if the heading text looks like a lab's proper name rather than
    a member-section header.

    Detects patterns like:
      - "berkeley netsys lab"          → ends with "lab", 3+ words
      - "distributed systems laboratory" → contains "laboratory"
      - "sail@princeton"               → contains "@"
      - "symbiotic lab"                → ends with "lab", 2 words

    Returns False when member-override words are present:
      - "lab members"     → has "members"  → NOT a lab name
      - "our team"        → "team" not a suffix word → not detected here
      - "current students"→ has "students" → NOT a lab name
    """
    if not normalized:
        return False

    # If any member-override word is present, it's a member section
    if any(mw in normalized for mw in MEMBER_OVERRIDE_WORDS):
        return False

    words = normalized.split()

    # Single-word headings ("lab", "team", "people") are section headers
    if len(words) <= 1:
        return False

    # Headings with "@" are lab names (e.g. "sail@princeton")
    if "@" in normalized:
        return True

    # If any word is "laboratory" or "laboratories" → it's a lab name
    if any(w in ("laboratory", "laboratories") for w in words):
        return True

    # If the last word is a lab-suffix indicator AND there's >= 1 preceding word
    last_word = words[-1].lower()
    if last_word in LAB_NAME_SUFFIX_WORDS and len(words) >= 2:
        return True

    return False


@dataclass
class SectionMatch:
    """
    Result of section boundary detection.

    Fields
    ------
    section_name    Normalized heading / inferred label.
    role            Most specific MemberRole for this section.
    member_status   CURRENT, ALUMNI, or UNKNOWN.
    is_member       True if this section should yield member entries.
    confidence      Detection confidence in [0, 1].
    detection_method  "heading", "plain_text", or "inferred".
    """

    section_name: str
    role: MemberRole
    member_status: MemberStatus
    is_member: bool
    confidence: float
    detection_method: str


class SectionDetector:
    """
    Classify section boundaries in research group HTML pages.

    Three detection strategies are available:

    1. detect_from_heading() — applies to h1–h4 elements
    2. detect_from_plain_text() — applies to paragraph / div text that looks
       like a section marker (e.g. "Current Ph.D. Students:")
    3. is_lab_name_heading() (static) — distinguish lab titles from sections
    """

    # ── Public API ───────────────────────────────────────────────────────────

    def detect_from_heading(self, heading_text: str) -> SectionMatch:
        """
        Classify an h1–h4 element as a section boundary.

        Always returns a SectionMatch; is_member=False when not a member section.
        """
        normalized = _normalize(heading_text)

        if not normalized:
            return SectionMatch("", MemberRole.UNKNOWN, MemberStatus.UNKNOWN, False, 0.0, "heading")

        # Structural skip sections
        for skip in SKIP_SECTION_KEYWORDS:
            if skip in normalized:
                return SectionMatch(
                    normalized, MemberRole.UNKNOWN, MemberStatus.UNKNOWN, False, 0.0, "heading"
                )

        # Lab name headings are titles, not member sections
        if is_lab_name_heading(normalized):
            return SectionMatch(
                normalized, MemberRole.UNKNOWN, MemberStatus.UNKNOWN, False, 0.0, "heading"
            )

        # Alumni keywords take priority over current (they're often substrings too)
        for keyword, role in ALUMNI_SECTION_KEYWORDS.items():
            if keyword in normalized:
                return SectionMatch(
                    normalized, role, MemberStatus.ALUMNI, True, 0.9, "heading"
                )

        # Current member keywords
        for keyword, role in CURRENT_SECTION_KEYWORDS.items():
            if keyword in normalized:
                return SectionMatch(
                    normalized, role, MemberStatus.CURRENT, True, 0.9, "heading"
                )

        return SectionMatch(
            normalized, MemberRole.UNKNOWN, MemberStatus.UNKNOWN, False, 0.3, "heading"
        )

    def detect_from_plain_text(self, text: str) -> SectionMatch | None:
        """
        Detect a section boundary from non-heading text (paragraph, div, etc.).

        Returns None if the text does not match any section-header pattern.

        Only matches when:
          - The text is ≤ _MAX_PLAIN_SECTION_LENGTH characters
          - No skip section keywords are present
          - A known section pattern matches
        """
        if not text:
            return None

        stripped = text.strip()
        if not stripped or len(stripped) > _MAX_PLAIN_SECTION_LENGTH:
            return None

        normalized = _normalize(stripped)

        # Reject known skip sections
        for skip in SKIP_SECTION_KEYWORDS:
            if skip in normalized:
                return None

        for pattern, role, member_status in _PLAIN_SECTION_PATTERNS:
            if pattern.search(stripped):
                # Build a canonical section name (cap at 80 chars to avoid noisy labels)
                section_name = normalized[:80].rstrip()

                return SectionMatch(
                    section_name=section_name,
                    role=role,
                    member_status=member_status,
                    is_member=True,
                    confidence=0.72,
                    detection_method="plain_text",
                )

        return None

    def is_section_header_only(self, text: str) -> bool:
        """
        Return True when *text* is a standalone section label (not member content).

        Used by _SectionAwareParser to distinguish section headers in p/div/strong
        blocks from actual member entries.
        """
        if not text:
            return False
        stripped = text.strip()
        if not stripped or len(stripped) > _MAX_PLAIN_SECTION_LENGTH:
            return False
        return self.detect_from_plain_text(stripped) is not None

    @staticmethod
    def is_lab_name_heading(normalized: str) -> bool:
        """Proxy for the module-level helper."""
        return is_lab_name_heading(normalized)
