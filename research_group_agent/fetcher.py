"""HTTP fetcher for research group pages — reuses homepage fetcher infrastructure."""

from __future__ import annotations

from homepage_agent.fetcher import HomepageFetcher
from homepage_agent.models import HomepageDocument


class ResearchGroupFetcher:
    """
    Fetch a single research group page.

    Thin wrapper around HomepageFetcher with a separate cache namespace so
    PeopleAgent / ScholarAgent can reuse the same underlying fetch layer.
    """

    def __init__(self, fetcher: HomepageFetcher | None = None):
        self._fetcher = fetcher or HomepageFetcher(
            cache_dir="data/cache/research_groups",
        )

    def fetch(self, url: str) -> HomepageDocument:
        return self._fetcher.fetch(url)
