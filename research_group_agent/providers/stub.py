"""Heuristic research group provider — precision-first, no external API calls."""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from homepage_agent.models import Hyperlink

from research_group_agent.adaptive_member_limiter import (
    AdaptiveMemberLimiter,
    LEGACY_MEMBER_CAP,
    format_adaptive_member_limit_log,
)
from research_group_agent.department_scope_detector import (
    DepartmentScopeDetector,
    DepartmentScopeResult,
)
from research_group_agent.models import (
    DigitalFootprint,
    ExtractedMember,
    IdentityLink,
    IdentityResolutionResult,
    MemberExtractionResult,
    MemberRole,
    MemberStatus,
)
from research_group_agent.parser import ParsedMemberPage
from research_group_agent.person_validator import PersonValidator
from research_group_agent.providers.base import ResearchGroupProvider

logger = logging.getLogger(__name__)

_ROLE_RULES: list[tuple[MemberRole, tuple[str, ...]]] = [
    (MemberRole.PROFESSOR, ("professor", "faculty", "pi", "principal investigator")),
    (MemberRole.POSTDOC, ("postdoc", "post-doc", "postdoctoral")),
    (MemberRole.PHD_STUDENT, ("phd", "ph.d", "doctoral student", "doctorate")),
    (MemberRole.MASTER_STUDENT, ("master", "m.s.", "ms student")),
    (MemberRole.RESEARCH_STAFF, ("research staff", "research scientist", "staff scientist")),
    (MemberRole.VISITOR, ("visitor", "visiting")),
    (MemberRole.ALUMNI, ("alumni", "former", "graduated")),
]

_IDENTITY_HOSTS: list[tuple[str, tuple[str, ...], str, float]] = [
    ("github", ("github.com",), "url_host_match", 0.95),
    ("linkedin", ("linkedin.com",), "url_host_match", 0.95),
    ("google_scholar", ("scholar.google",), "url_host_match", 0.95),
    ("dblp", ("dblp.org", "dblp.uni-trier.de"), "url_host_match", 0.95),
    ("openreview", ("openreview.net",), "url_host_match", 0.95),
    ("semantic_scholar", ("semanticscholar.org",), "url_host_match", 0.95),
    ("orcid", ("orcid.org",), "url_host_match", 0.95),
]

_BLOG_HINTS = ("blog", "medium.com", "substack.com", "wordpress", "tumblr")


