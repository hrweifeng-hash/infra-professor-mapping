"""GraphBuilder — constructs ResearchGroupGraph from pipeline stages."""

from __future__ import annotations

from research_group_agent.models import (
    GroupPageSelection,
    PIPELINE_VERSION,
    ResearchGroupGraph,
    SCHEMA_VERSION,
    TalentProfile,
)


class ResearchGroupGraphBuilder:
    """Build a ResearchGroupGraph from enrichment results."""

    def build(
        self,
        professor_name: str,
        professor_homepage: str,
        group_page: GroupPageSelection | None,
        members: list[TalentProfile],
        provider: str,
        fetch_status: str = "success",
        errors: list[str] | None = None,
        original_homepage: str | None = None,
        canonical_homepage: str | None = None,
        homepage_resolution_method: str | None = None,
        homepage_resolution_confidence: float = 0.0,
        former_members: list[TalentProfile] | None = None,
        parsed_pages: list[str] | None = None,
        successful_pages: list[str] | None = None,
        failed_pages: list[str] | None = None,
        member_sources: dict[str, list[str]] | None = None,
        candidate_pages_discovered: int = 0,
        second_hop_pages_discovered: int = 0,
        second_hop_pages_successful: int = 0,
        homepage_accepted_as_group_page: bool = False,
        department_scope_pages: list[dict] | None = None,
        navigation_discovery: dict | None = None,
    ) -> ResearchGroupGraph:
        navigation_path = list(group_page.navigation_path) if group_page else []
        navigation_provider = (
            group_page.navigation_provider if group_page else "heuristic"
        )

        return ResearchGroupGraph(
            professor_name=professor_name,
            professor_homepage=professor_homepage,
            original_homepage=original_homepage or professor_homepage,
            canonical_homepage=canonical_homepage or professor_homepage,
            homepage_resolution_method=homepage_resolution_method,
            homepage_resolution_confidence=homepage_resolution_confidence,
            group_page=group_page,
            members=members,
            former_members=list(former_members or []),
            provider=provider,
            navigation_provider=navigation_provider,
            navigation_path=navigation_path,
            fetch_status=fetch_status,
            errors=list(errors or []),
            schema_version=SCHEMA_VERSION,
            pipeline_version=PIPELINE_VERSION,
            parsed_pages=list(parsed_pages or []),
            successful_pages=list(successful_pages or []),
            failed_pages=list(failed_pages or []),
            member_sources=dict(member_sources or {}),
            candidate_pages_discovered=candidate_pages_discovered,
            second_hop_pages_discovered=second_hop_pages_discovered,
            second_hop_pages_successful=second_hop_pages_successful,
            homepage_accepted_as_group_page=homepage_accepted_as_group_page,
            department_scope_pages=list(department_scope_pages or []),
            navigation_discovery=dict(navigation_discovery or {}),
        )

    def build_skipped(
        self,
        professor_name: str,
        professor_homepage: str,
        provider: str,
        reason: str,
        original_homepage: str | None = None,
        canonical_homepage: str | None = None,
        homepage_resolution_method: str | None = None,
        homepage_resolution_confidence: float = 0.0,
        candidate_pages_discovered: int = 0,
        navigation_discovery: dict | None = None,
    ) -> ResearchGroupGraph:
        return self.build(
            professor_name=professor_name,
            professor_homepage=professor_homepage,
            group_page=None,
            members=[],
            provider=provider,
            fetch_status="skipped",
            errors=[reason],
            original_homepage=original_homepage,
            canonical_homepage=canonical_homepage,
            homepage_resolution_method=homepage_resolution_method,
            homepage_resolution_confidence=homepage_resolution_confidence,
            candidate_pages_discovered=candidate_pages_discovered,
            navigation_discovery=navigation_discovery,
        )

    def build_failed(
        self,
        professor_name: str,
        professor_homepage: str,
        group_page: GroupPageSelection | None,
        provider: str,
        fetch_status: str,
        errors: list[str],
        original_homepage: str | None = None,
        canonical_homepage: str | None = None,
        homepage_resolution_method: str | None = None,
        homepage_resolution_confidence: float = 0.0,
        parsed_pages: list[str] | None = None,
        successful_pages: list[str] | None = None,
        failed_pages: list[str] | None = None,
        candidate_pages_discovered: int = 0,
        second_hop_pages_discovered: int = 0,
        second_hop_pages_successful: int = 0,
        navigation_discovery: dict | None = None,
    ) -> ResearchGroupGraph:
        return self.build(
            professor_name=professor_name,
            professor_homepage=professor_homepage,
            group_page=group_page,
            members=[],
            provider=provider,
            fetch_status=fetch_status,
            errors=errors,
            original_homepage=original_homepage,
            canonical_homepage=canonical_homepage,
            homepage_resolution_method=homepage_resolution_method,
            homepage_resolution_confidence=homepage_resolution_confidence,
            parsed_pages=parsed_pages,
            successful_pages=successful_pages,
            failed_pages=failed_pages,
            candidate_pages_discovered=candidate_pages_discovered,
            second_hop_pages_discovered=second_hop_pages_discovered,
            second_hop_pages_successful=second_hop_pages_successful,
            navigation_discovery=navigation_discovery,
        )
