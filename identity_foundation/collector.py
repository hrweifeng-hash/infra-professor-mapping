"""Collect IdentityCandidates from parser output."""

from __future__ import annotations

from urllib.parse import urlparse

from research_group_agent.models import MemberExtractionResult, MemberRole
from research_group_agent.parser import MemberPageEntry, ParsedMemberPage
from research_group_agent.providers.stub import StubResearchGroupProvider

from identity_foundation.models import IdentityCandidate, ValidationState
from identity_foundation.validation import classify_validation_state, extract_signals


class IdentityCollector:
    """Build identity candidates from parsed page entries."""

    def __init__(self, role_classifier=None):
        self._classify_role = role_classifier or StubResearchGroupProvider._classify_role

    def collect_page(
        self,
        *,
        professor_name: str,
        source_page: str,
        parsed: ParsedMemberPage,
        extraction: MemberExtractionResult,
    ) -> list[IdentityCandidate]:
        """Collect one IdentityCandidate per parser entry (nothing discarded)."""
        professor_lower = professor_name.lower()
        source_domain = urlparse(source_page).netloc

        accepted_names = {
            m.name.lower() for m in extraction.members + extraction.former_members
        }
        rejection_by_name: dict[str, str] = {}
        for rejected in extraction.rejected_candidates:
            name = rejected.get("name", "")
            if name:
                rejection_by_name[name.lower()] = rejected.get("reason", "unknown")

        candidates: list[IdentityCandidate] = []
        for entry in parsed.entries:
            if entry.name.lower() == professor_lower:
                continue

            role = self._classify_role(
                entry.section_role, entry.role_hint, entry.raw_text
            )
            signals = extract_signals(entry)
            was_accepted = entry.name.lower() in accepted_names
            rejection_reason = rejection_by_name.get(entry.name.lower())

            state_str, confidence = classify_validation_state(
                entry,
                role,
                signals,
                is_exported=False,
                validation_accepted=was_accepted,
            )

            candidates.append(
                IdentityCandidate(
                    name=entry.name,
                    source_professor=professor_name,
                    source_page=source_page,
                    source_domain=source_domain,
                    role=role.value,
                    section=entry.section_name,
                    status=entry.member_status.value,
                    email=signals.email,
                    homepage=signals.homepage,
                    github=signals.github,
                    scholar=signals.scholar,
                    linkedin=signals.linkedin,
                    orcid=signals.orcid,
                    affiliation=signals.affiliation,
                    confidence=confidence,
                    validation_state=ValidationState(state_str),
                    rejection_reason=rejection_reason,
                )
            )

        return candidates

    @staticmethod
    def entry_to_candidate(
        entry: MemberPageEntry,
        *,
        professor_name: str,
        source_page: str,
        role: MemberRole | None = None,
        validation_accepted: bool = False,
        is_exported: bool = False,
        rejection_reason: str | None = None,
    ) -> IdentityCandidate:
        """Build a single candidate — useful for tests."""
        classify = StubResearchGroupProvider._classify_role
        resolved_role = role or classify(
            entry.section_role, entry.role_hint, entry.raw_text
        )
        signals = extract_signals(entry)
        state_str, confidence = classify_validation_state(
            entry,
            resolved_role,
            signals,
            is_exported=is_exported,
            validation_accepted=validation_accepted,
        )
        return IdentityCandidate(
            name=entry.name,
            source_professor=professor_name,
            source_page=source_page,
            source_domain=urlparse(source_page).netloc,
            role=resolved_role.value,
            section=entry.section_name,
            status=entry.member_status.value,
            email=signals.email,
            homepage=signals.homepage,
            github=signals.github,
            scholar=signals.scholar,
            linkedin=signals.linkedin,
            orcid=signals.orcid,
            affiliation=signals.affiliation,
            confidence=confidence,
            validation_state=ValidationState(state_str),
            rejection_reason=rejection_reason,
        )
