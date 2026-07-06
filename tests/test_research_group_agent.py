import unittest
from unittest.mock import MagicMock, patch

from homepage_agent.homepage_resolver import CanonicalHomepageResolver, HomepagePageType
from homepage_agent.models import ConfidenceScore, FetchStatus, GraphNode, HomepageGraph
from homepage_agent.parser import HomepageParser
from models.author import Author
from models.author_profile import AuthorProfile
from models.professor_profile import ProfessorProfile
from research_group_agent.enrichment import TalentEnricher
from research_group_agent.graph_builder import ResearchGroupGraphBuilder
from research_group_agent.group_discovery import GroupPageDiscoverer
from research_group_agent.models import MemberRole, MemberStatus
from research_group_agent.navigator import ResearchGroupNavigator
from research_group_agent.parser import MemberPageParser
from research_group_agent.pipeline import ResearchGroupPipeline
from research_group_agent.providers.navigator_stub import StubResearchGroupNavigatorProvider
from research_group_agent.providers.stub import StubResearchGroupProvider
from research_group_agent.report import ResearchGroupReport


MEMBER_PAGE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Netravali Research Group</title></head>
<body>
  <nav><a href="/news">News</a></nav>
  <h1>Princeton Systems Group</h1>
  <h2>Current Members</h2>
  <ul>
    <li><a href="https://example.edu/~jwang/">Jian Wang</a> – PhD Student</li>
    <li><a href="https://github.com/alicechen">Alice Chen</a> – Postdoc</li>
    <li><a href="https://scholar.google.com/citations?user=abc">Bob Smith</a> – Research Staff</li>
  </ul>
  <h2>Alumni</h2>
  <ul>
    <li><a href="https://example.edu/~clee/">Carol Lee</a> – Former PhD Student</li>
  </ul>
</body>
</html>
"""

FACULTY_PROFILE_HTML = """
<html><body>
  <a href="https://ravi-netravali.github.io/">Personal Website</a>
  <a href="https://www.cs.princeton.edu/people/faculty">Faculty</a>
