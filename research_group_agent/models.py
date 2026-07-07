"""Data models for the Research Group Intelligence Agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


SCHEMA_VERSION = "1.6"
PIPELINE_VERSION = "PR21"
DEFAULT_TOP_N = 10


class MemberStatus(str, Enum):
    CURRENT = "CURRENT"
    ALUMNI = "ALUMNI"
    UNKNOWN = "UNKNOWN"


class MemberRole(str, Enum):
    PROFESSOR = "Professor"
    POSTDOC = "Postdoc"
    PHD_STUDENT = "PhD Student"
    MASTER_STUDENT = "Master Student"
    RESEARCH_STAFF = "Research Staff"
    VISITOR = "Visitor"
    ALUMNI = "Alumni"
    UNKNOWN = "Unknown"


class GroupPageSource(str, Enum):
    PEOPLE_PAGE = "people_page"
    LAB_PAGE = "lab_page"
    RESEARCH_GROUP_PAGE = "research_group_page"


# Priority order for selecting a research group page from HomepageGraph.
GROUP_PAGE_PRIORITY: tuple[GroupPageSource, ...] = (
    GroupPageSource.PEOPLE_PAGE,
    GroupPageSource.LAB_PAGE,
    GroupPageSource.RESEARCH_GROUP_PAGE,
)


@dataclass
class IdentityLink:
    url: str
    confidence: float
    method: str
    discovery_source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "url": self.url,
            "confidence": round(self.confidence, 3),
            "method": self.method,
        }
        if self.discovery_source:
            payload["discovery_source"] = self.discovery_source
        return payload


@dataclass
class DigitalFootprint:
    homepage: IdentityLink | None = None
    github: IdentityLink | None = None
    linkedin: IdentityLink | None = None
    google_scholar: IdentityLink | None = None
    dblp: IdentityLink | None = None
    openreview: IdentityLink | None = None
    semantic_scholar: IdentityLink | None = None
    orcid: IdentityLink | None = None
    blog: IdentityLink | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            key: (getattr(self, key).to_dict() if getattr(self, key) else None)
            for key in (
                "homepage",
                "github",
                "linkedin",
                "google_scholar",
                "dblp",
                "openreview",
                "semantic_scholar",
                "orcid",
                "blog",
            )
        }

    def identity_count(self) -> int:
        return sum(
            1
            for key in (
                "homepage",
                "github",
                "linkedin",
                "google_scholar",
                "dblp",
                "openreview",
                "semantic_scholar",
                "orcid",
                "blog",
            )
            if getattr(self, key) is not None
        )


@dataclass
class LanguageSignal:
    """
    Probabilistic recruiting signal — not nationality, ethnicity, or citizenship.
    """

    signal_type: str
    probability: float
    method: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.signal_type,
            "probability": round(self.probability, 3),
            "method": self.method,
        }


@dataclass
class ExtractedMember:
    """Raw member extracted from a research group page."""

    name: str
    role: MemberRole = MemberRole.UNKNOWN
    status: MemberStatus = MemberStatus.CURRENT
    profile_url: str | None = None
    context: str | None = None
    extraction_confidence: float = 0.0
    extraction_method: str = "heuristic"


@dataclass
class MemberExtractionResult:
    members: list[ExtractedMember] = field(default_factory=list)
    former_members: list[ExtractedMember] = field(default_factory=list)
    provider: str = "heuristic"
    page_url: str = ""
    errors: list[str] = field(default_factory=list)
    rejected_candidates: list[dict] = field(default_factory=list)


@dataclass
class ExtractionRunMetrics:
    """Internal precision metrics — not part of ResearchGroupGraph schema."""

    rejected_pages: list[dict] = field(default_factory=list)
    rejected_candidates: list[dict] = field(default_factory=list)
    member_counts: list[int] = field(default_factory=list)
    homepage_upgrades: int = 0
    homepage_resolution_attempts: int = 0
    # PR19: per-professor candidate discovery counts
    candidate_page_counts: list[int] = field(default_factory=list)
    # PR20: per-professor second-hop discovery counts
    second_hop_discovered_counts: list[int] = field(default_factory=list)
    second_hop_successful_counts: list[int] = field(default_factory=list)

    def record_homepage_resolution(self, upgraded: bool) -> None:
        self.homepage_resolution_attempts += 1
        if upgraded:
            self.homepage_upgrades += 1

    def record_rejected_page(self, professor_name: str, url: str, reason: str) -> None:
        self.rejected_pages.append(
            {"professor_name": professor_name, "url": url, "reason": reason}
        )

    def record_rejected_candidate(
        self,
        professor_name: str,
        name: str,
        reason: str,
    ) -> None:
        self.rejected_candidates.append(
            {"professor_name": professor_name, "name": name, "reason": reason}
        )

    def record_member_count(self, count: int) -> None:
        self.member_counts.append(count)

    def record_candidate_count(self, count: int) -> None:
        """Record the number of candidate pages discovered for one professor."""
        self.candidate_page_counts.append(count)

    def record_second_hop(self, discovered: int, successful: int) -> None:
        """Record second-hop discovery stats for one professor."""
        self.second_hop_discovered_counts.append(discovered)
        self.second_hop_successful_counts.append(successful)

    @property
    def rejection_reason_counts(self) -> dict[str, int]:
        from collections import Counter

        reasons = Counter()
        for item in self.rejected_candidates:
            key = item["reason"].split(":")[0]
            reasons[key] += 1
        for item in self.rejected_pages:
            reasons[item["reason"].split(":")[0]] += 1
        return dict(reasons.most_common())


@dataclass
class IdentityResolutionResult:
    footprint: DigitalFootprint = field(default_factory=DigitalFootprint)
    provider: str = "heuristic"
    identities_found: int = 0


@dataclass
class TalentProfile:
    name: str
    role: MemberRole
    status: MemberStatus = MemberStatus.CURRENT
    advisor: str | None = None
    profile_url: str | None = None
    digital_footprint: DigitalFootprint = field(default_factory=DigitalFootprint)
    research_interests: list[str] = field(default_factory=list)
    language_signal: LanguageSignal | None = None
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role.value,
            "status": self.status.value,
            "advisor": self.advisor,
            "profile_url": self.profile_url,
            "digital_footprint": self.digital_footprint.to_dict(),
            "research_interests": self.research_interests,
            "language_signal": (
                self.language_signal.to_dict() if self.language_signal else None
            ),
            "confidence": round(self.confidence, 3),
        }


@dataclass
class GroupPageCandidate:
    """A navigation candidate drawn from HomepageGraph for provider scoring."""

    url: str
    node_type: str
    anchor_text: str | None = None
    title: str | None = None
    graph_confidence: float = 0.0


@dataclass
class NavigationScore:
    """Detailed score breakdown for a navigation decision."""

    # Per-category affinity scores (each 0–1)
    lab_score: float = 0.0
    member_score: float = 0.0
    research_group_score: float = 0.0
    homepage_score: float = 0.0

    # Penalty applied when the candidate looks like a directory
    directory_penalty: float = 0.0

    # Final score submitted by the provider (authoritative when > 0)
    provider_score: float = 0.0

    @property
    def final_score(self) -> float:
        """Public single score used for thresholding and sorting."""
        if self.provider_score > 0.0:
            return round(min(1.0, max(0.0, self.provider_score)), 3)
        category_max = max(
            self.lab_score,
            self.member_score,
            self.research_group_score,
            self.homepage_score,
        )
        penalized = category_max * max(0.0, 1.0 - self.directory_penalty)
        return round(min(1.0, max(0.0, penalized)), 3)

    def to_dict(self) -> dict[str, float]:
        return {
            "lab_score": self.lab_score,
            "member_score": self.member_score,
            "research_group_score": self.research_group_score,
            "homepage_score": self.homepage_score,
            "directory_penalty": self.directory_penalty,
            "provider_score": self.provider_score,
            "final_score": self.final_score,
        }


@dataclass
class ResearchGroupNavigationDecision:
    """Structured navigation classification produced by ResearchGroupNavigator."""

    candidate_url: str
    candidate_type: str
    reason: str
    navigation_score: NavigationScore = field(default_factory=NavigationScore)
    anchor_text: str | None = None
    title: str | None = None
    navigation_path: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    rejected_candidates: list[dict] = field(default_factory=list)

    @property
    def confidence(self) -> float:
        """Public single-value confidence — delegates to NavigationScore.final_score."""
        return self.navigation_score.final_score

    @property
    def final_confidence(self) -> float:
        return self.navigation_score.final_score

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_url": self.candidate_url,
            "candidate_type": self.candidate_type,
            "reason": self.reason,
            "navigation_score": self.navigation_score.to_dict(),
            "anchor_text": self.anchor_text,
            "title": self.title,
            "navigation_path": self.navigation_path,
            "evidence": self.evidence,
            "rejected_candidates": self.rejected_candidates,
        }


@dataclass
class GroupPageSelection:
    url: str
    source_node_type: str
    confidence: float
    reason: str
    navigation_path: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    navigation_score: NavigationScore | None = None
    navigation_provider: str = "heuristic"


@dataclass
class MultiPageSelection:
    """Selection of multiple candidate pages for multi-page member discovery."""

    selected_pages: list[GroupPageSelection] = field(default_factory=list)
    selection_strategy: str = "top_candidates"
    selection_reason: str = ""

    @property
    def page_count(self) -> int:
        return len(self.selected_pages)

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_pages": [
                {
                    "url": p.url,
                    "source_node_type": p.source_node_type,
                    "confidence": round(p.confidence, 3),
                    "reason": p.reason,
                    "navigation_path": p.navigation_path,
                    "evidence": p.evidence,
                }
                for p in self.selected_pages
            ],
            "selection_strategy": self.selection_strategy,
            "selection_reason": self.selection_reason,
            "page_count": self.page_count,
        }


@dataclass
class ResearchGroupGraph:
    professor_name: str
    professor_homepage: str
    original_homepage: str | None = None
    canonical_homepage: str | None = None
    homepage_resolution_method: str | None = None
    homepage_resolution_confidence: float = 0.0
    group_page: GroupPageSelection | None = None
    members: list[TalentProfile] = field(default_factory=list)
    former_members: list[TalentProfile] = field(default_factory=list)
    provider: str = "heuristic"
    navigation_provider: str = "heuristic"
    navigation_path: list[str] = field(default_factory=list)
    fetch_status: str = "not_attempted"
    errors: list[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    pipeline_version: str = PIPELINE_VERSION
    # PR17: multi-page discovery fields
    parsed_pages: list[str] = field(default_factory=list)
    successful_pages: list[str] = field(default_factory=list)
    failed_pages: list[str] = field(default_factory=list)
    member_sources: dict[str, list[str]] = field(default_factory=dict)
    # PR19: total candidate pages enumerated before ranking
    candidate_pages_discovered: int = 0
    # PR20: second-hop discovery results
    second_hop_pages_discovered: int = 0
    second_hop_pages_successful: int = 0

    @property
    def member_count(self) -> int:
        return len(self.members)

    @property
    def current_member_count(self) -> int:
        return len(self.members)

    @property
    def former_member_count(self) -> int:
        return len(self.former_members)

    def to_dict(self) -> dict[str, Any]:
        group_page_dict = None
        if self.group_page:
            group_page_dict = {
                "url": self.group_page.url,
                "source_node_type": self.group_page.source_node_type,
                "confidence": round(self.group_page.confidence, 3),
                "reason": self.group_page.reason,
                "navigation_path": self.group_page.navigation_path,
                "evidence": self.group_page.evidence,
            }
            if self.group_page.navigation_score:
                group_page_dict["navigation_score"] = self.group_page.navigation_score.to_dict()

        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "pipeline_version": self.pipeline_version,
            "professor_name": self.professor_name,
            "professor_homepage": self.professor_homepage,
            "original_homepage": self.original_homepage or self.professor_homepage,
            "canonical_homepage": self.canonical_homepage or self.professor_homepage,
            "homepage_resolution_method": self.homepage_resolution_method,
            "homepage_resolution_confidence": round(self.homepage_resolution_confidence, 3),
            "navigation_provider": self.navigation_provider,
            "navigation_path": self.navigation_path,
            "group_page": group_page_dict,
            "fetch_status": self.fetch_status,
            "provider": self.provider,
            "member_count": self.member_count,
            "current_member_count": self.current_member_count,
            "former_member_count": self.former_member_count,
            "members": [member.to_dict() for member in self.members],
            "former_members": [member.to_dict() for member in self.former_members],
            "errors": self.errors,
            "parsed_pages": self.parsed_pages,
            "successful_pages": self.successful_pages,
            "failed_pages": self.failed_pages,
            "member_sources": self.member_sources,
            "candidate_pages_discovered": self.candidate_pages_discovered,
            "second_hop_pages_discovered": self.second_hop_pages_discovered,
            "second_hop_pages_successful": self.second_hop_pages_successful,
        }
