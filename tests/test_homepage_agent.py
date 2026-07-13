import unittest
from unittest.mock import MagicMock, patch

from requests.exceptions import ConnectTimeout, ReadTimeout, TooManyRedirects

from homepage_agent.fetcher import FetchStats, HomepageFetcher
from homepage_agent.graph_builder import GraphBuilder
from homepage_agent.models import (
    ConfidenceScore,
    FetchStatus,
    NavigationDecision,
    NodeCategory,
    SCHEMA_VERSION,
)
from homepage_agent.parser import HomepageParser
from homepage_agent.pipeline import HomepagePipeline
from homepage_agent.providers.stub import StubNavigatorProvider
from homepage_agent.report import HomepageAgentReport
from homepage_agent.prompt_builder import build_navigation_prompt
from models.author import Author
from models.author_profile import AuthorProfile
from models.professor_profile import ProfessorProfile


SAMPLE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Professor Ada Lovelace</title></head>
<body>
  <h1>Ada Lovelace</h1>
  <p>Systems researcher at Example University.</p>
  <nav>
    <a href="/people.html">People</a>
    <a href="https://example.edu/lab/">Research Lab</a>
    <a href="/projects">Projects</a>
    <a href="publications/">Publications</a>
    <a href="https://github.com/ada/tools">Software</a>
    <a href="/teaching">Teaching</a>
    <a href="/news">News</a>
    <a href="contact.html">Contact</a>
    <a href="https://twitter.com/ada">Twitter</a>
  </nav>
