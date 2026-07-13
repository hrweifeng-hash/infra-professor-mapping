"""Validation-state classification for identity candidates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from research_group_agent.models import MemberRole, MemberStatus
from research_group_agent.person_validator import PersonValidator
from research_group_agent.precision_constants import (
    ALUMNI_SECTION_KEYWORDS,
    CURRENT_SECTION_KEYWORDS,
    PERSON_NEGATIVE_KEYWORDS,
    PERSON_NEGATIVE_NAME_PATTERNS,
    PERSON_NEGATIVE_URL_PATTERNS,
)

_EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")

STUDENT_ROLES = frozenset({
    MemberRole.PHD_STUDENT,
    MemberRole.MASTER_STUDENT,
    MemberRole.POSTDOC,
    MemberRole.RESEARCH_STAFF,
    MemberRole.VISITOR,
})

CURRENT_STUDENT_SECTION_HINTS = frozenset(
    kw
    for kw in CURRENT_SECTION_KEYWORDS
    if "student" in kw or kw in {"phd students", "doctoral students", "graduate students"}
)

_ADMIN_ROLE_HINTS = frozenset({
    "administrator",
    "administrative",
    "coordinator",
    "secretary",
    "manager",
    "receptionist",
    "webmaster",
})


@dataclass
class CandidateSignals:
    homepage: str | None = None
    profile_url: str | None = None
    email: str | None = None
    github: str | None = None
    scholar: str | None = None
    linkedin: str | None = None
    orcid: str | None = None
    affiliation: str | None = None


def extract_signals(entry: Any) -> CandidateSignals:
    """Extract identity signals from a parser entry."""
    raw = entry.raw_text or ""
    email_match = _EMAIL_PATTERN.search(raw)
    email = email_match.group(0) if email_match else None

    profile_url = entry.profile_url
    homepage = None
    github = None
    scholar = None
    linkedin = None
    orcid = None

    all_urls: list[str] = []
    if profile_url:
        all_urls.append(profile_url)
    for link in getattr(entry, "links", []) or []:
        url = getattr(link, "absolute_url", None) or getattr(link, "href", None)
        if url:
            all_urls.append(url)

    for url in all_urls:
        host = urlparse(url).netloc.lower()
        path = urlparse(url).path.lower()
        if "github.com" in host and not github:
            parts = [p for p in path.split("/") if p]
            if len(parts) == 1:
                github = url
        if "scholar.google" in host and not scholar:
            scholar = url
        if "linkedin.com" in host and not linkedin:
            linkedin = url
        if "orcid.org" in host and not orcid:
            orcid = url
        if not homepage and (
            "/~" in path
            or ".github.io" in host
            or "/people/profile/" in path
            or "/users/" in path
            or "/homes/" in path
        ):
            homepage = url

    if not homepage and profile_url and PersonValidator._is_personal_profile_url(profile_url):
        homepage = profile_url

    affiliation = None
    if entry.section_name:
        affiliation = entry.section_name
    elif entry.role_hint:
        affiliation = entry.role_hint

    return CandidateSignals(
        homepage=homepage,
        profile_url=profile_url,
        email=email,
        github=github,
        scholar=scholar,
        linkedin=linkedin,
        orcid=orcid,
        affiliation=affiliation,
    )


def _has_homepage_or_profile(signals: CandidateSignals) -> bool:
    if signals.homepage:
        return True
    if signals.profile_url and PersonValidator._is_personal_profile_url(signals.profile_url):
        return True
    return False


def _section_suggests_alumni(section_name: str | None) -> bool:
    if not section_name:
        return False
    normalized = section_name.lower().strip()
    return any(hint in normalized for hint in ALUMNI_SECTION_KEYWORDS) or any(
        token in normalized for token in ("past ", "former ", "alumni", "graduated")
    )


def _section_suggests_current_student(section_name: str | None) -> bool:
    if not section_name:
        return False
    normalized = section_name.lower().strip()
    return any(hint in normalized for hint in CURRENT_STUDENT_SECTION_HINTS)


def _is_obvious_non_person(entry: Any) -> bool:
    name = (entry.name or "").lower()
    haystack = f"{name} {entry.raw_text or ''} {entry.role_hint or ''}".lower()
    for pattern in PERSON_NEGATIVE_NAME_PATTERNS:
        if pattern in name:
            return True
    for keyword in PERSON_NEGATIVE_KEYWORDS:
        if keyword in haystack:
            return True
    return False


def _is_administrative(role: MemberRole, entry: Any) -> bool:
    haystack = (
        f"{entry.role_hint or ''} {entry.section_name or ''} {entry.raw_text or ''}"
    ).lower()
    if role == MemberRole.RESEARCH_STAFF and any(h in haystack for h in _ADMIN_ROLE_HINTS):
        return True
    return any(h in haystack for h in _ADMIN_ROLE_HINTS)


def _has_strong_affiliation(entry: Any, role: MemberRole, signals: CandidateSignals) -> bool:
    if not entry.in_member_section:
        return False
    if role in STUDENT_ROLES and role != MemberRole.UNKNOWN:
        return True
    if _section_suggests_current_student(entry.section_name):
        return True
    haystack = (
        f"{entry.raw_text or ''} {entry.role_hint or ''} {signals.affiliation or ''}"
    ).lower()
    university_hints = (
        "university",
        "institute of technology",
        "department of",
        "school of",
        "college of",
        "laboratory",
        "research group",
        "lab ",
    )
    return any(hint in haystack for hint in university_hints)


def _has_external_identity(signals: CandidateSignals) -> bool:
    return bool(
        signals.email
        or signals.github
        or signals.scholar
        or signals.linkedin
        or signals.orcid
    )


def classify_validation_state(
    entry: Any,
    role: MemberRole,
    signals: CandidateSignals,
    *,
    is_exported: bool,
    validation_accepted: bool,
) -> tuple[str, float]:
    """
    Classify a parsed candidate into VERIFIED / RESOLVABLE / PARTIAL / INVALID.

    Returns (state_value, confidence).
    """
    if is_exported:
        return "VERIFIED", 1.0

    if _is_obvious_non_person(entry):
        return "INVALID", 0.0

    if not PersonValidator._looks_like_person_name(entry.name):
        return "INVALID", 0.0

    if not entry.in_member_section:
        return "INVALID", 0.0

    if role == MemberRole.PROFESSOR:
        return "INVALID", 0.0

    if _is_administrative(role, entry):
        return "INVALID", 0.0

    if entry.member_status == MemberStatus.ALUMNI or _section_suggests_alumni(entry.section_name):
        return "INVALID", 0.0

    if signals.profile_url:
        url_lower = signals.profile_url.lower()
        for pattern in PERSON_NEGATIVE_URL_PATTERNS:
            if pattern in url_lower:
                return "INVALID", 0.0

    has_homepage = _has_homepage_or_profile(signals)
    if has_homepage and validation_accepted:
        return "RESOLVABLE", 0.85

    if _has_external_identity(signals) or _has_strong_affiliation(entry, role, signals):
        return "RESOLVABLE", 0.75

    if entry.name and (entry.section_name or entry.role_hint or role != MemberRole.UNKNOWN):
        return "PARTIAL", 0.55

    return "INVALID", 0.0