</body></html>
"""


def _homepage_graph_with_lab_and_people() -> HomepageGraph:
    return HomepageGraph(
        professor_name="Ravi Netravali",
        homepage_url="https://example.edu/~ravi/people.html",
        fetch_status=FetchStatus.SUCCESS,
        original_homepage="https://www.cs.princeton.edu/people/profile/ravian",
        canonical_homepage="https://example.edu/~ravi/people.html",
        graph_nodes=[
            GraphNode(
                node_type="lab_page",
                url="https://example.edu/~ravi/people.html",
                confidence=ConfidenceScore.from_stub(0.85, 0.8),
                discovery_method="heuristic",
                anchor_text="Lab Members",
            ),
        ],
    )


def _professor(homepage_graph: HomepageGraph | None = None) -> ProfessorProfile:
    profile = AuthorProfile(
        author=Author(pid=None, name="Ravi Netravali"),
        papers=[],
    )
    return ProfessorProfile(
        author_profile=profile,
        homepage="https://example.edu/~ravi/",
        homepage_graph=homepage_graph,
        is_us=True,
    )


class TestResearchGroupNavigator(unittest.TestCase):
    def test_returns_navigation_decisions_not_direct_url(self):
        graph = _homepage_graph_with_lab_and_people()
        navigator = ResearchGroupNavigator(provider=StubResearchGroupNavigatorProvider())

        decisions = navigator.navigate("Ravi Netravali", graph)

        self.assertTrue(decisions)
        self.assertTrue(all(hasattr(item, "candidate_url") for item in decisions))
        self.assertTrue(all(hasattr(item, "confidence") for item in decisions))

    def test_select_picks_highest_confidence_decision(self):
        graph = _homepage_graph_with_lab_and_people()
        navigator = ResearchGroupNavigator(provider=StubResearchGroupNavigatorProvider())

        decisions = navigator.navigate("Ravi Netravali", graph)
        selection = navigator.select(decisions)

        self.assertIsNotNone(selection)
        self.assertEqual(selection.url, decisions[0].candidate_url)
        self.assertEqual(selection.source_node_type, "lab_page")

    def test_group_page_discoverer_delegates_to_navigator(self):
        graph = _homepage_graph_with_lab_and_people()
        discoverer = GroupPageDiscoverer()

        selection = discoverer.select(graph)

        self.assertIsNotNone(selection)
        self.assertIn("people.html", selection.url)


class TestCanonicalHomepageResolver(unittest.TestCase):
    def test_classifies_university_faculty_profile(self):
        url = "https://www.cs.princeton.edu/people/profile/ravian"
        self.assertEqual(
            CanonicalHomepageResolver.classify_url(url),
            HomepagePageType.UNIVERSITY_FACULTY,
        )

    def test_classifies_personal_homepage(self):
        url = "https://ravi-netravali.github.io/"
        self.assertEqual(
            CanonicalHomepageResolver.classify_url(url),
            HomepagePageType.PERSONAL_HOMEPAGE,
        )

    @patch("homepage_agent.pipeline.HomepagePipeline.analyze_url")
    def test_upgrades_faculty_profile_to_personal_site(self, mock_analyze):
        mock_analyze.return_value = HomepageGraph(
            professor_name="Ravi Netravali",
            homepage_url="https://ravi-netravali.github.io/",
            fetch_status=FetchStatus.SUCCESS,
            graph_nodes=[],
        )
        graph = HomepageGraph(
            professor_name="Ravi Netravali",
            homepage_url="https://www.cs.princeton.edu/people/profile/ravian",
            fetch_status=FetchStatus.SUCCESS,
            graph_nodes=[
                GraphNode(
                    node_type="contact_page",
                    url="https://ravi-netravali.github.io/",
                    confidence=ConfidenceScore.from_stub(0.9, 0.8),
                    discovery_method="heuristic",
                    anchor_text="Personal Website",
                ),
            ],
        )
        resolver = CanonicalHomepageResolver()
        resolver.homepage_pipeline = MagicMock()
        resolver.homepage_pipeline.analyze_url = mock_analyze

        resolved = resolver.resolve(graph)
        self.assertTrue(resolved.homepage_resolution_method.startswith("link_upgrade"))
        self.assertEqual(resolved.canonical_homepage, "https://ravi-netravali.github.io/")


class TestMemberPageParser(unittest.TestCase):
    def test_extracts_current_members_only(self):
        parsed = MemberPageParser().parse(
            MEMBER_PAGE_HTML,
            base_url="https://example.edu/~ravi/people.html",
        )
        current = [
            entry for entry in parsed.entries
            if entry.member_status == MemberStatus.CURRENT
        ]
        names = {entry.name for entry in current}
        self.assertIn("Jian Wang", names)
        self.assertNotIn("Carol Lee", names)

    def test_alumni_section_parsed_separately_in_stub(self):
        parsed = MemberPageParser().parse(
            MEMBER_PAGE_HTML,
            base_url="https://example.edu/~ravi/people.html",
        )
        full_html = MEMBER_PAGE_HTML
        parsed_all = MemberPageParser().parse(full_html, base_url="https://example.edu/")
        alumni_sections = [
            section for section in parsed_all.sections if section.member_status == MemberStatus.ALUMNI
        ]
        self.assertTrue(any(section.name for section in alumni_sections))


class TestStubResearchGroupProvider(unittest.TestCase):
    def test_separates_current_and_former_members(self):
        html = MEMBER_PAGE_HTML.replace(
            "Carol Lee",
            "Carol Lee",
        )
        parsed = MemberPageParser().parse(html, base_url="https://example.edu/~ravi/people.html")

        # Manually parse alumni by using full parser on alumni block
        alumni_html = """
        <h2>Alumni</h2><ul><li><a href="https://x.edu/~clee/">Carol Lee</a> – Former PhD</li></ul>
        """
        combined = MEMBER_PAGE_HTML + alumni_html
        parsed = MemberPageParser().parse(combined, base_url="https://example.edu/")

        result = StubResearchGroupProvider().extract_members("", parsed, "Ravi Netravali")
        current_names = {member.name for member in result.members}
        self.assertIn("Jian Wang", current_names)
        self.assertNotIn("Carol Lee", current_names)


class TestResearchGroupPipeline(unittest.TestCase):
    @patch("research_group_agent.fetcher.HomepageFetcher.fetch")
    def test_exports_current_members_with_status(self, mock_fetch):
        mock_fetch.return_value = __import__(
            "homepage_agent.models", fromlist=["HomepageDocument"]
        ).HomepageDocument(
            url="https://example.edu/~ravi/people.html",
            html=MEMBER_PAGE_HTML,
            title="Netravali Research Group",
            fetch_status=FetchStatus.SUCCESS,
            final_url="https://example.edu/~ravi/people.html",
        )

        graph = HomepageGraph(
            professor_name="Ravi Netravali",
            homepage_url="https://example.edu/~ravi/",
            fetch_status=FetchStatus.SUCCESS,
            original_homepage="https://www.cs.princeton.edu/people/profile/ravian",
            canonical_homepage="https://example.edu/~ravi/",
            homepage_resolution_method="link_upgrade:personal_website",
            homepage_resolution_confidence=0.95,
            graph_nodes=_homepage_graph_with_lab_and_people().graph_nodes,
        )
        pipeline = ResearchGroupPipeline(provider=StubResearchGroupProvider())
        result = pipeline.analyze(_professor(graph), graph)

        self.assertEqual(result.fetch_status, "success")
        self.assertEqual(result.original_homepage, "https://www.cs.princeton.edu/people/profile/ravian")
        self.assertEqual(result.canonical_homepage, "https://example.edu/~ravi/")
        self.assertTrue(all(member.status == MemberStatus.CURRENT for member in result.members))


class TestResearchGroupReport(unittest.TestCase):
    @patch("research_group_agent.fetcher.HomepageFetcher.fetch")
    def test_report_includes_homepage_and_current_member_stats(self, mock_fetch):
        mock_fetch.return_value = __import__(
            "homepage_agent.models", fromlist=["HomepageDocument"]
        ).HomepageDocument(
            url="https://example.edu/~ravi/people.html",
            html=MEMBER_PAGE_HTML,
            title="Group",
            fetch_status=FetchStatus.SUCCESS,
        )

        professor = _professor(_homepage_graph_with_lab_and_people())
        pipeline = ResearchGroupPipeline(provider=StubResearchGroupProvider())
        graphs = pipeline.analyze_many([professor])
        report = ResearchGroupReport.generate(graphs, metrics=pipeline.last_metrics)

        self.assertIn("homepage_resolution", report)
        self.assertIn("current_members_extracted", report)
        self.assertIn("former_members_extracted", report)


if __name__ == "__main__":
    unittest.main()
