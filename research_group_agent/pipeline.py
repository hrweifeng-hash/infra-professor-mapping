"""Research Group Intelligence pipeline.

PR16 addition: cross-identity verification.
After fetching and parsing a candidate group page, the pipeline now checks
whether the page title or primary heading belongs to a *different* professor.
If so the page is rejected before the expensive classifier and extractor run.
"""

from __future__ import annotations

import re

from homepage_agent.models import FetchStatus, HomepageGraph

from research_group_agent.enrichment import TalentEnricher
from research_group_agent.fetcher import ResearchGroupFetcher
from research_group_agent.graph_builder import ResearchGroupGraphBuilder
from research_group_agent.group_discovery import GroupPageDiscoverer
from research_group_agent.identity_resolver import IdentityResolver
from research_group_agent.member_extractor import MemberExtractor
from research_group_agent.navigator import ResearchGroupNavigator
from research_group_agent.models import (
    DEFAULT_TOP_N,
    ExtractionRunMetrics,
    ResearchGroupGraph,
    TalentProfile,
)
from research_group_agent.page_classifier import PageClassifier
from research_group_agent.parser import MemberPageParser, ParsedMemberPage
from research_group_agent.providers.base import ResearchGroupProvider
from research_group_agent.providers.navigator_base import ResearchGroupNavigatorProvider
from research_group_agent.providers.navigator_stub import StubResearchGroupNavigatorProvider
from models.professor_profile import ProfessorProfile

# ─────────────────────────────────────────────────────────────────────────────
# Cross-identity verification helpers (Part 5)
# ─────────────────────────────────────────────────────────────────────────────

