"""Homepage Intelligence pipeline — Fetcher → Parser → Navigator → GraphBuilder."""

from __future__ import annotations

from homepage_agent.fetcher import HomepageFetcher
from homepage_agent.graph_builder import GraphBuilder
from homepage_agent.models import FetchStatus, HomepageGraph
from homepage_agent.navigator import Navigator
from homepage_agent.parser import HomepageParser
from homepage_agent.providers.base import NavigatorProvider
from models.professor_profile import ProfessorProfile


class HomepagePipeline:
    """
    Transform professor homepages into structured navigation graphs.

    Only invoked for the final US Top100 — never the full professor universe.
    Analyzes a single homepage URL; no recursive crawling.
    """

    def __init__(
        self,
        provider: NavigatorProvider,
        fetcher: HomepageFetcher | None = None,
        parser: HomepageParser | None = None,
        graph_builder: GraphBuilder | None = None,
    ):
        self.fetcher = fetcher or HomepageFetcher()
        self.parser = parser or HomepageParser()
        self.navigator = Navigator(provider=provider)
        self.graph_builder = graph_builder or GraphBuilder()
        self.provider = provider

    def analyze_url(
        self,
        professor_name: str,
        homepage_url: str,
    ) -> HomepageGraph:
        document = self.fetcher.fetch(homepage_url)

        if document.fetch_status != FetchStatus.SUCCESS:
            return self.graph_builder.build_failure(
                professor_name=professor_name,
                homepage_url=homepage_url,
                fetch_status=document.fetch_status,
                provider=self.provider.provider_name,
                errors=[document.error_message or document.fetch_status.value],
            )

        base_url = document.final_url or document.url
        parsed = self.parser.parse(document.html, base_url=base_url)
        decisions = self.navigator.navigate(
            professor_name=professor_name,
            document=document,
            parsed=parsed,
        )

        return self.graph_builder.build(
            professor_name=professor_name,
            homepage_url=homepage_url,
            fetch_status=document.fetch_status,
            decisions=decisions,
            provider=self.provider.provider_name,
            document=document,
            link_count=len(parsed.links),
        )

    def analyze(self, professor: ProfessorProfile) -> HomepageGraph:
        name = professor.author_profile.author.name
        homepage = professor.homepage

        if not homepage:
            return self.graph_builder.build_failure(
                professor_name=name,
                homepage_url="",
                fetch_status=FetchStatus.INVALID_URL,
                provider=self.provider.provider_name,
                errors=["No homepage URL available"],
            )

        return self.analyze_url(professor_name=name, homepage_url=homepage)

    def analyze_many(
        self,
        professors: list[ProfessorProfile],
    ) -> list[HomepageGraph]:
        graphs: list[HomepageGraph] = []
        for professor in professors:
            graph = self.analyze(professor)
            professor.homepage_graph = graph
            graphs.append(graph)
        return graphs
