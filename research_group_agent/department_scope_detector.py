"""DepartmentScopeDetector — recognise department-scale pages vs research groups.

PR26 addition: lightweight recognition layer using multiple weak signals.
Does not reject pages or alter extraction — exposes scope metadata only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from research_group_agent.models import MemberRole
from research_group_agent.parser import ParsedMemberPage
from research_group_agent.precision_constants import DEPARTMENT_URL_PATTERNS

# URL path/query substrings that suggest a department- or school-scale roster.
_URL_SCOPE_KEYWORDS: tuple[tuple[str, float, str], ...] = (
    ("faculty", 0.25, "faculty keyword in URL"),
    ("directory", 0.25, "directory keyword in URL"),
    ("staff", 0.15, "staff keyword in URL"),
    ("department", 0.25, "department keyword in URL"),
    ("graduate-program", 0.20, "graduate-program keyword in URL"),
    ("graduate-students", 0.20, "graduate-students keyword in URL"),
    ("postdocs", 0.20, "postdocs keyword in URL"),
    ("/people/faculty", 0.30, "faculty people path in URL"),
    ("/directory/", 0.25, "directory path in URL"),
)

# Page-title phrases suggesting an institution-wide listing.
_TITLE_SCOPE_KEYWORDS: tuple[tuple[str, float, str], ...] = (
    ("faculty", 0.25, "Faculty in page title"),
    ("department", 0.25, "Department in page title"),
    ("directory", 0.20, "Directory in page title"),
    ("all members", 0.20, "All Members in page title"),
    ("graduate program", 0.20, "Graduate Program in page title"),
    ("graduate students", 0.20, "Graduate Students in page title"),
    ("people", 0.10, "People in page title"),
)

_FACULTY_ROLE_KEYWORDS: tuple[str, ...] = (
    "faculty",
    "professor",
    "associate professor",
    "assistant professor",
    "lecturer",
    "instructor",
    "emeritus",
    "adjunct",
)

# Lab/group URL hints — reduce false positives on small team pages.
_GROUP_URL_HINTS: tuple[str, ...] = (
    "/lab",
    "/group",
    "/team",
    "/members",
    ".github.io",
    "/~",
)

_LOG_CONFIDENCE_THRESHOLD = 0.70
_DETECT_CONFIDENCE_THRESHOLD = 0.55


@dataclass
class DepartmentScopeResult:
    """Scope classification for a parsed member page."""

    is_department_page: bool
    confidence: float
    matched_rules: list[str] = field(default_factory=list)
    page_url: str = ""
    parsed_entry_count: int = 0
    faculty_role_count: int = 0
    distinct_profile_url_count: int = 0

    @property
    def department_scope(self) -> bool:
        """Alias used by downstream consumers."""
        return self.is_department_page

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_department_page": self.is_department_page,
            "department_scope": self.is_department_page,
            "confidence": round(self.confidence, 3),
            "matched_rules": list(self.matched_rules),
            "page_url": self.page_url,
            "parsed_entry_count": self.parsed_entry_count,
            "faculty_role_count": self.faculty_role_count,
            "distinct_profile_url_count": self.distinct_profile_url_count,
        }


class DepartmentScopeDetector:
    """
    Detect whether a parsed page represents a department-scale directory
    rather than an individual research group roster.

    Uses multiple weak signals; no single signal is sufficient on its own.
    """

    def detect(
        self,
        parsed: ParsedMemberPage,
        page_url: str,
        page_title: str | None = None,
    ) -> DepartmentScopeResult:
        matched_rules: list[str] = []
        score = 0.0

        url_lower = (page_url or "").lower()
        path_lower = urlparse(page_url or "").path.lower()
        title_lower = (page_title or parsed.page_title or "").lower()
        parsed_count = len(parsed.entries)

        # ── URL signals ───────────────────────────────────────────────────────
        for pattern in DEPARTMENT_URL_PATTERNS:
            if pattern in url_lower or pattern in path_lower:
                matched_rules.append(f"department URL pattern: {pattern}")
                score += 0.25
                break

        for keyword, weight, label in _URL_SCOPE_KEYWORDS:
            if keyword in url_lower or keyword in path_lower:
                matched_rules.append(label)
                score += weight

        if "postdocs" in url_lower and parsed_count >= 15:
            matched_rules.append(f"{parsed_count} postdocs directory entries")
            score += 0.25

        # ── Title signals ─────────────────────────────────────────────────────
        for keyword, weight, label in _TITLE_SCOPE_KEYWORDS:
            if keyword in title_lower:
                matched_rules.append(label)
                score += weight

        # ── Parsed roster size ────────────────────────────────────────────────
        if parsed_count > 100:
            matched_rules.append(f"{parsed_count} parsed entries")
            score += 0.35
        elif parsed_count > 50:
            matched_rules.append(f"{parsed_count} parsed entries")
            score += 0.20
        elif parsed_count > 30:
            matched_rules.append(f"{parsed_count} parsed entries")
            score += 0.10

        # ── Repeated faculty role labels ──────────────────────────────────────
        faculty_role_count = self._count_faculty_roles(parsed)
        if faculty_role_count >= 20:
            matched_rules.append(f"{faculty_role_count} faculty roles")
            score += 0.30
        elif faculty_role_count >= 10:
            matched_rules.append(f"{faculty_role_count} faculty roles")
            score += 0.20
        elif faculty_role_count >= 5:
            matched_rules.append(f"{faculty_role_count} faculty roles")
            score += 0.10

        # ── Distinct profile URLs ─────────────────────────────────────────────
        distinct_urls = {
            entry.profile_url
            for entry in parsed.entries
            if entry.profile_url
        }
        distinct_profile_url_count = len(distinct_urls)
        if distinct_profile_url_count >= 30:
            matched_rules.append(f"{distinct_profile_url_count} distinct profile URLs")
            score += 0.15
        elif distinct_profile_url_count >= 15:
            matched_rules.append(f"{distinct_profile_url_count} distinct profile URLs")
            score += 0.10

        # ── Group-page dampening (avoid false positives on small lab pages) ───
        if parsed_count <= 25 and faculty_role_count <= 2:
            if any(hint in url_lower for hint in _GROUP_URL_HINTS):
                score *= 0.5
                matched_rules.append("small lab/group page dampening")

        confidence = round(min(1.0, score), 3)
        has_scope_url_or_title = any(
            rule.endswith("in URL") or rule.endswith("in page title")
            for rule in matched_rules
        )
        is_department = confidence >= _DETECT_CONFIDENCE_THRESHOLD and (
            has_scope_url_or_title or confidence >= 0.75
        )

        return DepartmentScopeResult(
            is_department_page=is_department,
            confidence=confidence,
            matched_rules=_dedupe_rules(matched_rules),
            page_url=page_url,
            parsed_entry_count=parsed_count,
            faculty_role_count=faculty_role_count,
            distinct_profile_url_count=distinct_profile_url_count,
        )

    @staticmethod
    def _count_faculty_roles(parsed: ParsedMemberPage) -> int:
        count = 0
        for entry in parsed.entries:
            haystack = " ".join(
                filter(
                    None,
                    [
                        entry.section_name or "",
                        entry.role_hint or "",
                        entry.raw_text or "",
                        entry.section_role.value
                        if entry.section_role != MemberRole.UNKNOWN
                        else "",
                    ],
                )
            ).lower()
            if any(keyword in haystack for keyword in _FACULTY_ROLE_KEYWORDS):
                count += 1
            elif entry.section_role == MemberRole.PROFESSOR:
                count += 1
        return count

    @staticmethod
    def should_log(result: DepartmentScopeResult) -> bool:
        return result.is_department_page and result.confidence >= _LOG_CONFIDENCE_THRESHOLD


def _dedupe_rules(rules: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for rule in rules:
        if rule not in seen:
            seen.add(rule)
            ordered.append(rule)
    return ordered


def format_department_scope_log(professor_name: str, result: DepartmentScopeResult) -> str:
    """Format the PR26 console log block for a detected department page."""
    lines = [
        "Department Scope Detector",
        f"  professor={professor_name}",
        f"  url={result.page_url}",
        f"  department_scope={result.is_department_page}",
        f"  confidence={result.confidence:.2f}",
        "  rules:",
    ]
    for rule in result.matched_rules:
        lines.append(f"    - {rule}")
    return "\n".join(lines)