# Words that are typical in lab / group names — their presence disqualifies a
# title from being treated as a personal name (e.g. "Berkeley NetSys Lab").
_LAB_TITLE_WORDS: frozenset[str] = frozenset({
    "lab", "laboratory", "systems", "system", "network", "networking",
    "research", "group", "institute", "center", "university", "home",
    "computing", "computer", "science", "engineering", "technology",
    "department", "distributed", "homepage", "page", "website", "portal",
})
_LAB_WORD_RE = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in sorted(_LAB_TITLE_WORDS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


def _title_is_personal_name(title: str) -> bool:
    """
    Return True when the page title looks like a person's full name rather
    than a lab/group name.

    Conditions:
      - 2–4 words, all capitalized, only letters/hyphens
      - No lab-type words
      - No punctuation other than hyphens
      - Title length ≤ 60 characters
    """
    if not title or len(title) > 60:
        return False
    if any(c in title for c in ("@", "|", "–", "—", "#", "/", ".", ":", "!", "?")):
        return False
    if _LAB_WORD_RE.search(title):
        return False
    parts = title.strip().split()
    if not (2 <= len(parts) <= 4):
        return False
    return all(p and p[0].isupper() and p.replace("-", "").isalpha() for p in parts)


def _wrong_page_professor(
    parsed: ParsedMemberPage,
    professor_name: str,
) -> str | None:
    """
    Return a non-empty string (rejection reason) if the page clearly belongs
    to a *different* professor.  Return None to continue processing.

    Checks:
      1. Page title is a personal name different from professor_name.
      2. Primary h1 heading is a personal name different from professor_name.
    """
    # Normalise the professor's name tokens for matching
    name_tokens = [
        t.lower()
        for t in professor_name.split()
        if len(t) > 2 and t.lower() not in ("0001", "0002", "0003", "0004")
    ]
    if not name_tokens:
        return None

    candidates = [parsed.page_title]

    def _check(title: str) -> str | None:
        title = title.strip()
        if not title:
            return None
        if not _title_is_personal_name(title):
            return None
        title_lower = title.lower()
        # If NONE of the professor's name tokens appear in the title it's a wrong page
        if not any(tok in title_lower for tok in name_tokens):
            return (
                f"Page title '{title}' does not match target professor '{professor_name}'; "
                "likely a different person's homepage"
            )
        return None

    for candidate in candidates:
        reason = _check(candidate)
        if reason:
            return reason

    return None


class ResearchGroupPipeline:
    """
    Transform HomepageGraph into ResearchGroupGraph with TalentProfiles.

    Uses canonical homepage from HomepageGraph for group discovery.
    Fetches at most one additional page (the selected group page).
    """

    def __init__(
        self,
        provider: ResearchGroupProvider,
        top_n: int = DEFAULT_TOP_N,
        fetcher: ResearchGroupFetcher | None = None,
        parser: MemberPageParser | None = None,
        graph_builder: ResearchGroupGraphBuilder | None = None,
        page_classifier: PageClassifier | None = None,
        navigator_provider: ResearchGroupNavigatorProvider | None = None,
        navigator: ResearchGroupNavigator | None = None,
    ):
        self.provider = provider
        self.top_n = top_n
        self.fetcher = fetcher or ResearchGroupFetcher()
        self.parser = parser or MemberPageParser()
        group_navigator = navigator or ResearchGroupNavigator(
            provider=navigator_provider or StubResearchGroupNavigatorProvider()
        )
        self.group_navigator = group_navigator
        self.group_discoverer = GroupPageDiscoverer(navigator=group_navigator)
        self.page_classifier = page_classifier or PageClassifier()
        self.member_extractor = MemberExtractor(provider=provider)
        self.identity_resolver = IdentityResolver(provider=provider)
        self.enricher = TalentEnricher()
        self.graph_builder = graph_builder or ResearchGroupGraphBuilder()
        self.last_metrics = ExtractionRunMetrics()

    def _homepage_context(self, homepage_graph: HomepageGraph) -> dict:
        original = homepage_graph.original_homepage or homepage_graph.homepage_url
        canonical = homepage_graph.canonical_homepage or homepage_graph.effective_homepage
        return {
            "original_homepage": original,
            "canonical_homepage": canonical,
            "homepage_resolution_method": homepage_graph.homepage_resolution_method,
            "homepage_resolution_confidence": homepage_graph.homepage_resolution_confidence,
        }

    def analyze(
        self,
        professor: ProfessorProfile,
        homepage_graph: HomepageGraph,
    ) -> ResearchGroupGraph:
        name = professor.author_profile.author.name
        ctx = self._homepage_context(homepage_graph)
        canonical = ctx["canonical_homepage"]

        group_page = self.group_discoverer.select(homepage_graph)
        if group_page is None:
            self.last_metrics.record_rejected_page(
                name, canonical, "no suitable group page in HomepageGraph"
            )
            return self.graph_builder.build_skipped(
                professor_name=name,
                professor_homepage=canonical,
                provider=self.provider.provider_name,
                reason="No suitable group page found in HomepageGraph",
                **ctx,
            )

        document = self.fetcher.fetch(group_page.url)
        if document.fetch_status != FetchStatus.SUCCESS:
            self.last_metrics.record_rejected_page(
                name,
                group_page.url,
                f"fetch failed: {document.fetch_status.value}",
            )
            return self.graph_builder.build_failed(
                professor_name=name,
                professor_homepage=canonical,
                group_page=group_page,
                provider=self.provider.provider_name,
                fetch_status=document.fetch_status.value,
                errors=[document.error_message or document.fetch_status.value],
                **ctx,
            )

        base_url = document.final_url or document.url
        parsed = self.parser.parse(document.html, base_url=base_url)

        wrong_reason = _wrong_page_professor(parsed, name)
        if wrong_reason:
            self.last_metrics.record_rejected_page(name, group_page.url, wrong_reason)
            return self.graph_builder.build_failed(
                professor_name=name,
                professor_homepage=canonical,
                group_page=group_page,
                provider=self.provider.provider_name,
                fetch_status="page_rejected",
                errors=[f"Wrong page: {wrong_reason}"],
                **ctx,
            )

        classification = self.page_classifier.classify(
            parsed=parsed,
            page_url=base_url,
            page_title=document.title,
        )
        if not classification.is_acceptable:
            self.last_metrics.record_rejected_page(
                name,
                group_page.url,
                classification.reason,
            )
            return self.graph_builder.build_failed(
                professor_name=name,
                professor_homepage=canonical,
                group_page=group_page,
                provider=self.provider.provider_name,
                fetch_status="page_rejected",
                errors=[f"Page rejected: {classification.reason}"],
                **ctx,
            )

        extraction = self.member_extractor.extract(
            professor_name=name,
            group_page=group_page,
            parsed=parsed,
        )

        for rejected in extraction.rejected_candidates:
            self.last_metrics.record_rejected_candidate(
                name,
                rejected.get("name", "unknown"),
                rejected.get("reason", "unknown"),
            )

        current_profiles, former_profiles = self._build_profiles(
            extraction.members,
            extraction.former_members,
            parsed,
            name,
        )

        return self.graph_builder.build(
            professor_name=name,
            professor_homepage=canonical,
            group_page=group_page,
            members=current_profiles,
            former_members=former_profiles,
            provider=self.provider.provider_name,
            fetch_status="success",
            errors=list(extraction.errors),
            **ctx,
        )

    def _build_profiles(
        self,
        current_members,
        former_members,
        parsed,
        professor_name: str,
    ) -> tuple[list[TalentProfile], list[TalentProfile]]:
        current_profiles: list[TalentProfile] = []
        former_profiles: list[TalentProfile] = []

        for member in current_members:
            identity = self.identity_resolver.resolve(
                member=member,
                page_links=parsed.all_links,
                professor_name=professor_name,
            )
            current_profiles.append(
                self.enricher.enrich_member(
                    member=member,
                    identity_result=identity,
                    professor_name=professor_name,
                )
            )

        for member in former_members:
            identity = self.identity_resolver.resolve(
                member=member,
                page_links=parsed.all_links,
                professor_name=professor_name,
            )
            former_profiles.append(
                self.enricher.enrich_member(
                    member=member,
                    identity_result=identity,
                    professor_name=professor_name,
                )
            )

        return current_profiles, former_profiles

    def analyze_many(
        self,
        professors: list[ProfessorProfile],
    ) -> list[ResearchGroupGraph]:
        self.last_metrics = ExtractionRunMetrics()
        graphs: list[ResearchGroupGraph] = []
        targets = professors[: self.top_n]

        for professor in targets:
            homepage_graph = professor.homepage_graph
            if homepage_graph is None:
                graph = self.graph_builder.build_skipped(
                    professor_name=professor.author_profile.author.name,
                    professor_homepage=professor.homepage or "",
                    provider=self.provider.provider_name,
                    reason="No HomepageGraph available",
                )
            else:
                if homepage_graph.homepage_resolution_method:
                    upgraded = (
                        homepage_graph.original_homepage
                        and homepage_graph.canonical_homepage
                        and homepage_graph.original_homepage.rstrip("/")
                        != homepage_graph.canonical_homepage.rstrip("/")
                    )
                    self.last_metrics.record_homepage_resolution(upgraded)
                graph = self.analyze(professor, homepage_graph)

            professor.research_group_graph = graph
            graphs.append(graph)
            self.last_metrics.record_member_count(graph.member_count)

        return graphs
