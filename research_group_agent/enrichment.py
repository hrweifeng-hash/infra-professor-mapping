"""Talent enrichment — language signals and TalentProfile assembly."""

from __future__ import annotations

import json
from pathlib import Path

from research_group_agent.models import (
    ExtractedMember,
    IdentityResolutionResult,
    LanguageSignal,
    MemberRole,
    MemberStatus,
    TalentProfile,
)


class TalentEnricher:
    """Enrich extracted members into recruiter-facing TalentProfiles."""

    SURNAME_SIGNAL_TYPE = "Likely Chinese Surname"

    def __init__(self, surname_dictionary_path: str | Path | None = None):
        path = Path(surname_dictionary_path or "resources/chinese_surnames.json")
        self._surnames: set[str] = set()
        if path.exists():
            self._surnames = {value.lower() for value in json.loads(path.read_text())}

    def enrich_member(
        self,
        member: ExtractedMember,
        identity_result: IdentityResolutionResult,
        professor_name: str,
    ) -> TalentProfile:
        language_signal = self.detect_language_signal(member.name)
        confidence = self._compute_confidence(member, identity_result)

        return TalentProfile(
            name=member.name,
            role=member.role,
            status=member.status,
            advisor=professor_name,
            profile_url=member.profile_url,
            digital_footprint=identity_result.footprint,
            research_interests=[],
            language_signal=language_signal,
            confidence=confidence,
        )

    def detect_language_signal(self, name: str) -> LanguageSignal | None:
        if not self._surnames:
            return None

        tokens = [token.strip(".,()") for token in name.split() if token.strip(".,()")]
        if not tokens:
            return None

        matched_token: str | None = None
        probability = 0.0

        # Check each name token against surname dictionary (supports "Li Ming" and "John Wang").
        for token in tokens:
            lower = token.lower()
            if lower in self._surnames:
                matched_token = token
                probability = 0.96 if len(tokens) <= 2 else 0.85
                break

        if not matched_token:
            return None

        return LanguageSignal(
            signal_type=self.SURNAME_SIGNAL_TYPE,
            probability=probability,
            method="surname_dictionary",
        )

    @staticmethod
    def _compute_confidence(
        member: ExtractedMember,
        identity_result: IdentityResolutionResult,
    ) -> float:
        base = member.extraction_confidence or 0.5
        identity_boost = min(0.3, identity_result.identities_found * 0.08)
        role_boost = 0.1 if member.role != MemberRole.UNKNOWN else 0.0
        return round(min(1.0, base + identity_boost + role_boost), 3)