class StubResearchGroupProvider(ResearchGroupProvider):
    """
    Heuristic member extraction and identity resolution.

    Precision-first: rejects ambiguous candidates rather than including noise.
    """

    MIN_EXTRACTION_CONFIDENCE = 0.55
    MAX_MEMBERS_PER_GROUP = LEGACY_MEMBER_CAP  # backward-compatible alias (PR29)

    def __init__(
        self,
        validator: PersonValidator | None = None,
        department_detector: DepartmentScopeDetector | None = None,
        member_limiter: AdaptiveMemberLimiter | None = None,
    ):
        self.validator = validator or PersonValidator()
        self.department_detector = department_detector or DepartmentScopeDetector()
        self.member_limiter = member_limiter or AdaptiveMemberLimiter()

    @property
    def provider_name(self) -> str:
        return "heuristic"

    def extract_members(
        self,
        prompt: str,
        parsed: ParsedMemberPage,
        professor_name: str,
        *,
        page_url: str | None = None,
        department_scope: DepartmentScopeResult | None = None,
    ) -> MemberExtractionResult:
        del prompt

        current_members: list[ExtractedMember] = []
        former_members: list[ExtractedMember] = []
        rejected: list[dict] = []
        professor_lower = professor_name.lower()

        for entry in parsed.entries:
            if entry.name.lower() == professor_lower:
                continue

            role = self._classify_role(entry.section_role, entry.role_hint, entry.raw_text)
            status = entry.member_status
            validation = self.validator.validate(
                name=entry.name,
                profile_url=entry.profile_url,
                section_name=entry.section_name,
                section_role=entry.section_role,
                role_hint=entry.role_hint,
                raw_text=entry.raw_text,
                in_member_section=entry.in_member_section,
            )

            if not validation.is_valid:
                rejected.append({"name": entry.name, "reason": validation.reason})
                continue

            confidence = self._extraction_confidence(entry, role, validation.confidence)
            if confidence < self.MIN_EXTRACTION_CONFIDENCE:
                rejected.append(
                    {
                        "name": entry.name,
                        "reason": f"low extraction confidence ({confidence:.2f})",
                    }
                )
                continue

            extracted = ExtractedMember(
                name=entry.name,
                role=role,
                status=status,
                profile_url=entry.profile_url,
                context=entry.raw_text[:200] if entry.raw_text else None,
                extraction_confidence=confidence,
                extraction_method=self.provider_name,
            )
            if status == MemberStatus.ALUMNI:
                former_members.append(extracted)
            else:
                current_members.append(extracted)

        current_members.sort(key=lambda member: member.extraction_confidence, reverse=True)

        scope = department_scope
        if scope is None:
            scope = self.department_detector.detect(
                parsed=parsed,
                page_url=page_url or "",
                page_title=parsed.page_title,
            )

        limit_result = self.member_limiter.compute(
            parsed,
            scope,
            validated_member_count=len(current_members),
        )
        member_limit = limit_result.member_limit
        parsed_count = len(parsed.entries)

        if not limit_result.unlimited and len(current_members) > member_limit:
            for dropped in current_members[member_limit:]:
                rejected.append(
                    {
                        "name": dropped.name,
                        "reason": (
                            f"exceeded adaptive member cap ({member_limit}; "
                            f"{limit_result.reason})"
                        ),
                    }
                )
            current_members = current_members[:member_limit]

            log_block = format_adaptive_member_limit_log(
                professor_name=professor_name,
                parsed_members=parsed_count,
                exported_members=len(current_members),
                limit_result=limit_result,
            )
            logger.info("\n%s", log_block)
            print(log_block)

        return MemberExtractionResult(
            members=current_members,
            former_members=former_members,
            provider=self.provider_name,
            rejected_candidates=rejected,
            errors=[] if current_members else ["No current members passed precision validation"],
            adaptive_member_limit=member_limit if not limit_result.unlimited else None,
            adaptive_limit_confidence=limit_result.confidence,
            adaptive_limit_reason=limit_result.reason,
            adaptive_limit_rules=list(limit_result.rules_applied),
            adaptive_limit_unlimited=limit_result.unlimited,
        )

    def resolve_identities(
        self,
        prompt: str,
        member: ExtractedMember,
        page_links: list[Hyperlink],
        professor_name: str,
    ) -> IdentityResolutionResult:
        del prompt, professor_name

        footprint = DigitalFootprint()
        candidate_links = list(page_links)

        if member.profile_url:
            candidate_links.append(
                Hyperlink(
                    anchor_text=member.name,
                    href=member.profile_url,
                    absolute_url=member.profile_url,
                )
            )

        name_lower = member.name.lower()
        name_links = [
            link
            for link in candidate_links
            if link.anchor_text.strip().lower() == name_lower
        ]
        if not name_links and member.profile_url:
            name_links = [
                link for link in candidate_links
                if link.absolute_url == member.profile_url
            ]

        for link in name_links:
            self._apply_link_to_footprint(footprint, link)

        if member.profile_url and not footprint.homepage:
            if self._is_personal_homepage(member.profile_url):
                footprint.homepage = IdentityLink(
                    url=member.profile_url,
                    confidence=0.85,
                    method=self.provider_name,
                    discovery_source="profile_url",
                )

        return IdentityResolutionResult(
            footprint=footprint,
            provider=self.provider_name,
            identities_found=footprint.identity_count(),
        )

    def _apply_link_to_footprint(
        self,
        footprint: DigitalFootprint,
        link: Hyperlink,
    ) -> None:
        host = urlparse(link.absolute_url).netloc.lower()

        for field_name, host_patterns, method, confidence in _IDENTITY_HOSTS:
            if any(pattern in host for pattern in host_patterns):
                if getattr(footprint, field_name) is None:
                    setattr(
                        footprint,
                        field_name,
                        IdentityLink(
                            url=link.absolute_url,
                            confidence=confidence,
                            method=method,
                            discovery_source="page_link",
                        ),
                    )
                return

        if any(hint in host for hint in _BLOG_HINTS):
            if footprint.blog is None:
                footprint.blog = IdentityLink(
                    url=link.absolute_url,
                    confidence=0.75,
                    method="url_host_match",
                    discovery_source="page_link",
                )
            return

        if self._is_personal_homepage(link.absolute_url) and footprint.homepage is None:
            footprint.homepage = IdentityLink(
                url=link.absolute_url,
                confidence=0.7,
                method="url_heuristic",
                discovery_source="page_link",
            )

    @staticmethod
    def _classify_role(
        section_role: MemberRole,
        role_hint: str | None,
        raw_text: str,
    ) -> MemberRole:
        if section_role != MemberRole.UNKNOWN:
            return section_role

        haystack = f"{role_hint or ''} {raw_text}".lower()
        for role, keywords in _ROLE_RULES:
            if any(keyword in haystack for keyword in keywords):
                return role
        if "student" in haystack:
            return MemberRole.PHD_STUDENT
        return MemberRole.UNKNOWN

    @staticmethod
    def _extraction_confidence(entry, role: MemberRole, validation_score: float) -> float:
        score = validation_score * 0.6
        if entry.profile_url:
            score += 0.2
        if role != MemberRole.UNKNOWN:
            score += 0.15
        if entry.role_hint:
            score += 0.05
        if re.match(r"^[A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z]+)+$", entry.name):
            score += 0.05
        return round(min(1.0, score), 3)

    @staticmethod
    def _is_personal_homepage(url: str) -> bool:
        host = urlparse(url).netloc.lower()
        path = urlparse(url).path.lower()
        personal_hints = ("~", "/people/profile/", "/users/", "/homes/", ".github.io")
        if any(hint in path or hint in host for hint in personal_hints):
            return True
        if "github.com" in host:
            parts = [part for part in path.split("/") if part]
            return len(parts) == 1
        return False
