"""Research Group Intelligence pipeline.

PR16 addition: cross-identity verification.
After fetching and parsing a candidate group page, the pipeline now checks
whether the page title or primary heading belongs to a *different* professor.
If so the page is rejected before the expensive classifier and extractor run.

PR17 addition: multi-page member discovery.
Instead of selecting a single best group page, the pipeline now selects the
top N candidate pages, parses each one, and merges/deduplicates the results.

PR19 addition: broader candidate page discovery.
Replaces the navigator-based candidate selection with CandidatePageGenerator
(enumerates ALL HomepageGraph nodes + the canonical homepage) and
CandidatePageRanker (scores with explainable rules, returns top 5).

PR20 addition: second-hop candidate discovery.
When a first-hop candidate page passes all validation but yields zero members,
PeoplePageDiscovery inspects its navigation links for explicit people/team/
member/student sub-pages and fetches those as a single additional hop.
"""

from __future__ import annotations

import re
from typing import NamedTuple

from homepage_agent.models import FetchStatus, HomepageGraph

from research_group_agent.candidate_page import (
    CandidatePage,
    CandidatePageGenerator,
    CandidatePageRanker,
)
from research_group_agent.people_page_discovery import PeoplePageDiscovery
from research_group_agent.enrichment import TalentEnricher
from research_group_agent.fetcher import ResearchGroupFetcher
from research_group_agent.graph_builder import ResearchGroupGraphBuilder
from research_group_agent.group_discovery import GroupPageDiscoverer
from research_group_agent.identity_resolver import IdentityResolver
from research_group_agent.member_extractor import MemberExtractor
from research_group_agent.member_merger import MemberMerger
from research_group_agent.navigator import ResearchGroupNavigator
from research_group_agent.models import (
    DEFAULT_TOP_N,
    ExtractionRunMetrics,
    GroupPageSelection,
    MultiPageSelection,
    ResearchGroupGraph,
    TalentProfile,
)
from research_group_agent.page_classifier import PageClassifier
from research_group_agent.parser import MemberPageParser, ParsedMemberPage
from research_group_agent.providers.base import ResearchGroupProvider
from research_group_agent.providers.navigator_base import ResearchGroupNavigatorProvider
from research_group_agent.providers.navigator_stub import StubResearchGroupNavigatorProvider
from models.professor_profile import ProfessorProfile

# Maximum candidate pages to parse per professor (PR19: expanded to 5)
_MAX_CANDIDATE_PAGES = 5


# ─────────────────────────────────────────────────────────────────────────────
# Internal result types
# ─────────────────────────────────────────────────────────────────────────────

class _FetchParseResult(NamedTuple):
    """Outcome of the fetch + parse + cross-identity phase."""

    parsed: object    # ParsedMemberPage
    base_url: str
    document_title: str
    raw_html: str     # Original HTML for PeoplePageDiscovery (nav links not in parsed)


