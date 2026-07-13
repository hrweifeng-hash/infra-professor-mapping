"""PR22 — HomepageMemberDetector.

Detects whether a professor's homepage contains research group member
information so the pipeline can inject it as a competing candidate page.

This implements Part 1 (Homepage Candidate Detection) of PR22.

Architecture:
    Homepage
        ↓
    HomepageMemberDetector
        ↓
    homepage_is_group_page?
        ├── YES → cache ParsedMemberPage → Homepage Candidate (competes with others)
        └── NO  → Homepage Candidate (no pre-parse, ranked normally)
        ↓
    HomepageGraph → NavigationGuard → CandidatePageRanker → top-N pages
        ↓
    Fetch + Classify + Extract each candidate
        ↓
    MemberMerger → best result wins

The detector never terminates navigation.  When the homepage contains member
content, the pre-parsed result is cached so the pipeline can skip a redundant
fetch and bypass the PageClassifier (whose member-page heuristics are not
calibrated for professor homepages).  The homepage then competes fairly against
dedicated /people, /members, and /students pages in the ranker.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from research_group_agent.models import MemberStatus
from research_group_agent.parser import MemberPageParser, ParsedMemberPage

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

#: Minimum number of extracted member entries for homepage to qualify as the
#: research group page.  Increase to be more conservative; decrease to recover
#: more "Homepage Embedded" professors.
MIN_HOMEPAGE_MEMBER_COUNT: int = 3

#: Minimum paragraph-member count to treat a flat paragraph layout as a
#: recognizable member structure (PR24).
MIN_PARAGRAPH_STRUCTURE_COUNT: int = 3

#: Master switch for homepage-first detection.  Set to False to restore
#: pure PR21 navigation behaviour (navigate away from homepage always).
ENABLE_HOMEPAGE_FIRST: bool = True


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class HomepageMemberDetectionResult:
    """Result of running HomepageMemberDetector on a professor homepage."""

    homepage_url: str
    homepage_is_group_page: bool
    member_count: int
    has_member_sections: bool
    has_heading_cards: bool
    detection_reason: str
    has_paragraph_layout: bool = False
    #: Pre-parsed page — only set when homepage_is_group_page is True so
    #: the pipeline can reuse the parse result without re-fetching.
    parsed: ParsedMemberPage | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Detector
# ─────────────────────────────────────────────────────────────────────────────

class HomepageMemberDetector:
    """
    Detect member content on a professor's homepage for use as a candidate page.

    Runs the existing MemberPageParser (including HeadingCardExtractor from PR21)
    on the homepage HTML and checks for sufficient member-related content.

    Qualification criteria (all must hold for homepage_is_group_page=True):
      1. member_count >= min_member_count  (default 3)
      2. At least one recognizable member structure:
           - traditional member sections (SectionDetector-detected, non-empty)
           - heading-card entries (HeadingCardExtractor)
           - repeated profile patterns (>= 2 profiles)
           - paragraph-member layout (paragraph_member_count >= 3, PR24)

    When the homepage qualifies, the pre-parsed result is returned inside
    HomepageMemberDetectionResult.parsed so the pipeline can:
      - skip re-fetching the homepage when it is selected as a candidate
      - bypass the PageClassifier (calibrated for dedicated member pages, not
        professor homepages)

    The detector does NOT terminate pipeline navigation.  It is a signal
    generator only — the ranking framework decides which page wins.

    Logging
    -------
    Decisions are logged at INFO level:
      - "Homepage accepted as group page: <url>"
      - "Homepage rejected: below threshold (<n> < <threshold> members)"
      - "Homepage rejected: no recognizable member structure"
    """

    def __init__(
        self,
        min_member_count: int = MIN_HOMEPAGE_MEMBER_COUNT,
        enabled: bool = ENABLE_HOMEPAGE_FIRST,
    ):
        self.min_member_count = min_member_count
        self.enabled = enabled
        self._parser = MemberPageParser()

    def detect(
        self,
        html: str,
        homepage_url: str,
    ) -> HomepageMemberDetectionResult:
        """
        Parse homepage HTML and decide whether it qualifies as a group page.

        Parameters
        ----------
        html:
            Raw HTML of the professor homepage (may be empty string).
        homepage_url:
            Canonical URL used as base_url for the parser and for logging.

        Returns
        -------
        HomepageMemberDetectionResult
            .homepage_is_group_page  True when the homepage qualifies.
            .parsed                  ParsedMemberPage when qualifies; else None.
        """
        if not self.enabled:
            return HomepageMemberDetectionResult(
                homepage_url=homepage_url,
                homepage_is_group_page=False,
                member_count=0,
                has_member_sections=False,
                has_heading_cards=False,
                has_paragraph_layout=False,
                detection_reason="HomepageFirst detection disabled (ENABLE_HOMEPAGE_FIRST=False)",
            )

        if not html:
            return HomepageMemberDetectionResult(
                homepage_url=homepage_url,
                homepage_is_group_page=False,
                member_count=0,
                has_member_sections=False,
                has_heading_cards=False,
                has_paragraph_layout=False,
                detection_reason="No homepage HTML available",
            )

        parsed = self._parser.parse(html, base_url=homepage_url)

        has_member_sections = any(
            s.is_member_section
            and s.member_status == MemberStatus.CURRENT
            and s.entry_count > 0
            for s in parsed.sections
        )
        has_heading_cards = parsed.heading_card_count > 0
        has_repeated_profiles = len(parsed.repeated_profiles) >= 2
        has_paragraph_layout = (
            parsed.paragraph_member_count >= MIN_PARAGRAPH_STRUCTURE_COUNT
        )

        member_count = len(parsed.entries)

        has_recognizable_structure = (
            has_member_sections
            or has_heading_cards
            or has_repeated_profiles
            or has_paragraph_layout
        )

        if member_count >= self.min_member_count and has_recognizable_structure:
            if has_paragraph_layout:
                structure_detail = (
                    f"paragraph layout ({parsed.paragraph_member_count} members)"
                )
            else:
                structure_detail = (
                    f"member_sections={has_member_sections}, "
                    f"heading_cards={parsed.heading_card_count}, "
                    f"repeated_profiles={len(parsed.repeated_profiles)}"
                )
            reason = (
                f"Homepage contains {member_count} member entries "
                f"(threshold={self.min_member_count}, {structure_detail})"
            )
            logger.info(
                "[PR24] Homepage accepted as group page: %s — %s",
                homepage_url,
                reason,
            )
            return HomepageMemberDetectionResult(
                homepage_url=homepage_url,
                homepage_is_group_page=True,
                member_count=member_count,
                has_member_sections=has_member_sections,
                has_heading_cards=has_heading_cards,
                has_paragraph_layout=has_paragraph_layout,
                detection_reason=reason,
                parsed=parsed,
            )

        # Build rejection reason
        if member_count < self.min_member_count:
            reason = (
                f"Homepage rejected: below threshold "
                f"({member_count} < {self.min_member_count} members)"
            )
        elif (
            0 < parsed.paragraph_member_count < MIN_PARAGRAPH_STRUCTURE_COUNT
        ):
            reason = (
                f"Homepage rejected: paragraph layout below threshold "
                f"({parsed.paragraph_member_count} members)"
            )
        else:
            reason = (
                f"Homepage rejected: {member_count} entries but no recognizable "
                "member structure (no member sections, heading cards, "
                "repeated profiles, or paragraph layout)"
            )

        logger.info("[PR24] %s for %s", reason, homepage_url)
        return HomepageMemberDetectionResult(
            homepage_url=homepage_url,
            homepage_is_group_page=False,
            member_count=member_count,
            has_member_sections=has_member_sections,
            has_heading_cards=has_heading_cards,
            has_paragraph_layout=has_paragraph_layout,
            detection_reason=reason,
            parsed=None,
        )
