"""M5-PR1 — Multi-level navigation explorer.

Deterministic breadth-first exploration of laboratory websites up to a
configurable depth and page budget.  No AI / LLM involvement.

Public API:
  NavigationExplorer – build_graph, discover_links, expand, collect_candidate_pages
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urljoin, urlparse

from homepage_agent.models import FetchStatus

from research_group_agent.candidate_page import CandidatePage
from research_group_agent.fetcher import ResearchGroupFetcher
from research_group_agent.navigation_graph import NavigationGraph, NavigationGraphBuilder
from research_group_agent.navigation_models import (
    MAX_NAVIGATION_DEPTH,
    MAX_NAVIGATION_PAGES,
    VisitStatus,
    infer_page_type,
    is_candidate_page,
    is_expandable_link,
    match_positive_anchor,
    match_positive_url,
    normalize_navigation_url,
    should_ignore_url,
)
from research_group_agent.people_page_discovery import _AllLinksExtractor

logger = logging.getLogger(__name__)

SOURCE_NODE_TYPE = "navigation_explorer"


@dataclass
class DiscoveredLink:
    """A hyperlink extracted from a fetched page."""

    url: str
    anchor_text: str
    edge_type: str


class NavigationExplorer:
    """
    Explore a professor homepage via bounded BFS and collect member-relevant
    candidate pages for the existing ranking / extraction pipeline.
    """

    def __init__(
        self,
        fetcher: ResearchGroupFetcher | None = None,
        max_depth: int = MAX_NAVIGATION_DEPTH,
        max_pages: int = MAX_NAVIGATION_PAGES,
        html_provider: Callable[[str], str | None] | None = None,
    ) -> None:
        self.fetcher = fetcher or ResearchGroupFetcher()
        self.max_depth = max_depth
        self.max_pages = max_pages
        self._html_provider = html_provider
        self._graph_builder = NavigationGraphBuilder()
        self.last_graph: NavigationGraph | None = None

    def build_graph(
        self,
        start_url: str,
        *,
        already_seen: set[str] | None = None,
        base_host: str | None = None,
    ) -> NavigationGraph:
        """
        Run full BFS exploration from *start_url* and return the navigation graph.

        Args:
            start_url:    Professor homepage (canonical URL).
            already_seen: Normalized URLs to treat as already visited (e.g. from
                          CandidatePageGenerator) — prevents duplicate exploration.
            base_host:    Restrict traversal to this host; inferred from start_url
                          when omitted.
        """
        graph = self._graph_builder.create(start_url)
        host = (base_host or urlparse(start_url).netloc).lower()

        seen = set(already_seen or set())
        root_key = normalize_navigation_url(start_url)
        seen.add(root_key)
        graph.visited_urls.add(root_key)

        queue: deque[str] = deque([root_key])

        while queue and graph.statistics.pages_visited < self.max_pages:
            if not self.expand(graph, queue, host=host, seen=seen):
                break

        graph.finalize_statistics()
        self.last_graph = graph
        logger.info(
            "[M5-PR1] NavigationExplorer: visited=%d skipped=%d loops=%d candidates=%d max_depth=%d",
            graph.statistics.pages_visited,
            graph.statistics.pages_skipped,
            graph.statistics.loops_prevented,
            graph.statistics.candidate_pages,
            graph.statistics.maximum_depth,
        )
        return graph

    def discover_links(self, html: str, base_url: str) -> list[DiscoveredLink]:
        """Extract and classify hyperlinks from raw HTML."""
        raw_links = _AllLinksExtractor.extract(html, base_url)
        discovered: list[DiscoveredLink] = []

        for anchor_text, url in raw_links:
            if should_ignore_url(url):
                continue

            edge_type = self._classify_edge(url, anchor_text)
            if edge_type is None:
                continue

            discovered.append(
                DiscoveredLink(
                    url=url,
                    anchor_text=anchor_text,
                    edge_type=edge_type,
                )
            )

        discovered.sort(key=lambda link: normalize_navigation_url(link.url))
        return discovered

    def expand(
        self,
        graph: NavigationGraph,
        queue: deque[str],
        *,
        host: str,
        seen: set[str],
    ) -> bool:
        """
        Visit the next queued page, discover links, and enqueue children.

        Returns False when the queue is empty or the page budget is exhausted.
        """
        if not queue:
            return False

        current_key = queue.popleft()
        node = graph.nodes.get(current_key)
        if node is None:
            return bool(queue)

        if node.depth >= self.max_depth:
            graph.mark_skipped(current_key)
            graph.statistics.pages_skipped += 1
            return bool(queue)

        if graph.statistics.pages_visited >= self.max_pages:
            return False

        html, final_url = self._fetch_html(node.url)
        if html is None:
            graph.mark_skipped(current_key)
            graph.statistics.pages_skipped += 1
            return bool(queue)

        graph.mark_visited(current_key)
        graph.statistics.pages_visited += 1

        if is_candidate_page(final_url or node.url, node.anchor_text):
            graph.register_candidate(node)

        child_candidates: list[tuple[str, DiscoveredLink]] = []
        for link in self.discover_links(html, final_url or node.url):
            if not is_expandable_link(link.url, link.anchor_text):
                continue

            try:
                parsed = urlparse(link.url)
            except Exception:
                continue

            if parsed.netloc.lower() != host:
                continue

            child_key = normalize_navigation_url(link.url)
            if child_key in seen:
                graph.statistics.loops_prevented += 1
                continue

            child_candidates.append((child_key, link))

        child_candidates.sort(key=lambda item: item[0])

        for child_key, link in child_candidates:
            if graph.statistics.pages_visited + len(queue) >= self.max_pages:
                break

            child_depth = node.depth + 1
            if child_depth > self.max_depth:
                continue

            new_node = self._graph_builder.register_discovered(
                graph,
                url=link.url,
                parent_url=node.url,
                depth=child_depth,
                anchor_text=link.anchor_text,
                discovered_from=current_key,
                edge_type=link.edge_type,
            )
            if new_node is None:
                continue

            seen.add(child_key)
            queue.append(child_key)

        return bool(queue)

    def collect_candidate_pages(
        self,
        graph: NavigationGraph,
        *,
        already_seen: set[str] | None = None,
    ) -> list[CandidatePage]:
        """Convert navigation graph candidate nodes into CandidatePage objects."""
        seen = set(already_seen or set())
        candidates: list[CandidatePage] = []

        for node in graph.candidate_pages:
            key = node.normalized_url
            if key in seen:
                continue
            seen.add(key)

            evidence: list[str] = ["navigation_explorer"]
            anchor_signal = match_positive_anchor(node.anchor_text)
            url_signal = match_positive_url(node.url)
            if anchor_signal:
                evidence.append(f"anchor_match:{anchor_signal}")
            if url_signal:
                evidence.append(f"path_match:{url_signal}")
            evidence.append(f"depth:{node.depth}")

            candidates.append(
                CandidatePage(
                    url=node.url,
                    page_type=node.page_type or infer_page_type(node.url, node.anchor_text),
                    anchor_text=node.anchor_text,
                    source_node_type=SOURCE_NODE_TYPE,
                    graph_confidence=max(0.0, 0.9 - (node.depth * 0.1)),
                    evidence=evidence,
                )
            )

        return candidates

    def explore(
        self,
        start_url: str,
        *,
        already_seen: set[str] | None = None,
    ) -> tuple[NavigationGraph, list[CandidatePage]]:
        """Convenience wrapper: build_graph + collect_candidate_pages."""
        seen = set(already_seen or set())
        graph = self.build_graph(start_url, already_seen=seen)
        candidates = self.collect_candidate_pages(graph, already_seen=seen)
        return graph, candidates

    def _fetch_html(self, url: str) -> tuple[str | None, str | None]:
        if self._html_provider is not None:
            html = self._html_provider(url)
            return html, url

        document = self.fetcher.fetch(url)
        if document.fetch_status != FetchStatus.SUCCESS:
            return None, None
        return document.html or "", document.final_url or document.url or url

    @staticmethod
    def _classify_edge(url: str, anchor_text: str) -> str | None:
        anchor_signal = match_positive_anchor(anchor_text)
        if anchor_signal:
            return f"anchor:{anchor_signal}"
        url_signal = match_positive_url(url)
        if url_signal:
            return f"url:{url_signal}"
        return None