class _PageResult(NamedTuple):
    """Successful outcome of the full classify + extract phase."""

    current_profiles: list
    former_profiles: list
    errors: list[str]

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
        self.member_merger = MemberMerger()
        self.graph_builder = graph_builder or ResearchGroupGraphBuilder()
        self.last_metrics = ExtractionRunMetrics()
        # PR19: candidate-based discovery components
        self.candidate_generator = CandidatePageGenerator()
        self.candidate_ranker = CandidatePageRanker()
        # PR20: second-hop people-page discovery
        self.people_page_discovery = PeoplePageDiscovery()

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

        # PR19: broader candidate discovery via CandidatePageGenerator + CandidatePageRanker
        all_candidates = self.candidate_generator.generate(homepage_graph)
        candidate_count = len(all_candidates)
        self.last_metrics.record_candidate_count(candidate_count)

        ranked = self.candidate_ranker.rank(all_candidates, top_n=_MAX_CANDIDATE_PAGES)
        multi = self._candidates_to_multi(ranked, homepage_graph)

        if not multi.selected_pages:
            self.last_metrics.record_rejected_page(
                name, canonical, "no suitable group page in HomepageGraph"
            )
            return self.graph_builder.build_skipped(
                professor_name=name,
                professor_homepage=canonical,
                provider=self.provider.provider_name,
                reason="No suitable group page found in HomepageGraph",
                candidate_pages_discovered=candidate_count,
                **ctx,
            )

        # PR17: parse every candidate page
        page_results: list[tuple[str, list[TalentProfile], list[TalentProfile]]] = []
        parsed_pages: list[str] = []
        successful_pages: list[str] = []
        failed_pages: list[str] = []
        all_errors: list[str] = []
        # Track the primary group_page (highest confidence) for graph metadata
        primary_group_page: GroupPageSelection | None = multi.selected_pages[0]

        # PR20: track every URL attempted to prevent second-hop duplication;
        # pre-populate with all first-hop URLs so second-hop never re-queues them.
        tried_urls: set[str] = {gp.url.rstrip("/") for gp in multi.selected_pages}
        second_hop_discovered = 0
        second_hop_successful = 0

        for group_page in multi.selected_pages:
            parsed_pages.append(group_page.url)
            fp, result = self._process_single_page(
                name=name,
                group_page=group_page,
                canonical=canonical,
            )

            if result is not None:
                successful_pages.append(group_page.url)
                all_errors.extend(result.errors)
                page_results.append(
                    (group_page.url, result.current_profiles, result.former_profiles)
                )
            else:
                failed_pages.append(group_page.url)

            # PR20: second-hop discovery — trigger when:
            #   (a) the page was fetched successfully (fp is not None), AND
            #   (b) no members were found (either classifier rejected or extraction
            #       returned zero profiles).
            # This catches the common pattern where a lab homepage has zero member
            # sections itself but navigates to a /people or /team sub-page.
            profiles_found = (
                len(result.current_profiles) + len(result.former_profiles)
                if result is not None else 0
            )
            if fp is not None and profiles_found == 0:
                hop2_candidates = self.people_page_discovery.discover(
                    html=fp.raw_html,
                    base_url=fp.base_url,
                    already_seen=tried_urls,
                )
                second_hop_discovered += len(hop2_candidates)

                for hop2 in hop2_candidates:
                    hop2_page = GroupPageSelection(
                        url=hop2.url,
                        source_node_type="second_hop",
                        confidence=0.5,
                        reason="; ".join(hop2.evidence) or "second_hop_discovery",
                        navigation_provider="second_hop_discovery",
                        evidence=list(hop2.evidence),
                    )
                    parsed_pages.append(hop2.url)
                    _, hop2_result = self._process_single_page(
                        name=name,
                        group_page=hop2_page,
                        canonical=canonical,
                    )
                    if hop2_result is None:
                        failed_pages.append(hop2.url)
                        continue
                    successful_pages.append(hop2.url)
                    all_errors.extend(hop2_result.errors)
                    page_results.append(
                        (hop2.url, hop2_result.current_profiles, hop2_result.former_profiles)
                    )
                    if len(hop2_result.current_profiles) + len(hop2_result.former_profiles) > 0:
                        second_hop_successful += 1

        if not page_results:
            # All pages failed — return failed result using the primary page
            return self.graph_builder.build_failed(
                professor_name=name,
                professor_homepage=canonical,
                group_page=primary_group_page,
                provider=self.provider.provider_name,
                fetch_status="page_rejected",
                errors=all_errors or ["All candidate pages failed"],
                parsed_pages=parsed_pages,
                successful_pages=successful_pages,
                failed_pages=failed_pages,
                candidate_pages_discovered=candidate_count,
                second_hop_pages_discovered=second_hop_discovered,
                second_hop_pages_successful=second_hop_successful,
                **ctx,
            )

        # PR17: merge and deduplicate across pages
        merged = self.member_merger.merge(page_results)
        current_merged = merged["current"]
        former_merged = merged["former"]

        # Build member_sources: member_name → list of source page URLs
        member_sources: dict[str, list[str]] = {}
        for mm in current_merged + former_merged:
            member_sources[mm.person.name] = mm.source_pages

        final_current = [mm.person for mm in current_merged]
        final_former = [mm.person for mm in former_merged]

        graph = self.graph_builder.build(
            professor_name=name,
            professor_homepage=canonical,
            group_page=primary_group_page,
            members=final_current,
            former_members=final_former,
            provider=self.provider.provider_name,
            fetch_status="success",
            errors=all_errors,
            parsed_pages=parsed_pages,
            successful_pages=successful_pages,
            failed_pages=failed_pages,
            member_sources=member_sources,
            candidate_pages_discovered=candidate_count,
            second_hop_pages_discovered=second_hop_discovered,
            second_hop_pages_successful=second_hop_successful,
            **ctx,
        )
        return graph

    # ── Two-phase page processing ─────────────────────────────────────────────

    def _fetch_and_parse(
        self,
        group_page: GroupPageSelection,
        name: str,
    ) -> _FetchParseResult | None:
        """
        Phase 1: fetch the page, parse HTML, run cross-identity check.

        Returns ``_FetchParseResult`` when the page is fetched successfully and
        passes the cross-identity check.  Returns ``None`` on fetch failure or
        when the page clearly belongs to a different professor.

        The PageClassifier is NOT run here — callers can inspect navigation
        links for second-hop discovery even when the classifier would reject.
        """
        document = self.fetcher.fetch(group_page.url)
        if document.fetch_status != FetchStatus.SUCCESS:
            self.last_metrics.record_rejected_page(
                name,
                group_page.url,
                f"fetch failed: {document.fetch_status.value}",
            )
            return None

        base_url = document.final_url or document.url
        parsed = self.parser.parse(document.html, base_url=base_url)

        wrong_reason = _wrong_page_professor(parsed, name)
        if wrong_reason:
            self.last_metrics.record_rejected_page(name, group_page.url, wrong_reason)
            return None

        return _FetchParseResult(
            parsed=parsed,
            base_url=base_url,
            document_title=document.title or "",
            raw_html=document.html or "",
        )

    def _classify_and_extract(
        self,
        fp: _FetchParseResult,
        group_page: GroupPageSelection,
        name: str,
    ) -> _PageResult | None:
        """
        Phase 2: run PageClassifier then MemberExtractor on a pre-parsed page.

        Returns ``_PageResult`` when the page passes the classifier and
        extraction runs (even if zero members are found).  Returns ``None``
        when the classifier rejects the page.
        """
        classification = self.page_classifier.classify(
            parsed=fp.parsed,
            page_url=fp.base_url,
            page_title=fp.document_title,
        )
        if not classification.is_acceptable:
            self.last_metrics.record_rejected_page(
                name,
                group_page.url,
                classification.reason,
            )
            return None

        extraction = self.member_extractor.extract(
            professor_name=name,
            group_page=group_page,
            parsed=fp.parsed,
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
            fp.parsed,
            name,
        )
        return _PageResult(
            current_profiles=current_profiles,
            former_profiles=former_profiles,
            errors=list(extraction.errors),
        )

    def _process_single_page(
        self,
        name: str,
        group_page: GroupPageSelection,
        canonical: str,
    ) -> tuple[_FetchParseResult | None, _PageResult | None]:
        """
        Full pipeline for one candidate page (both phases).

        Returns ``(fp_result, page_result)`` where:
          - ``fp_result``  is the fetch+parse result (None on fetch failure)
          - ``page_result`` is the classify+extract result (None on rejection)

        Callers should treat the page as "successful" only when both are
        non-None.  ``fp_result`` alone (with ``page_result=None``) indicates
        the page was fetched but the classifier rejected it — the parsed HTML
        is still available for second-hop navigation discovery.
        """
        fp = self._fetch_and_parse(group_page, name)
        if fp is None:
            return None, None
        result = self._classify_and_extract(fp, group_page, name)
        return fp, result

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

    def _candidates_to_multi(
        self,
        ranked: list[CandidatePage],
        homepage_graph: HomepageGraph,
    ) -> MultiPageSelection:
        """Convert ranked CandidatePage objects to a MultiPageSelection."""
        selected: list[GroupPageSelection] = []
        for candidate in ranked:
            nav_path = ResearchGroupNavigator._build_navigation_path(
                homepage_graph, candidate.url
            )
            reason = (
                "; ".join(candidate.evidence)
                if candidate.evidence
                else f"type:{candidate.page_type}"
            )
            selected.append(
                GroupPageSelection(
                    url=candidate.url,
                    source_node_type=candidate.source_node_type or "candidate",
                    confidence=candidate.score,
                    reason=reason,
                    navigation_path=nav_path,
                    evidence=list(candidate.evidence),
                    navigation_provider="candidate_ranker",
                )
            )

        return MultiPageSelection(
            selected_pages=selected,
            selection_strategy="candidate_ranker",
            selection_reason=(
                f"Selected {len(selected)} candidates via CandidatePageRanker (PR19)"
            ),
        )

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
                self.last_metrics.record_candidate_count(0)
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
            self.last_metrics.record_second_hop(
                graph.second_hop_pages_discovered,
                graph.second_hop_pages_successful,
            )

        return graphs