</body>
</html>
"""


def _professor(homepage: str | None = "https://example.edu/~ada/") -> ProfessorProfile:
    profile = AuthorProfile(
        author=Author(pid=None, name="Ada Lovelace"),
        papers=[],
    )
    return ProfessorProfile(
        author_profile=profile,
        university="Example University",
        homepage=homepage,
        is_us=True,
    )


class TestConfidenceScore(unittest.TestCase):
    def test_from_stub_computes_final_score(self):
        score = ConfidenceScore.from_stub(keyword_score=0.9, structure_score=0.5)
        self.assertEqual(score.provider_score, 0.9)
        self.assertAlmostEqual(score.final_score, 0.76, places=2)

    def test_certain(self):
        score = ConfidenceScore.certain()
        self.assertEqual(score.final_score, 1.0)


class TestHomepageParser(unittest.TestCase):
    def test_extracts_title_text_and_links(self):
        parser = HomepageParser()
        parsed = parser.parse(SAMPLE_HTML, base_url="https://example.edu/~ada/")

        self.assertEqual(parsed.page_title, "Professor Ada Lovelace")
        self.assertIn("Systems researcher", parsed.visible_text)
        self.assertGreaterEqual(len(parsed.links), 8)

        urls = {link.absolute_url for link in parsed.links}
        self.assertIn("https://example.edu/people.html", urls)
        self.assertIn("https://example.edu/lab/", urls)
        self.assertIn("https://example.edu/~ada/publications/", urls)

        people = next(link for link in parsed.links if "people" in link.absolute_url)
        self.assertEqual(people.anchor_text, "People")

    def test_skips_mailto_and_fragment_links(self):
        html = '<html><body><a href="#top">Top</a><a href="mailto:a@b.edu">Email</a></body></html>'
        parsed = HomepageParser().parse(html, base_url="https://example.edu/")
        self.assertEqual(parsed.links, [])


class TestStubNavigatorProvider(unittest.TestCase):
    def test_returns_navigation_decisions(self):
        parser = HomepageParser()
        parsed = parser.parse(SAMPLE_HTML, base_url="https://example.edu/~ada/")
        provider = StubNavigatorProvider()

        from homepage_agent.models import HomepageDocument

        document = HomepageDocument(
            url="https://example.edu/~ada/",
            html=SAMPLE_HTML,
            title="Professor Ada Lovelace",
            fetch_status=FetchStatus.SUCCESS,
            final_url="https://example.edu/~ada/",
        )
        prompt = build_navigation_prompt("Ada Lovelace", document, parsed)
        decisions = provider.classify_links(prompt, document, parsed.links)

        self.assertIsInstance(decisions, list)
        types = {decision.candidate_type for decision in decisions}
        self.assertIn(NodeCategory.PEOPLE_PAGE, types)
        self.assertIn(NodeCategory.PUBLICATIONS_PAGE, types)
        self.assertIn(NodeCategory.CONTACT_PAGE, types)

        people = next(
            decision for decision in decisions
            if decision.candidate_type == NodeCategory.PEOPLE_PAGE
        )
        self.assertGreaterEqual(people.final_confidence, 0.5)
        self.assertTrue(people.reason)
        self.assertIsInstance(people.confidence, ConfidenceScore)

    def test_ignores_social_links(self):
        parser = HomepageParser()
        parsed = parser.parse(
            '<a href="https://twitter.com/ada">Twitter</a>',
            base_url="https://example.edu/",
        )
        provider = StubNavigatorProvider()
        from homepage_agent.models import HomepageDocument

        document = HomepageDocument(
            url="https://example.edu/",
            html="",
            title="",
            fetch_status=FetchStatus.SUCCESS,
        )
        decisions = provider.classify_links("", document, parsed.links)
        self.assertEqual(decisions, [])


class TestGraphBuilder(unittest.TestCase):
    def test_builds_graph_from_decisions(self):
        decisions = [
            NavigationDecision(
                candidate_url="https://example.edu/people.html",
                candidate_type=NodeCategory.PEOPLE_PAGE,
                confidence=ConfidenceScore.from_stub(0.9, 0.5),
                reason="anchor matched 'people'",
                anchor_text="People",
            )
        ]
        from homepage_agent.models import HomepageDocument

        document = HomepageDocument(
            url="https://example.edu/~ada/",
            html=SAMPLE_HTML,
            title="Professor Ada Lovelace",
            fetch_status=FetchStatus.SUCCESS,
            final_url="https://example.edu/~ada/",
        )

        graph = GraphBuilder().build(
            professor_name="Ada Lovelace",
            homepage_url="https://example.edu/~ada/",
            fetch_status=FetchStatus.SUCCESS,
            decisions=decisions,
            provider="heuristic",
            document=document,
            link_count=9,
        )

        self.assertEqual(graph.schema_version, SCHEMA_VERSION)
        self.assertEqual(graph.pipeline_version, "PR13.2")
        self.assertEqual(graph.homepage_status, "success")
        self.assertEqual(len(graph.graph_nodes), 2)
        self.assertIsNotNone(graph.people_page)
        self.assertIsNotNone(graph.nodes["homepage"])
        self.assertEqual(graph.people_page.anchor_text, "People")


class TestHomepagePipeline(unittest.TestCase):
    def test_analyze_url_builds_graph(self):
        fetcher = MagicMock()
        fetcher.fetch.return_value = __import__(
            "homepage_agent.models", fromlist=["HomepageDocument"]
        ).HomepageDocument(
            url="https://example.edu/~ada/",
            html=SAMPLE_HTML,
            title="Professor Ada Lovelace",
            fetch_status=FetchStatus.SUCCESS,
            final_url="https://example.edu/~ada/",
            status_code=200,
        )

        pipeline = HomepagePipeline(
            provider=StubNavigatorProvider(),
            fetcher=fetcher,
        )
        graph = pipeline.analyze_url(
            professor_name="Ada Lovelace",
            homepage_url="https://example.edu/~ada/",
        )

        self.assertEqual(graph.fetch_status, FetchStatus.SUCCESS)
        self.assertIsNotNone(graph.nodes["homepage"])
        self.assertIsNotNone(graph.people_page)
        self.assertGreater(graph.link_count, 0)
        self.assertTrue(graph.graph_nodes)

    def test_missing_homepage_returns_error_graph(self):
        pipeline = HomepagePipeline(provider=StubNavigatorProvider())
        graph = pipeline.analyze(_professor(homepage=None))

        self.assertEqual(graph.fetch_status, FetchStatus.INVALID_URL)
        self.assertIn("No homepage URL available", graph.errors)
        self.assertEqual(graph.graph_nodes, [])

    def test_analyze_many_attaches_to_professor(self):
        fetcher = MagicMock()
        fetcher.fetch.return_value = __import__(
            "homepage_agent.models", fromlist=["HomepageDocument"]
        ).HomepageDocument(
            url="https://example.edu/~ada/",
            html=SAMPLE_HTML,
            title="Professor Ada Lovelace",
            fetch_status=FetchStatus.SUCCESS,
            final_url="https://example.edu/~ada/",
        )

        pipeline = HomepagePipeline(
            provider=StubNavigatorProvider(),
            fetcher=fetcher,
        )
        professor = _professor()
        pipeline.analyze_many([professor])

        self.assertIsNotNone(professor.homepage_graph)
        self.assertEqual(professor.homepage_graph.professor_name, "Ada Lovelace")

    def test_to_dict_includes_schema_and_legacy_nodes(self):
        fetcher = MagicMock()
        fetcher.fetch.return_value = __import__(
            "homepage_agent.models", fromlist=["HomepageDocument"]
        ).HomepageDocument(
            url="https://example.edu/~ada/",
            html=SAMPLE_HTML,
            title="Professor Ada Lovelace",
            fetch_status=FetchStatus.SUCCESS,
            final_url="https://example.edu/~ada/",
        )

        graph = HomepagePipeline(
            provider=StubNavigatorProvider(),
            fetcher=fetcher,
        ).analyze_url("Ada Lovelace", "https://example.edu/~ada/")

        payload = graph.to_dict()
        self.assertEqual(payload["schema_version"], SCHEMA_VERSION)
        self.assertIn("graph_nodes", payload)
        self.assertIn("nodes", payload)
        self.assertIsNotNone(payload["nodes"]["people_page"])
        non_homepage = [
            node for node in payload["graph_nodes"]
            if node["node_type"] != "homepage"
        ]
        self.assertTrue(non_homepage)
        self.assertIn("confidence_detail", non_homepage[0])


class TestHomepageFetcher(unittest.TestCase):
    @patch("homepage_agent.fetcher.requests.Session.get")
    def test_fetch_success(self, mock_get):
        response = MagicMock()
        response.url = "https://example.edu/"
        response.status_code = 200
        response.text = "<html><title>Test</title><body>Hello</body></html>"
        mock_get.return_value = response

        fetcher = HomepageFetcher(use_cache=False, retries=0)
        document = fetcher.fetch("example.edu")

        self.assertEqual(document.fetch_status, FetchStatus.SUCCESS)
        self.assertEqual(document.title, "Test")
        self.assertIn("Hello", document.html)
        mock_get.assert_called_once_with(
            "https://example.edu",
            timeout=(5, 10),
            allow_redirects=True,
        )

    @patch("homepage_agent.fetcher.requests.Session.get")
    def test_fetch_http_error(self, mock_get):
        response = MagicMock()
        response.url = "https://example.edu/missing"
        response.status_code = 404
        response.text = "Not Found"
        mock_get.return_value = response

        document = HomepageFetcher(use_cache=False, retries=0).fetch(
            "https://example.edu/missing"
        )
        self.assertEqual(document.fetch_status, FetchStatus.HTTP_ERROR)

    @patch("homepage_agent.fetcher.logger")
    @patch("homepage_agent.fetcher.requests.Session.get")
    def test_fetch_read_timeout_returns_without_retry(self, mock_get, mock_logger):
        mock_get.side_effect = ReadTimeout("read timed out")

        fetcher = HomepageFetcher(use_cache=False, retries=2)
        document = fetcher.fetch("https://slow.example.edu/")

        self.assertEqual(document.fetch_status, FetchStatus.TIMEOUT)
        mock_get.assert_called_once()
        mock_logger.warning.assert_called()

    @patch("homepage_agent.fetcher.logger")
    @patch("homepage_agent.fetcher.requests.Session.get")
    def test_fetch_connect_timeout_returns_without_retry(self, mock_get, mock_logger):
        mock_get.side_effect = ConnectTimeout("connect timed out")

        fetcher = HomepageFetcher(use_cache=False, retries=2)
        document = fetcher.fetch("https://unreachable.example.edu/")

        self.assertEqual(document.fetch_status, FetchStatus.TIMEOUT)
        mock_get.assert_called_once()
        mock_logger.warning.assert_called()

    @patch("homepage_agent.fetcher.logger")
    @patch("homepage_agent.fetcher.requests.Session.get")
    def test_fetch_too_many_redirects_skips_page(self, mock_get, mock_logger):
        mock_get.side_effect = TooManyRedirects("too many redirects")

        fetcher = HomepageFetcher(use_cache=False, retries=2, max_redirects=5)
        document = fetcher.fetch("https://redirect-loop.example.edu/")

        self.assertEqual(document.fetch_status, FetchStatus.NETWORK_ERROR)
        self.assertIn("redirect limit", document.error_message.lower())
        mock_get.assert_called_once()
        mock_logger.warning.assert_called()

    @patch("homepage_agent.fetcher.time.monotonic")
    @patch("homepage_agent.fetcher.logger")
    @patch("homepage_agent.fetcher.requests.Session.get")
    def test_fetch_logs_slow_request(self, mock_get, mock_logger, mock_monotonic):
        mock_monotonic.side_effect = [0.0, 7.8, 7.8]
        response = MagicMock()
        response.url = "https://example.edu/"
        response.status_code = 200
        response.text = "<html><title>Test</title><body>Hello</body></html>"
        mock_get.return_value = response

        fetcher = HomepageFetcher(use_cache=False, retries=0)
        fetcher.fetch("https://example.edu/")

        mock_logger.warning.assert_called_with(
            "Slow fetch (%.1fs) %s",
            7.8,
            "https://example.edu/",
        )

    def test_session_redirect_limit_configured(self):
        fetcher = HomepageFetcher(use_cache=False, max_redirects=5)
        self.assertEqual(fetcher._session.max_redirects, 5)

    @patch("homepage_agent.fetcher.requests.Session.get")
    def test_fetch_records_success_stats(self, mock_get):
        response = MagicMock()
        response.url = "https://example.edu/"
        response.status_code = 200
        response.text = "<html><title>Test</title><body>Hello</body></html>"
        mock_get.return_value = response

        stats = FetchStats()
        fetcher = HomepageFetcher(use_cache=False, retries=0, stats=stats)
        document = fetcher.fetch("https://example.edu/")

        self.assertEqual(document.fetch_status, FetchStatus.SUCCESS)
        self.assertEqual(stats.total_requests, 1)
        self.assertEqual(stats.successful, 1)
        self.assertEqual(stats.timeouts, 0)

    @patch("homepage_agent.fetcher.requests.Session.get")
    def test_fetch_records_timeout_stats(self, mock_get):
        mock_get.side_effect = ReadTimeout("read timed out")

        stats = FetchStats()
        fetcher = HomepageFetcher(use_cache=False, retries=2, stats=stats)
        fetcher.fetch("https://slow.example.edu/")

        self.assertEqual(stats.total_requests, 1)
        self.assertEqual(stats.timeouts, 1)

    @patch("homepage_agent.fetcher.requests.Session.get")
    def test_fetch_records_redirect_limit_stats(self, mock_get):
        mock_get.side_effect = TooManyRedirects("too many redirects")

        stats = FetchStats()
        fetcher = HomepageFetcher(use_cache=False, retries=0, stats=stats)
        fetcher.fetch("https://redirect-loop.example.edu/")

        self.assertEqual(stats.total_requests, 1)
        self.assertEqual(stats.redirect_limit_exceeded, 1)
        self.assertEqual(stats.network_errors, 0)

    def test_fetch_stats_summary_format(self):
        stats = FetchStats()
        stats.record(0.4, FetchStatus.SUCCESS)
        stats.record(6.2, FetchStatus.TIMEOUT)
        stats.record(1.1, FetchStatus.NETWORK_ERROR, redirect_limit=True)

        summary = stats.to_dict()
        self.assertEqual(summary["total_requests"], 3)
        self.assertEqual(summary["successful"], 1)
        self.assertEqual(summary["timeouts"], 1)
        self.assertEqual(summary["redirect_limit_exceeded"], 1)
        self.assertEqual(summary["slow_requests"], 1)
        self.assertIn("Fetch Summary", stats.format_summary())


class TestHomepageAgentReport(unittest.TestCase):
    def test_report_includes_enhanced_metrics(self):
        pipeline = HomepagePipeline(provider=StubNavigatorProvider())
        fetcher = MagicMock()
        fetcher.fetch.return_value = __import__(
            "homepage_agent.models", fromlist=["HomepageDocument"]
        ).HomepageDocument(
            url="https://example.edu/~ada/",
            html=SAMPLE_HTML,
            title="Professor Ada Lovelace",
            fetch_status=FetchStatus.SUCCESS,
            final_url="https://example.edu/~ada/",
        )
        pipeline.fetcher = fetcher

        graphs = pipeline.analyze_many([_professor(), _professor(homepage=None)])
        report = HomepageAgentReport.generate(graphs)

        self.assertEqual(report["total_professors"], 2)
        self.assertEqual(report["fetch_success_count"], 1)
        self.assertIn("homepage_coverage", report)
        self.assertIn("node_type_distribution", report)
        self.assertIn("average_links_per_homepage", report)
        self.assertIn("most_common_anchor_texts", report)
        self.assertIn("broken_homepage_statistics", report)
        self.assertIn("manual_review_reasons", report)
        self.assertGreaterEqual(report["discovery_counts"]["people_page"], 1)


if __name__ == "__main__":
    unittest.main()
