"""PersonValidator — validates extracted items are likely human members.

PR16 addition: PersonValidationScore provides a named, inspectable score
breakdown. The existing PersonValidation interface is preserved for backward
compatibility; PersonValidation.score_breakdown now carries the full detail.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from research_group_agent.models import MemberRole
from research_group_agent.precision_constants import (
    PERSON_NEGATIVE_KEYWORDS,
    PERSON_NEGATIVE_NAME_PATTERNS,
    PERSON_NEGATIVE_URL_PATTERNS,
)

_NAME_PATTERN = re.compile(
    r"^[A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z]+)+$"
)
_EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")


# ─────────────────────────────────────────────────────────────────────────────
# PR16: PersonValidationScore
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class PersonValidationScore:
    """
    Granular score breakdown for a person-validation decision.

    Fields
    ------
    name_score
        How closely the candidate string resembles a real person name.
        0.0 – failed basic name check, up to 0.25 for a canonical name pattern.

    role_score
        Evidence that the candidate has a research role.
        Up to 0.20 for an explicit section role; 0.10 for a text role hint.

    profile_score
        Digital footprint evidence (personal homepage URL or email address).
        Up to 0.25 for a personal URL; 0.15 for an email address.

    context_score
        Context signals: being inside a member section, section-level clues.
        Up to 0.25 for being in a confirmed member section.

    research_group_score
        Group-membership signals beyond simple section membership.
        Up to 0.05 for additional contextual evidence.

    final_score
        Sum of all sub-scores, capped at 1.0. Acceptance requires
        final_score >= PersonValidator.MIN_ACCEPT_CONFIDENCE.
    """

    name_score: float = 0.0
    role_score: float = 0.0
    profile_score: float = 0.0
    context_score: float = 0.0
    research_group_score: float = 0.0

    @property
    def final_score(self) -> float:
        total = (
            self.name_score
            + self.role_score
            + self.profile_score
            + self.context_score
            + self.research_group_score
        )
        return round(min(1.0, max(0.0, total)), 3)

    def to_dict(self) -> dict:
        return {
            "name_score": round(self.name_score, 3),
            "role_score": round(self.role_score, 3),
            "profile_score": round(self.profile_score, 3),
            "context_score": round(self.context_score, 3),
            "research_group_score": round(self.research_group_score, 3),
            "final_score": self.final_score,
        }


# ─────────────────────────────────────────────────────────────────────────────
# PersonValidation (unchanged public interface)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class PersonValidation:
    is_valid: bool
    confidence: float
    reason: str
    score_breakdown: PersonValidationScore = field(
        default_factory=PersonValidationScore
    )


# ─────────────────────────────────────────────────────────────────────────────
# PersonValidator
# ─────────────────────────────────────────────────────────────────────────────


class PersonValidator:
    """
    Validate that an extracted item represents a human research group member.

    Precision-first: false positives are rejected aggressively.
    Acceptance is now driven by PersonValidationScore.final_score rather than
    individual hard-coded rules.
    """

    MIN_ACCEPT_CONFIDENCE = 0.55

    def validate(
        self,
        name: str,
        profile_url: str | None = None,
        section_name: str | None = None,
        section_role: MemberRole | None = None,
        role_hint: str | None = None,
        raw_text: str | None = None,
        in_member_section: bool = False,
    ) -> PersonValidation:
        name = (name or "").strip()
        haystack = f"{name} {raw_text or ''} {role_hint or ''}".lower()

        # ── Hard rejects — non-person entities ──────────────────────────────
        for pattern in PERSON_NEGATIVE_NAME_PATTERNS:
            if pattern in name.lower():
                return PersonValidation(
                    False, 0.0,
                    f"name matches non-person pattern: {pattern}",
                    PersonValidationScore(),
                )

        for keyword in PERSON_NEGATIVE_KEYWORDS:
            if keyword in haystack:
                return PersonValidation(
                    False, 0.0,
                    f"contains non-person keyword: {keyword}",
                    PersonValidationScore(),
                )

        if profile_url:
            url_lower = profile_url.lower()
            for pattern in PERSON_NEGATIVE_URL_PATTERNS:
                if pattern in url_lower:
                    return PersonValidation(
                        False, 0.0,
                        f"profile URL indicates non-person page: {pattern}",
                        PersonValidationScore(),
                    )

        if not self._looks_like_person_name(name):
            return PersonValidation(
                False, 0.0,
                "does not look like a person name",
                PersonValidationScore(),
            )

        if not in_member_section:
            return PersonValidation(
                False, 0.0,
                "not in a member section",
                PersonValidationScore(),
            )

        # ── Build PersonValidationScore ──────────────────────────────────────
        scores = PersonValidationScore()

        # name_score: base + bonus for canonical pattern
        scores.name_score = 0.10
        if _NAME_PATTERN.match(name):
            scores.name_score = 0.25

        # context_score: being in a member section
        if in_member_section:
            scores.context_score = 0.25

        # role_score: section role or text role hint
        has_section_role = bool(section_role and section_role != MemberRole.UNKNOWN)
        if has_section_role:
            scores.role_score = 0.20
        elif role_hint:
            scores.role_score = 0.10

        # profile_score: personal URL or email
        has_personal_url = bool(
            profile_url and self._is_personal_profile_url(profile_url)
        )
        has_any_url = bool(profile_url)
        has_email = bool(_EMAIL_PATTERN.search(raw_text or ""))

        if has_personal_url:
            scores.profile_score = 0.25
        elif has_any_url:
            scores.profile_score = 0.08
        if has_email:
            scores.profile_score = max(scores.profile_score, 0.15)

        # research_group_score: additional contextual signals
        if section_name:
            scores.research_group_score = 0.05

        # ── Hard require: at least one strong identity anchor unless role known ──
        if (
            not has_personal_url
            and not has_email
            and not has_section_role
            and not role_hint
        ):
            return PersonValidation(
                False, 0.0,
                "missing personal profile URL or role evidence",
                PersonValidationScore(),
            )

        final = scores.final_score
        is_valid = final >= self.MIN_ACCEPT_CONFIDENCE

        reason = (
            f"accepted (score={final:.3f})"
            if is_valid
            else f"low confidence ({final:.3f} < {self.MIN_ACCEPT_CONFIDENCE})"
        )

        return PersonValidation(
            is_valid=is_valid,
            confidence=final,
            reason=reason,
            score_breakdown=scores,
        )

    @staticmethod
    def _looks_like_person_name(text: str) -> bool:
        text = text.strip()
        if len(text) < 4 or len(text) > 50:
            return False
        if any(char.isdigit() for char in text):
            return False
        if text.isupper():
            return False

        words = text.split()
        if len(words) < 2 or len(words) > 5:
            return False

        if not all(word[0].isupper() for word in words if word):
            return False

        if _NAME_PATTERN.match(text):
            return True

        # Allow "First Last" with optional middle initial / period suffix
        return all(
            re.match(r"^[A-Z][a-z]+(\.?)?$", word) or word.endswith(".")
            for word in words
        )

    @staticmethod
    def _is_personal_profile_url(url: str) -> bool:
        parsed = urlparse(url)
        path = parsed.path.lower()
        host = parsed.netloc.lower()

        personal_patterns = (
            "/~",
            ".github.io",
            "/people/profile/",
            "/users/",
            "/homes/",
        )
        if any(pattern in path or pattern in host for pattern in personal_patterns):
            return True

        # GitHub user profile (not org/repo)
        if "github.com" in host:
            parts = [part for part in path.split("/") if part]
            return len(parts) == 1

        return False
