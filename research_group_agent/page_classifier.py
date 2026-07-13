"""PageClassifier — determines whether a fetched page is a research group page.

PR16 additions:
  - PageClassificationScore provides a named, inspectable score breakdown.
  - Evidence from repeated profile detection (profile cards).
  - Research-role keyword evidence from visible text.
  - Pages are no longer rejected solely because standard headings are missing;
    repeated profile patterns or strong URL/title signals can still pass.
  - MIN_ACCEPTABLE_SCORE slightly relaxed from 0.45 to 0.40 for evidence-rich
    pages; the hard requirement for at least one member section with entries
    still applies (unless overridden by profile-card evidence).

PR24 additions:
  - Paragraph-member layouts (paragraph_member_count >= 3) are recognised as
    valid member-page evidence with a score comparable to member sections.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlparse

from research_group_agent.homepage_member_detector import MIN_PARAGRAPH_STRUCTURE_COUNT
from research_group_agent.models import MemberStatus
from research_group_agent.parser import ParsedMemberPage
from research_group_agent.precision_constants import (
    DEPARTMENT_URL_PATTERNS,
    GROUP_URL_PATTERNS,
    SKIP_SECTION_KEYWORDS,
)


class PageType(str, Enum):
    RESEARCH_GROUP = "research_group"
    LAB_MEMBERS = "lab_members"
    TEAM_PAGE = "team_page"
    STUDENT_PAGE = "student_page"
    DEPARTMENT_DIRECTORY = "department_directory"
    FACULTY_DIRECTORY = "faculty_directory"
    RESEARCH_AREA_PAGE = "research_area_page"
    PROJECT_PAGE = "project_page"
    COURSE_PAGE = "course_page"
    ADMINISTRATIVE_PAGE = "administrative_page"
    GENERIC_HOMEPAGE = "generic_homepage"
    UNKNOWN = "unknown"


ACCEPTABLE_PAGE_TYPES: frozenset[PageType] = frozenset({
    PageType.RESEARCH_GROUP,
    PageType.LAB_MEMBERS,
    PageType.TEAM_PAGE,
    PageType.STUDENT_PAGE,
})

# Visible-text keywords that support a research-group/member-page classification.
_RESEARCH_ROLE_KEYWORDS: tuple[str, ...] = (
    "phd student", "ph.d. student", "doctoral student",
    "graduate student", "postdoc", "research staff", "research scientist",
    "advisor", "advisee", "co-advised", "current member",
)

_STUDENT_ROLE_KEYWORDS: tuple[str, ...] = (
    "phd", "ph.d.", "doctoral", "graduate student",
    "master student", "undergraduate research",
)

_HOMEPAGE_LINK_KEYWORDS: tuple[str, ...] = (
    "personal website", "personal page", "homepage",
    "github.com/", "scholar.google", "linkedin.com/in/",
)

logger = logging.getLogger(__name__)


@dataclass
class PageClassificationScore:
    """
    Evidence-based score breakdown for PageClassifier decisions.

    Fields
    ------
    url_score         Score from URL pattern analysis.
    title_score       Score from page title / heading analysis.
    section_score     Score from parser-detected member sections.
    profile_score     Score from repeated profile-card detection.
    role_score        Score from research-role keywords in visible text.
    negative_score    Penalty from directory / administrative signals.
    final_score       Combined score used for acceptance threshold.
    """

    url_score: float = 0.0
    title_score: float = 0.0
    section_score: float = 0.0
    profile_score: float = 0.0
    role_score: float = 0.0
    paragraph_layout_bonus: float = 0.0
    negative_score: float = 0.0

    @property
    def final_score(self) -> float:
        positive = (
            self.url_score
            + self.title_score
            + self.section_score
            + self.profile_score
            + self.role_score
            + self.paragraph_layout_bonus
        )
        penalized = positive * max(0.0, 1.0 - self.negative_score)
        return round(min(1.0, max(0.0, penalized)), 3)

    def to_dict(self) -> dict:
        return {
            "url_score": round(self.url_score, 3),
            "title_score": round(self.title_score, 3),
            "section_score": round(self.section_score, 3),
            "profile_score": round(self.profile_score, 3),
            "role_score": round(self.role_score, 3),
            "paragraph_layout_bonus": round(self.paragraph_layout_bonus, 3),
            "negative_score": round(self.negative_score, 3),
            "final_score": self.final_score,
        }


@dataclass
class PageClassification:
    page_type: PageType
    confidence: float
    is_acceptable: bool
    reason: str
    score_breakdown: PageClassificationScore = field(
        default_factory=PageClassificationScore
    )


class PageClassifier:
    """
    Determine whether a fetched page represents a research group / member listing.

    Rejects department directories, faculty listings, and administrative pages.
    Evidence-based: uses URL, title, section, profile-card, and role signals.
    """

    MIN_ACCEPTABLE_SCORE = 0.40
    MIN_MEMBER_SECTIONS = 1

    def classify(
        self,
        parsed: ParsedMemberPage,
        page_url: str,
        page_title: str = "",
    ) -> PageClassification:
        url_lower = page_url.lower()
        title_lower = (page_title or parsed.page_title or "").lower()
        visible_lower = parsed.visible_text.lower()

        # ── Initialize per-type scores ───────────────────────────────────────
        scores: dict[PageType, float] = {pt: 0.0 for pt in PageType}
        breakdown = PageClassificationScore()

        # ── URL signals ──────────────────────────────────────────────────────
        url_group_hits = sum(1 for p in GROUP_URL_PATTERNS if p in url_lower)
        url_dept_hits = sum(1 for p in DEPARTMENT_URL_PATTERNS if p in url_lower)

        if url_group_hits:
            scores[PageType.LAB_MEMBERS] += 0.20 * url_group_hits
            scores[PageType.RESEARCH_GROUP] += 0.15 * url_group_hits
            breakdown.url_score = min(0.35, 0.20 * url_group_hits)

        if url_dept_hits:
            scores[PageType.FACULTY_DIRECTORY] += 0.35
            scores[PageType.DEPARTMENT_DIRECTORY] += 0.30
            scores[PageType.ADMINISTRATIVE_PAGE] += 0.20
            breakdown.negative_score += 0.40

        if "faculty" in url_lower and "member" not in url_lower:
            scores[PageType.FACULTY_DIRECTORY] += 0.25
            breakdown.negative_score += 0.20

        # ── Title / heading signals ──────────────────────────────────────────
        if any(kw in title_lower for kw in ("lab", "group", "members", "team")):
            scores[PageType.RESEARCH_GROUP] += 0.25
            scores[PageType.LAB_MEMBERS] += 0.20
            breakdown.title_score += 0.20

        if any(kw in title_lower for kw in ("people", "students", "researchers", "personnel")):
            scores[PageType.LAB_MEMBERS] += 0.25
            scores[PageType.STUDENT_PAGE] += 0.20
            breakdown.title_score += 0.20

        if any(kw in title_lower for kw in ("faculty", "directory", "department")):
            scores[PageType.FACULTY_DIRECTORY] += 0.35
            scores[PageType.DEPARTMENT_DIRECTORY] += 0.25
            breakdown.negative_score += 0.25

        if any(kw in title_lower for kw in ("admissions", "academics", "courses")):
            scores[PageType.ADMINISTRATIVE_PAGE] += 0.30
            scores[PageType.COURSE_PAGE] += 0.25
            breakdown.negative_score += 0.25

        if any(kw in title_lower for kw in ("publications", "projects", "research areas")):
            scores[PageType.PROJECT_PAGE] += 0.25
            scores[PageType.RESEARCH_AREA_PAGE] += 0.25

        # ── Section structure signals ────────────────────────────────────────
        member_sections = [
            s
            for s in parsed.sections
            if s.is_member_section
            and s.member_status == MemberStatus.CURRENT
            and s.entry_count > 0
        ]
        if member_sections:
            scores[PageType.RESEARCH_GROUP] += 0.35
            scores[PageType.LAB_MEMBERS] += 0.30
            breakdown.section_score += 0.35
            if any("student" in s.name.lower() for s in member_sections):
                scores[PageType.STUDENT_PAGE] += 0.25
            if any("team" in s.name.lower() for s in member_sections):
                scores[PageType.TEAM_PAGE] += 0.25

        # Inferred sections (plain-text headers detected by SectionDetector)
        inferred_sections = [
            s for s in parsed.sections
            if s.is_member_section and getattr(s, "detection_method", "heading") == "plain_text"
        ]
        if inferred_sections:
            scores[PageType.RESEARCH_GROUP] += 0.15
            scores[PageType.LAB_MEMBERS] += 0.10
            breakdown.section_score += 0.10

        # PR24: paragraph-member layout evidence
        if parsed.paragraph_member_count >= MIN_PARAGRAPH_STRUCTURE_COUNT:
            scores[PageType.RESEARCH_GROUP] += 0.35
            scores[PageType.LAB_MEMBERS] += 0.30
            breakdown.paragraph_layout_bonus += 0.35

        # High entry count without member sections → likely directory
        if (
            len(parsed.entries) > 30
            and not member_sections
            and parsed.paragraph_member_count < MIN_PARAGRAPH_STRUCTURE_COUNT
        ):
            scores[PageType.FACULTY_DIRECTORY] += 0.40
            scores[PageType.DEPARTMENT_DIRECTORY] += 0.35
            breakdown.negative_score += 0.30

        # ── Repeated profile detection ───────────────────────────────────────
        if parsed.profile_card_count >= 4:
            scores[PageType.RESEARCH_GROUP] += 0.20
            scores[PageType.LAB_MEMBERS] += 0.20
            breakdown.profile_score += 0.20
        if parsed.repeated_profiles:
            scores[PageType.RESEARCH_GROUP] += 0.15
            breakdown.profile_score += 0.10

        # ── Research role keywords in visible text ───────────────────────────
        role_hits = sum(1 for kw in _RESEARCH_ROLE_KEYWORDS if kw in visible_lower)
        if role_hits:
            bonus = min(0.20, 0.05 * role_hits)
            scores[PageType.RESEARCH_GROUP] += bonus
            scores[PageType.LAB_MEMBERS] += bonus
            breakdown.role_score += bonus

        student_hits = sum(1 for kw in _STUDENT_ROLE_KEYWORDS if kw in visible_lower)
        if student_hits:
            scores[PageType.STUDENT_PAGE] += min(0.15, 0.05 * student_hits)

        homepage_hits = sum(1 for kw in _HOMEPAGE_LINK_KEYWORDS if kw in visible_lower)
        if homepage_hits:
            scores[PageType.RESEARCH_GROUP] += min(0.10, 0.03 * homepage_hits)
            breakdown.role_score += min(0.05, 0.02 * homepage_hits)

        # ── Visible text negatives ───────────────────────────────────────────
        if "faculty type" in visible_lower or "faculty directory" in visible_lower:
            scores[PageType.FACULTY_DIRECTORY] += 0.30
            breakdown.negative_score += 0.20

        if "undergraduate program" in visible_lower or "graduate admissions" in visible_lower:
            scores[PageType.ADMINISTRATIVE_PAGE] += 0.25
            breakdown.negative_score += 0.15

        # ── Determine best page type ─────────────────────────────────────────
        page_type = max(scores, key=scores.get)
        raw_confidence = scores[page_type]

        # Apply negative penalty to final confidence
        confidence = min(1.0, raw_confidence * max(0.0, 1.0 - breakdown.negative_score * 0.5))
        confidence = round(confidence, 3)

        # ── Acceptability gate ───────────────────────────────────────────────
        # Primary path: standard member sections with entries
        has_member_content = len(member_sections) >= self.MIN_MEMBER_SECTIONS

        # Alternative path: repeated profile card evidence
        has_profile_evidence = (
            parsed.profile_card_count >= 8
            or len(parsed.repeated_profiles) >= 4
        )

        # PR24: paragraph-member layout evidence
        has_paragraph_evidence = (
            parsed.paragraph_member_count >= MIN_PARAGRAPH_STRUCTURE_COUNT
        )

        is_acceptable = (
            page_type in ACCEPTABLE_PAGE_TYPES
            and confidence >= self.MIN_ACCEPTABLE_SCORE
            and (has_member_content or has_profile_evidence or has_paragraph_evidence)
        )

        # Build reason string
        if page_type in ACCEPTABLE_PAGE_TYPES and not (
            has_member_content or has_profile_evidence or has_paragraph_evidence
        ):
            is_acceptable = False
            if (
                0 < parsed.paragraph_member_count < MIN_PARAGRAPH_STRUCTURE_COUNT
            ):
                reason = (
                    f"Paragraph layout below threshold "
                    f"({parsed.paragraph_member_count} members, "
                    f"need {MIN_PARAGRAPH_STRUCTURE_COUNT})"
                )
            elif parsed.profile_card_count > 0:
                reason = (
                    f"No member sections found; {parsed.profile_card_count} profile cards "
                    "detected but below threshold"
                )
            else:
                reason = "No member sections found on page"
        elif is_acceptable:
            evidence_parts = []
            if member_sections:
                evidence_parts.append(f"{len(member_sections)} member section(s)")
            if has_profile_evidence:
                evidence_parts.append(f"{parsed.profile_card_count} profile cards")
            if has_paragraph_evidence:
                evidence_parts.append(
                    f"paragraph layout ({parsed.paragraph_member_count} members)"
                )
            evidence_str = ", ".join(evidence_parts) or "unknown"
            reason = f"Classified as {page_type.value} with {evidence_str}"
        else:
            reason = f"Rejected as {page_type.value} (confidence={confidence:.2f})"

        logger.debug(
            "[PR24] PageClassifier: url=%s paragraph_member_count=%d "
            "paragraph_layout_bonus=%.3f classification_score=%.3f acceptable=%s",
            page_url,
            parsed.paragraph_member_count,
            breakdown.paragraph_layout_bonus,
            breakdown.final_score,
            is_acceptable,
        )

        return PageClassification(
            page_type=page_type,
            confidence=confidence,
            is_acceptable=is_acceptable,
            reason=reason,
            score_breakdown=breakdown,
        )
