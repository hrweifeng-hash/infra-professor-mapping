import unittest
from unittest.mock import MagicMock, patch

from homepage_agent.homepage_resolver import CanonicalHomepageResolver, HomepagePageType
from homepage_agent.models import ConfidenceScore, FetchStatus, GraphNode, HomepageGraph
from homepage_agent.parser import HomepageParser
from models.author import Author
from models.author_profile import AuthorProfile
from models.professor_profile import ProfessorProfile
from research_group_agent.candidate_page import (
    CandidatePage,
    CandidatePageGenerator,
    CandidatePageRanker,
    PAGE_TYPE_ALUMNI,
    PAGE_TYPE_GROUP,
    PAGE_TYPE_HOMEPAGE,
    PAGE_TYPE_LAB,
    PAGE_TYPE_MEMBERS,
    PAGE_TYPE_OTHER,
    PAGE_TYPE_PEOPLE,
    PAGE_TYPE_PROJECTS,
    PAGE_TYPE_STUDENTS,
    PAGE_TYPE_TEAM,
)
from research_group_agent.enrichment import TalentEnricher
from research_group_agent.graph_builder import ResearchGroupGraphBuilder
from research_group_agent.group_discovery import GroupPageDiscoverer
from research_group_agent.models import MemberRole, MemberStatus, PIPELINE_VERSION, SCHEMA_VERSION
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
        from homepage_agent.models import HomepageDocument

        def _fetch(url: str) -> HomepageDocument:
            if "~ravi/" in url and "people" not in url:
                return HomepageDocument(
                    url=url,
                    html="<html><body>Homepage</body></html>",
                    title="Ravi Netravali",
                    fetch_status=FetchStatus.SUCCESS,
                    final_url=url,
                )
            return HomepageDocument(
                url="https://example.edu/~ravi/people.html",
                html=MEMBER_PAGE_HTML,
                title="Netravali Research Group",
                fetch_status=FetchStatus.SUCCESS,
                final_url="https://example.edu/~ravi/people.html",
            )

        mock_fetch.side_effect = _fetch

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
        self.assertGreater(result.member_count, 0)
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

    @patch("research_group_agent.fetcher.HomepageFetcher.fetch")
    def test_report_includes_candidate_page_stats(self, mock_fetch):
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

        self.assertIn("candidate_pages", report)
        cp = report["candidate_pages"]
        self.assertIn("total_candidates_discovered", cp)
        self.assertIn("average_candidates_per_professor", cp)
        self.assertIn("candidate_page_success_rate", cp)
        self.assertGreater(cp["total_candidates_discovered"], 0)


class TestVersionConstants(unittest.TestCase):
    def test_schema_version_is_1_6(self):
        self.assertEqual(SCHEMA_VERSION, "1.7")

    def test_pipeline_version_is_pr32(self):
        self.assertEqual(PIPELINE_VERSION, "PR32")


class TestCandidatePageGenerator(unittest.TestCase):
    def _graph_with_nodes(self, nodes: list[GraphNode]) -> HomepageGraph:
        return HomepageGraph(
            professor_name="Ada Lovelace",
            homepage_url="https://ada.github.io/",
            fetch_status=FetchStatus.SUCCESS,
            canonical_homepage="https://ada.github.io/",
            graph_nodes=nodes,
        )

    def test_returns_empty_for_failed_fetch(self):
        graph = HomepageGraph(
            professor_name="Ada Lovelace",
            homepage_url="https://ada.github.io/",
            fetch_status=FetchStatus.HTTP_ERROR,
            graph_nodes=[],
        )
        result = CandidatePageGenerator().generate(graph)
        self.assertEqual(result, [])

    def test_always_includes_canonical_homepage(self):
        graph = self._graph_with_nodes([])
        result = CandidatePageGenerator().generate(graph)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].url, "https://ada.github.io/")
        self.assertEqual(result[0].page_type, PAGE_TYPE_HOMEPAGE)

    def test_includes_all_graph_nodes(self):
        nodes = [
            GraphNode(
                node_type="lab_page",
                url="https://ada.github.io/lab/",
                confidence=ConfidenceScore.from_stub(0.9, 0.8),
                discovery_method="heuristic",
                anchor_text="Lab Members",
            ),
            GraphNode(
                node_type="projects_page",
                url="https://ada.github.io/projects/",
                confidence=ConfidenceScore.from_stub(0.7, 0.6),
                discovery_method="heuristic",
                anchor_text="Projects",
            ),
        ]
        graph = self._graph_with_nodes(nodes)
        result = CandidatePageGenerator().generate(graph)
        urls = {c.url for c in result}
        self.assertIn("https://ada.github.io/", urls)
        self.assertIn("https://ada.github.io/lab/", urls)
        self.assertIn("https://ada.github.io/projects/", urls)

    def test_projects_page_mapped_to_projects_type(self):
        nodes = [
            GraphNode(
                node_type="projects_page",
                url="https://ada.github.io/projects/",
                confidence=ConfidenceScore.from_stub(0.7, 0.6),
                discovery_method="heuristic",
            ),
        ]
        graph = self._graph_with_nodes(nodes)
        result = CandidatePageGenerator().generate(graph)
        proj = next(c for c in result if "projects" in c.url)
        self.assertEqual(proj.page_type, PAGE_TYPE_PROJECTS)

    def test_alumni_url_detected(self):
        nodes = [
            GraphNode(
                node_type="people_page",
                url="https://ada.github.io/alumni/",
                confidence=ConfidenceScore.from_stub(0.6, 0.5),
                discovery_method="heuristic",
                anchor_text="Alumni",
            ),
        ]
        graph = self._graph_with_nodes(nodes)
        result = CandidatePageGenerator().generate(graph)
        alumni = next(c for c in result if "alumni" in c.url)
        self.assertEqual(alumni.page_type, PAGE_TYPE_ALUMNI)

    def test_students_url_detected(self):
        nodes = [
            GraphNode(
                node_type="people_page",
                url="https://ada.github.io/students/",
                confidence=ConfidenceScore.from_stub(0.8, 0.7),
                discovery_method="heuristic",
            ),
        ]
        graph = self._graph_with_nodes(nodes)
        result = CandidatePageGenerator().generate(graph)
        students = next(c for c in result if "students" in c.url)
        self.assertEqual(students.page_type, PAGE_TYPE_STUDENTS)

    def test_deduplicates_by_normalized_url(self):
        nodes = [
            GraphNode(
                node_type="lab_page",
                url="https://ada.github.io/",
                confidence=ConfidenceScore.from_stub(0.9, 0.8),
                discovery_method="heuristic",
            ),
        ]
        graph = self._graph_with_nodes(nodes)
        result = CandidatePageGenerator().generate(graph)
        urls = [c.url for c in result]
        self.assertEqual(len(urls), len(set(u.rstrip("/") for u in urls)))

    def test_lab_node_type_mapped_correctly(self):
        nodes = [
            GraphNode(
                node_type="lab_page",
                url="https://ada.github.io/lab/members/",
                confidence=ConfidenceScore.from_stub(0.9, 0.8),
                discovery_method="heuristic",
                anchor_text="Lab Members",
            ),
        ]
        graph = self._graph_with_nodes(nodes)
        result = CandidatePageGenerator().generate(graph)
        lab = next(c for c in result if "lab" in c.url)
        self.assertEqual(lab.page_type, PAGE_TYPE_MEMBERS)


class TestCandidatePageRanker(unittest.TestCase):
    def _candidate(
        self,
        url: str,
        page_type: str,
        anchor_text: str = "",
        graph_confidence: float = 0.8,
    ) -> CandidatePage:
        return CandidatePage(
            url=url,
            page_type=page_type,
            anchor_text=anchor_text,
            graph_confidence=graph_confidence,
        )

    def test_lab_page_scores_higher_than_homepage(self):
        ranker = CandidatePageRanker(enable_navigation_evidence=False)
        lab = self._candidate("https://ada.github.io/lab/", PAGE_TYPE_LAB)
        home = self._candidate("https://ada.github.io/", PAGE_TYPE_HOMEPAGE)
        ranked = ranker.rank([lab, home])
        self.assertEqual(ranked[0].page_type, PAGE_TYPE_LAB)

    def test_alumni_page_scores_higher_than_projects(self):
        ranker = CandidatePageRanker(enable_navigation_evidence=False)
        alumni = self._candidate("https://ada.github.io/alumni/", PAGE_TYPE_ALUMNI)
        proj = self._candidate("https://ada.github.io/projects/", PAGE_TYPE_PROJECTS)
        ranked = ranker.rank([alumni, proj])
        self.assertEqual(ranked[0].page_type, PAGE_TYPE_ALUMNI)

    def test_url_keyword_bonus_applied(self):
        ranker = CandidatePageRanker(enable_navigation_evidence=False)
        with_kw = self._candidate("https://ada.github.io/members/", PAGE_TYPE_PEOPLE)
        without_kw = self._candidate("https://ada.github.io/page/", PAGE_TYPE_PEOPLE)
        ranked = ranker.rank([with_kw, without_kw])
        self.assertGreater(ranked[0].score, ranked[-1].score)
        self.assertEqual(ranked[0].url, with_kw.url)

    def test_department_penalty_applied(self):
        ranker = CandidatePageRanker(enable_navigation_evidence=False)
        dept = self._candidate(
            "https://cs.example.edu/people/faculty", PAGE_TYPE_PEOPLE
        )
        lab = self._candidate("https://ada.github.io/lab/", PAGE_TYPE_LAB)
        ranked = ranker.rank([dept, lab])
        lab_result = next(c for c in ranked if "lab" in c.url)
        dept_result = next((c for c in ranked if "faculty" in c.url), None)
        self.assertGreater(lab_result.score, dept_result.score if dept_result else 0)

    def test_returns_at_most_top_n(self):
        ranker = CandidatePageRanker(enable_navigation_evidence=False)
        candidates = [
            self._candidate(f"https://ada.github.io/page{i}/", PAGE_TYPE_LAB)
            for i in range(10)
        ]
        ranked = ranker.rank(candidates, top_n=5)
        self.assertLessEqual(len(ranked), 5)

    def test_evidence_is_populated(self):
        ranker = CandidatePageRanker(enable_navigation_evidence=False)
        candidate = self._candidate(
            "https://ada.github.io/lab/members/",
            PAGE_TYPE_LAB,
            anchor_text="Lab Members",
        )
        ranked = ranker.rank([candidate])
        self.assertTrue(ranked)
        self.assertTrue(ranked[0].evidence)

    def test_below_min_score_excluded(self):
        ranker = CandidatePageRanker(enable_navigation_evidence=False)
        low = CandidatePage(
            url="https://ada.github.io/other/",
            page_type=PAGE_TYPE_OTHER,
            graph_confidence=0.0,
        )
        ranked = ranker.rank([low])
        self.assertEqual(ranked, [])

    def test_deduplicates_by_url(self):
        ranker = CandidatePageRanker(enable_navigation_evidence=False)
        c1 = self._candidate("https://ada.github.io/lab/", PAGE_TYPE_LAB)
        c2 = self._candidate("https://ada.github.io/lab/", PAGE_TYPE_LAB)
        ranked = ranker.rank([c1, c2])
        self.assertEqual(len(ranked), 1)

    def test_scores_are_capped_at_one(self):
        ranker = CandidatePageRanker(enable_navigation_evidence=False)
        candidate = self._candidate(
            "https://ada.github.io/lab/members/",
            PAGE_TYPE_LAB,
            anchor_text="lab members",
            graph_confidence=1.0,
        )
        ranked = ranker.rank([candidate])
        self.assertLessEqual(ranked[0].score, 1.0)
        self.assertGreaterEqual(ranked[0].score, 0.0)


class TestPipelineCandidateIntegration(unittest.TestCase):
    """Verify that the PR19 candidate-based pipeline integration works end-to-end."""

    @patch("research_group_agent.fetcher.HomepageFetcher.fetch")
    def test_pipeline_tracks_candidate_count(self, mock_fetch):
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
            canonical_homepage="https://example.edu/~ravi/",
            graph_nodes=_homepage_graph_with_lab_and_people().graph_nodes,
        )
        pipeline = ResearchGroupPipeline(provider=StubResearchGroupProvider())
        pipeline.analyze(_professor(graph), graph)

        self.assertTrue(pipeline.last_metrics.candidate_page_counts)
        self.assertGreater(pipeline.last_metrics.candidate_page_counts[0], 0)

    @patch("research_group_agent.fetcher.HomepageFetcher.fetch")
    def test_graph_records_candidate_pages_discovered(self, mock_fetch):
        mock_fetch.return_value = __import__(
            "homepage_agent.models", fromlist=["HomepageDocument"]
        ).HomepageDocument(
            url="https://example.edu/~ravi/people.html",
            html=MEMBER_PAGE_HTML,
            title="Netravali Research Group",
            fetch_status=FetchStatus.SUCCESS,
            final_url="https://example.edu/~ravi/people.html",
        )

        graph_hp = HomepageGraph(
            professor_name="Ravi Netravali",
            homepage_url="https://example.edu/~ravi/",
            fetch_status=FetchStatus.SUCCESS,
            canonical_homepage="https://example.edu/~ravi/",
            graph_nodes=_homepage_graph_with_lab_and_people().graph_nodes,
        )
        pipeline = ResearchGroupPipeline(provider=StubResearchGroupProvider())
        result = pipeline.analyze(_professor(graph_hp), graph_hp)

        self.assertGreater(result.candidate_pages_discovered, 0)

    def test_pipeline_version_is_pr32(self):
        graph = ResearchGroupGraphBuilder().build(
            professor_name="Test",
            professor_homepage="https://test.edu/",
            group_page=None,
            members=[],
            provider="heuristic",
        )
        self.assertEqual(graph.pipeline_version, "PR32")
        self.assertEqual(graph.schema_version, "1.7")


# ─────────────────────────────────────────────────────────────────────────────
# PR20 — PeoplePageDiscovery unit tests
# ─────────────────────────────────────────────────────────────────────────────

from research_group_agent.people_page_discovery import PeoplePageDiscovery


def _html_with_links(*links: tuple[str, str], base: str = "https://example.edu") -> str:
    """Build minimal HTML containing anchor tags for the given (anchor_text, href) pairs."""
    lis = "".join(
        f'<li><a href="{href}">{anchor}</a></li>'
        for anchor, href in links
    )
    return f"<html><body><ul>{lis}</ul></body></html>"


def _nav_html_with_links(*links: tuple[str, str], base: str = "https://example.edu") -> str:
    """Build HTML with links inside a <nav> element (tests nav-link discovery)."""
    lis = "".join(
        f'<li><a href="{href}">{anchor}</a></li>'
        for anchor, href in links
    )
    return f"<html><body><nav><ul>{lis}</ul></nav></body></html>"


class TestPeoplePageDiscovery(unittest.TestCase):
    def setUp(self):
        self.disc = PeoplePageDiscovery()
        self.base = "https://example.edu/~prof/"

    def _disc(self, html: str, already_seen: set[str] | None = None) -> list:
        return self.disc.discover(html, self.base, already_seen or set())

    # ── URL path matching ──────────────────────────────────────────────────

    def test_discovers_people_path(self):
        html = _html_with_links(("People", "https://example.edu/~prof/people"))
        results = self._disc(html)
        self.assertEqual(len(results), 1)
        self.assertIn("/people", results[0].url)

    def test_discovers_students_path(self):
        html = _html_with_links(("Students", "https://example.edu/~prof/students"))
        results = self._disc(html)
        self.assertEqual(len(results), 1)

    def test_discovers_team_path(self):
        html = _html_with_links(("Team", "https://example.edu/~prof/team"))
        results = self._disc(html)
        self.assertEqual(len(results), 1)

    def test_discovers_members_path(self):
        html = _html_with_links(("Group", "https://example.edu/~prof/members"))
        results = self._disc(html)
        self.assertEqual(len(results), 1)

    def test_discovers_personnel_path(self):
        html = _html_with_links(("Personnel", "https://example.edu/~prof/personnel"))
        results = self._disc(html)
        self.assertEqual(len(results), 1)

    def test_discovers_links_inside_nav(self):
        """Links inside <nav> (skipped by MemberPageParser) must still be found."""
        html = _nav_html_with_links(("People", "https://example.edu/~prof/people"))
        results = self._disc(html)
        self.assertEqual(len(results), 1)

    # ── Anchor text matching ───────────────────────────────────────────────

    def test_discovers_via_anchor_text_people(self):
        # URL path has no people-pattern hit so anchor text drives detection
        html = _html_with_links(("People", "https://example.edu/~prof/overview"))
        results = self._disc(html)
        self.assertEqual(len(results), 1)
        self.assertTrue(any("anchor_match" in e for e in results[0].evidence))

    def test_discovers_via_anchor_text_team(self):
        html = _html_with_links(("Our Team", "https://example.edu/~prof/xyz"))
        results = self._disc(html)
        self.assertEqual(len(results), 1)

    # ── Deduplication ─────────────────────────────────────────────────────

    def test_skips_already_seen_url(self):
        url = "https://example.edu/~prof/people"
        html = _html_with_links(("People", url))
        results = self._disc(html, already_seen={url.rstrip("/")})
        self.assertEqual(len(results), 0)

    def test_deduplicates_multiple_same_url_links(self):
        url = "https://example.edu/~prof/people"
        html = _html_with_links(("People", url), ("Lab members", url))
        results = self._disc(html)
        self.assertEqual(len(results), 1)

    def test_updates_already_seen_in_place(self):
        html = _html_with_links(("People", "https://example.edu/~prof/people"))
        already_seen: set[str] = set()
        self.disc.discover(html, self.base, already_seen)
        self.assertIn("https://example.edu/~prof/people", already_seen)

    # ── Cross-host filtering ───────────────────────────────────────────────

    def test_rejects_cross_host_link(self):
        html = _html_with_links(("People", "https://other.edu/people"))
        results = self._disc(html)
        self.assertEqual(len(results), 0)

    def test_accepts_same_host_different_path(self):
        html = _html_with_links(("Team", "https://example.edu/dept/team"))
        results = self.disc.discover(html, "https://example.edu/~prof/", set())
        self.assertEqual(len(results), 1)

    # ── Non-matching links are ignored ────────────────────────────────────

    def test_ignores_unrelated_links(self):
        html = _html_with_links(
            ("Publications", "https://example.edu/~prof/papers"),
            ("News",         "https://example.edu/~prof/news"),
            ("Home",         "https://example.edu/~prof/"),
        )
        results = self._disc(html)
        self.assertEqual(len(results), 0)

    def test_ignores_empty_html(self):
        results = self._disc("<html><body></body></html>")
        self.assertEqual(len(results), 0)

    # ── Cap enforcement ───────────────────────────────────────────────────

    def test_caps_at_max_per_page(self):
        from research_group_agent.people_page_discovery import _MAX_SECOND_HOP_PER_PAGE
        links = tuple(
            (f"People {i}", f"https://example.edu/~prof/people{i}")
            for i in range(20)
        )
        html = _html_with_links(*links)
        results = self._disc(html)
        self.assertLessEqual(len(results), _MAX_SECOND_HOP_PER_PAGE)

    # ── Source metadata ───────────────────────────────────────────────────

    def test_result_has_second_hop_source_node_type(self):
        html = _html_with_links(("People", "https://example.edu/~prof/people"))
        results = self._disc(html)
        self.assertEqual(results[0].source_node_type, "second_hop")

    def test_result_evidence_contains_match_type(self):
        html = _html_with_links(("Members", "https://example.edu/~prof/members"))
        results = self._disc(html)
        self.assertTrue(any("match" in e for e in results[0].evidence))


# ─────────────────────────────────────────────────────────────────────────────
# PR20 — Second-hop integration in pipeline
# ─────────────────────────────────────────────────────────────────────────────

# HTML for a lab homepage that has members links in navigation but no members itself
LAB_HOME_WITH_PEOPLE_NAV_HTML = """
<!DOCTYPE html>
<html>
<head><title>Smith Systems Lab</title></head>
<body>
  <nav>
    <a href="/~smith/">Home</a>
    <a href="/~smith/people">People</a>
    <a href="/~smith/publications">Publications</a>
  </nav>
  <h1>Smith Systems Lab</h1>
  <p>We do systems research.</p>
</body>
</html>
"""

# HTML for the people sub-page that actually has members
PEOPLE_SUBPAGE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Smith Systems Lab — People</title></head>
<body>
  <h1>Smith Systems Lab</h1>
  <h2>Current Members</h2>
  <ul>
    <li><a href="https://example.edu/~alice">Alice Wang</a> – PhD Student</li>
    <li><a href="https://example.edu/~bob">Bob Chen</a> – Postdoc</li>
  </ul>
</body>
</html>
"""


def _smith_homepage_graph() -> HomepageGraph:
    return HomepageGraph(
        professor_name="John Smith",
        homepage_url="https://example.edu/~smith/",
        fetch_status=FetchStatus.SUCCESS,
        canonical_homepage="https://example.edu/~smith/",
        graph_nodes=[
            GraphNode(
                node_type="lab_page",
                url="https://example.edu/~smith/",
                confidence=ConfidenceScore.from_stub(0.9, 0.8),
                discovery_method="heuristic",
                anchor_text="Lab Home",
            ),
        ],
    )


def _smith_professor(graph: HomepageGraph) -> "ProfessorProfile":
    profile = AuthorProfile(
        author=Author(pid=None, name="John Smith"),
        papers=[],
    )
    return ProfessorProfile(
        author_profile=profile,
        homepage="https://example.edu/~smith/",
        homepage_graph=graph,
        is_us=True,
    )


class TestSecondHopIntegration(unittest.TestCase):
    """Integration tests for PR20 second-hop discovery inside ResearchGroupPipeline."""

    def _make_fetch_side_effect(self, url_to_html: dict):
        """Return a side_effect callable that returns different HTML per URL."""
        from homepage_agent.models import HomepageDocument

        def _side_effect(url):
            html = url_to_html.get(url, "<html><body></body></html>")
            return HomepageDocument(
                url=url,
                html=html,
                title="",
                fetch_status=FetchStatus.SUCCESS,
                final_url=url,
            )
        return _side_effect

    @patch("research_group_agent.fetcher.HomepageFetcher.fetch")
    def test_second_hop_triggered_when_first_hop_has_zero_members(self, mock_fetch):
        """
        When the lab homepage parses successfully but yields 0 members, the
        pipeline should discover and fetch the /people sub-page.
        """
        mock_fetch.side_effect = self._make_fetch_side_effect({
            "https://example.edu/~smith/": LAB_HOME_WITH_PEOPLE_NAV_HTML,
            "https://example.edu/~smith/people": PEOPLE_SUBPAGE_HTML,
        })

        graph_hp = _smith_homepage_graph()
        pipeline = ResearchGroupPipeline(provider=StubResearchGroupProvider())
        result = pipeline.analyze(_smith_professor(graph_hp), graph_hp)

        # People sub-page should be parsed (via second-hop or PR32 lab navigation)
        self.assertIn("https://example.edu/~smith/people", result.parsed_pages)
        self.assertTrue(
            result.second_hop_pages_discovered > 0
            or result.navigation_discovery.get("labs_discovered")
            or result.member_count > 0
        )

    @patch("research_group_agent.fetcher.HomepageFetcher.fetch")
    def test_second_hop_finds_members_when_sub_page_has_them(self, mock_fetch):
        """Members discovered via second-hop are included in the final graph."""
        mock_fetch.side_effect = self._make_fetch_side_effect({
            "https://example.edu/~smith/": LAB_HOME_WITH_PEOPLE_NAV_HTML,
            "https://example.edu/~smith/people": PEOPLE_SUBPAGE_HTML,
        })

        graph_hp = _smith_homepage_graph()
        pipeline = ResearchGroupPipeline(provider=StubResearchGroupProvider())
        result = pipeline.analyze(_smith_professor(graph_hp), graph_hp)

        self.assertGreater(result.member_count, 0)
        self.assertIn("https://example.edu/~smith/people", result.parsed_pages)

    @patch("research_group_agent.fetcher.HomepageFetcher.fetch")
    def test_second_hop_not_triggered_when_first_hop_has_members(self, mock_fetch):
        """When the first-hop page already has members, no second-hop is attempted."""
        mock_fetch.return_value = __import__(
            "homepage_agent.models", fromlist=["HomepageDocument"]
        ).HomepageDocument(
            url="https://example.edu/~ravi/people.html",
            html=MEMBER_PAGE_HTML,
            title="Netravali Research Group",
            fetch_status=FetchStatus.SUCCESS,
            final_url="https://example.edu/~ravi/people.html",
        )

        graph_hp = HomepageGraph(
            professor_name="Ravi Netravali",
            homepage_url="https://example.edu/~ravi/",
            fetch_status=FetchStatus.SUCCESS,
            canonical_homepage="https://example.edu/~ravi/",
            graph_nodes=_homepage_graph_with_lab_and_people().graph_nodes,
        )
        pipeline = ResearchGroupPipeline(provider=StubResearchGroupProvider())
        result = pipeline.analyze(_professor(graph_hp), graph_hp)

        # Members found on first hop, so second-hop should not have been triggered
        self.assertGreater(result.member_count, 0)
        self.assertEqual(result.second_hop_pages_discovered, 0)

    @patch("research_group_agent.fetcher.HomepageFetcher.fetch")
    def test_second_hop_urls_not_retried(self, mock_fetch):
        """
        A URL already in the first-hop candidate set should not be fetched again
        as a second-hop page.
        """
        from homepage_agent.models import HomepageDocument

        fetched_urls: list[str] = []

        def _tracking_fetch(url):
            fetched_urls.append(url)
            html = LAB_HOME_WITH_PEOPLE_NAV_HTML if "smith" in url else "<html/>"
            return HomepageDocument(
                url=url,
                html=html,
                title="",
                fetch_status=FetchStatus.SUCCESS,
                final_url=url,
            )

        mock_fetch.side_effect = _tracking_fetch

        # Graph already includes /~smith/people as a first-hop candidate
        graph_hp = HomepageGraph(
            professor_name="John Smith",
            homepage_url="https://example.edu/~smith/",
            fetch_status=FetchStatus.SUCCESS,
            canonical_homepage="https://example.edu/~smith/",
            graph_nodes=[
                GraphNode(
                    node_type="lab_page",
                    url="https://example.edu/~smith/",
                    confidence=ConfidenceScore.from_stub(0.9, 0.8),
                    discovery_method="heuristic",
                    anchor_text="Lab Home",
                ),
                GraphNode(
                    node_type="people_page",
                    url="https://example.edu/~smith/people",
                    confidence=ConfidenceScore.from_stub(0.9, 0.8),
                    discovery_method="heuristic",
                    anchor_text="People",
                ),
            ],
        )
        pipeline = ResearchGroupPipeline(provider=StubResearchGroupProvider())
        pipeline.analyze(_smith_professor(graph_hp), graph_hp)

        # /~smith/people must appear at most once in fetched URLs
        people_fetches = [u for u in fetched_urls if "people" in u]
        self.assertLessEqual(len(people_fetches), 1)

    @patch("research_group_agent.fetcher.HomepageFetcher.fetch")
    def test_second_hop_graph_fields_in_to_dict(self, mock_fetch):
        """Serialised graph always contains second_hop_pages_discovered and _successful."""
        mock_fetch.return_value = __import__(
            "homepage_agent.models", fromlist=["HomepageDocument"]
        ).HomepageDocument(
            url="https://example.edu/~ravi/people.html",
            html=MEMBER_PAGE_HTML,
            title="Netravali Research Group",
            fetch_status=FetchStatus.SUCCESS,
            final_url="https://example.edu/~ravi/people.html",
        )

        graph_hp = HomepageGraph(
            professor_name="Ravi Netravali",
            homepage_url="https://example.edu/~ravi/",
            fetch_status=FetchStatus.SUCCESS,
            canonical_homepage="https://example.edu/~ravi/",
            graph_nodes=_homepage_graph_with_lab_and_people().graph_nodes,
        )
        pipeline = ResearchGroupPipeline(provider=StubResearchGroupProvider())
        result = pipeline.analyze(_professor(graph_hp), graph_hp)
        d = result.to_dict()

        self.assertIn("second_hop_pages_discovered", d)
        self.assertIn("second_hop_pages_successful", d)
        self.assertIsInstance(d["second_hop_pages_discovered"], int)
        self.assertIsInstance(d["second_hop_pages_successful"], int)

    @patch("research_group_agent.fetcher.HomepageFetcher.fetch")
    def test_second_hop_metrics_recorded_in_analyze_many(self, mock_fetch):
        """ExtractionRunMetrics records second-hop stats after analyze_many."""
        mock_fetch.return_value = __import__(
            "homepage_agent.models", fromlist=["HomepageDocument"]
        ).HomepageDocument(
            url="https://example.edu/~ravi/people.html",
            html=MEMBER_PAGE_HTML,
            title="Netravali Research Group",
            fetch_status=FetchStatus.SUCCESS,
            final_url="https://example.edu/~ravi/people.html",
        )

        graph_hp = HomepageGraph(
            professor_name="Ravi Netravali",
            homepage_url="https://example.edu/~ravi/",
            fetch_status=FetchStatus.SUCCESS,
            canonical_homepage="https://example.edu/~ravi/",
            graph_nodes=_homepage_graph_with_lab_and_people().graph_nodes,
        )
        professor = _professor(graph_hp)
        pipeline = ResearchGroupPipeline(provider=StubResearchGroupProvider())
        pipeline.analyze_many([professor])

        self.assertEqual(
            len(pipeline.last_metrics.second_hop_discovered_counts), 1
        )
        self.assertEqual(
            len(pipeline.last_metrics.second_hop_successful_counts), 1
        )


# ─────────────────────────────────────────────────────────────────────────────
# PR21 — HeadingCardExtractor unit tests
# ─────────────────────────────────────────────────────────────────────────────

from research_group_agent.heading_card_extractor import HeadingCardExtractor


# Bootstrap-style card layout: each member has an H3 heading with a profile
# link inside a card div, followed by a paragraph with the role.
BOOTSTRAP_CARD_HTML = """
<!DOCTYPE html>
<html>
<head><title>RISE Lab People</title></head>
<body>
  <h1>RISE Lab</h1>
  <h2>Current Members</h2>
  <div class="row">
    <div class="card">
      <h3><a href="https://example.edu/~alice">Alice Wang</a></h3>
      <p>PhD Student</p>
    </div>
    <div class="card">
      <h3><a href="https://example.edu/~bob">Bob Chen</a></h3>
      <p>Postdoc</p>
    </div>
    <div class="card">
      <h3><a href="https://example.edu/~carol">Carol Davis</a></h3>
      <p>Research Scientist</p>
    </div>
  </div>
</body>
</html>
"""

# Consecutive H3 headings with role text — no Bootstrap structure, just
# headings and paragraphs inside a member section.
H34_IN_MEMBER_SECTION_HTML = """
<!DOCTYPE html>
<html>
<head><title>Sky Computing Lab</title></head>
<body>
  <h1>Sky Computing Lab</h1>
  <h2>PhD Students</h2>
  <h3><a href="https://example.edu/~dan">Dan Kim</a></h3>
  <p>PhD Student — 5th year</p>
  <h3><a href="https://example.edu/~eva">Eva Martinez</a></h3>
  <p>PhD Student — 3rd year</p>
  <h3><a href="https://example.edu/~frank">Frank Liu</a></h3>
  <p>PhD Student — 2nd year</p>
  <h3><a href="https://example.edu/~grace">Grace Park</a></h3>
  <p>Visiting Student</p>
</body>
</html>
"""

# Standalone heading cards (no parent section heading) — triggers standalone
# mode because ≥3 headings have profile links.
STANDALONE_H3_CARDS_HTML = """
<!DOCTYPE html>
<html>
<head><title>CSL Illinois People</title></head>
<body>
  <h1>CSL Illinois</h1>
  <h3><a href="https://csl.illinois.edu/~mike">Mike Johnson</a></h3>
  <p>Associate Professor</p>
  <h3><a href="https://csl.illinois.edu/~nina">Nina Patel</a></h3>
  <p>PhD Student</p>
  <h3><a href="https://csl.illinois.edu/~omar">Omar Hassan</a></h3>
  <p>Postdoc</p>
  <h3><a href="https://csl.illinois.edu/~priya">Priya Singh</a></h3>
  <p>Research Staff</p>
</body>
</html>
"""

# Only 2 standalone heading cards — below threshold; should NOT trigger.
BELOW_THRESHOLD_H3_HTML = """
<!DOCTYPE html>
<html>
<head><title>Some Lab</title></head>
<body>
  <h1>Some Lab</h1>
  <h3><a href="https://example.edu/~anna">Anna Brown</a></h3>
  <p>PhD Student</p>
  <h3><a href="https://example.edu/~ben">Ben White</a></h3>
  <p>Postdoc</p>
</body>
</html>
"""

# Documentation page with section-like H3 headings — should NOT produce entries.
DOCS_PAGE_H3_HTML = """
<!DOCTYPE html>
<html>
<head><title>Research Overview</title></head>
<body>
  <h1>Research Areas</h1>
  <h3>Distributed Systems</h3>
  <p>We study distributed computing at scale.</p>
  <h3>Machine Learning</h3>
  <p>We apply ML to infrastructure problems.</p>
  <h3>Cloud Computing</h3>
  <p>We build cloud platforms.</p>
  <h3>Network Security</h3>
  <p>We secure distributed systems.</p>
</body>
</html>
"""

# No-regression: standard UL/LI layout should still work when heading cards
# are also present (heading card extractor must not interfere).
UL_LI_WITH_HEADING_CARDS_HTML = """
<!DOCTYPE html>
<html>
<head><title>Mixed Lab Page</title></head>
<body>
  <h2>Current Members</h2>
  <ul>
    <li><a href="https://example.edu/~jw">Jian Wang</a> – PhD Student</li>
    <li><a href="https://example.edu/~ac">Alice Chen</a> – Postdoc</li>
  </ul>
  <h2>Additional Members</h2>
  <h3><a href="https://example.edu/~bs">Bob Smith</a></h3>
  <p>Research Scientist</p>
  <h3><a href="https://example.edu/~cd">Carol Davis</a></h3>
  <p>PhD Student</p>
  <h3><a href="https://example.edu/~ef">Eve Foster</a></h3>
  <p>Postdoc</p>
</body>
</html>
"""


class TestHeadingCardExtractor(unittest.TestCase):
    """PR21: tests for HeadingCardExtractor — heading-based member card layouts."""

    def _extract(self, html: str, base: str = "https://example.edu/") -> list:
        extractor = HeadingCardExtractor()
        already_seen: set[str] = set()
        return extractor.extract(html, base, already_seen)

    # ── Bootstrap card layout ─────────────────────────────────────────────

    def test_bootstrap_card_extracts_all_members(self):
        entries = self._extract(BOOTSTRAP_CARD_HTML)
        names = {e.name for e in entries}
        self.assertIn("Alice Wang", names)
        self.assertIn("Bob Chen", names)
        self.assertIn("Carol Davis", names)

    def test_bootstrap_card_profile_urls_resolved(self):
        entries = self._extract(BOOTSTRAP_CARD_HTML)
        alice = next(e for e in entries if e.name == "Alice Wang")
        self.assertIsNotNone(alice.profile_url)
        self.assertIn("alice", alice.profile_url)

    def test_bootstrap_card_role_hints_attached(self):
        entries = self._extract(BOOTSTRAP_CARD_HTML)
        bob = next(e for e in entries if e.name == "Bob Chen")
        self.assertIsNotNone(bob.role_hint)

    def test_bootstrap_card_entries_marked_in_member_section(self):
        entries = self._extract(BOOTSTRAP_CARD_HTML)
        self.assertTrue(all(e.in_member_section for e in entries))

    # ── Consecutive H3/H4 inside a member section ─────────────────────────

    def test_h34_in_member_section_all_extracted(self):
        entries = self._extract(H34_IN_MEMBER_SECTION_HTML)
        names = {e.name for e in entries}
        self.assertIn("Dan Kim", names)
        self.assertIn("Eva Martinez", names)
        self.assertIn("Frank Liu", names)
        self.assertIn("Grace Park", names)

    def test_h34_in_member_section_role_hints_present(self):
        entries = self._extract(H34_IN_MEMBER_SECTION_HTML)
        self.assertTrue(any(e.role_hint for e in entries))

    # ── Standalone H3 cards (threshold activation) ────────────────────────

    def test_standalone_h3_cards_extracted_above_threshold(self):
        entries = self._extract(STANDALONE_H3_CARDS_HTML)
        names = {e.name for e in entries}
        self.assertIn("Mike Johnson", names)
        self.assertIn("Nina Patel", names)
        self.assertIn("Omar Hassan", names)
        self.assertIn("Priya Singh", names)

    def test_standalone_h3_below_threshold_not_extracted(self):
        entries = self._extract(BELOW_THRESHOLD_H3_HTML)
        self.assertEqual(len(entries), 0)

    # ── False positive prevention ─────────────────────────────────────────

    def test_docs_page_section_headings_not_extracted(self):
        """H3 headings like 'Distributed Systems' must not produce member entries."""
        entries = self._extract(DOCS_PAGE_H3_HTML)
        names = {e.name for e in entries}
        self.assertNotIn("Distributed Systems", names)
        self.assertNotIn("Machine Learning", names)
        self.assertNotIn("Cloud Computing", names)
        self.assertNotIn("Network Security", names)

    def test_docs_page_produces_no_entries(self):
        entries = self._extract(DOCS_PAGE_H3_HTML)
        self.assertEqual(len(entries), 0)

    # ── Deduplication ─────────────────────────────────────────────────────

    def test_already_seen_names_not_duplicated(self):
        extractor = HeadingCardExtractor()
        already_seen = {"alice wang", "bob chen"}
        entries = extractor.extract(
            BOOTSTRAP_CARD_HTML, "https://example.edu/", already_seen
        )
        names = {e.name for e in entries}
        self.assertNotIn("Alice Wang", names)
        self.assertNotIn("Bob Chen", names)
        self.assertIn("Carol Davis", names)

    def test_already_seen_updated_in_place(self):
        extractor = HeadingCardExtractor()
        already_seen: set[str] = set()
        extractor.extract(BOOTSTRAP_CARD_HTML, "https://example.edu/", already_seen)
        self.assertIn("alice wang", already_seen)
        self.assertIn("bob chen", already_seen)


class TestMemberPageParserPR21Regression(unittest.TestCase):
    """Verify that PR21 (heading card extractor) does not break existing UL/LI parsing."""

    def test_ul_li_layout_still_works(self):
        """Standard list-based layout must not be affected by heading card extraction."""
        parsed = MemberPageParser().parse(
            MEMBER_PAGE_HTML, base_url="https://example.edu/"
        )
        names = {e.name for e in parsed.entries}
        self.assertIn("Jian Wang", names)
        self.assertIn("Alice Chen", names)

    def test_heading_card_count_zero_for_list_only_page(self):
        """heading_card_count must be 0 when no heading cards are found."""
        parsed = MemberPageParser().parse(
            MEMBER_PAGE_HTML, base_url="https://example.edu/"
        )
        self.assertEqual(parsed.heading_card_count, 0)

    def test_mixed_layout_combines_ul_and_heading_cards(self):
        """UL/LI entries and heading card entries should both be present."""
        parsed = MemberPageParser().parse(
            UL_LI_WITH_HEADING_CARDS_HTML, base_url="https://example.edu/"
        )
        names = {e.name for e in parsed.entries}
        # UL/LI members
        self.assertIn("Jian Wang", names)
        self.assertIn("Alice Chen", names)
        # Heading card members
        self.assertIn("Bob Smith", names)
        self.assertIn("Carol Davis", names)
        self.assertIn("Eve Foster", names)

    def test_heading_card_count_reflects_new_entries(self):
        """heading_card_count should equal number of newly extracted heading cards."""
        parsed = MemberPageParser().parse(
            UL_LI_WITH_HEADING_CARDS_HTML, base_url="https://example.edu/"
        )
        # 3 heading cards should have been added (Bob Smith, Carol Davis, Eve Foster)
        self.assertGreater(parsed.heading_card_count, 0)

    def test_bootstrap_cards_via_main_parser(self):
        """Full MemberPageParser pipeline must extract Bootstrap card members."""
        parsed = MemberPageParser().parse(
            BOOTSTRAP_CARD_HTML, base_url="https://rise.cs.berkeley.edu/people/"
        )
        names = {e.name for e in parsed.entries}
        self.assertIn("Alice Wang", names)
        self.assertIn("Bob Chen", names)
        self.assertIn("Carol Davis", names)
        self.assertGreater(parsed.heading_card_count, 0)


# ─────────────────────────────────────────────────────────────────────────────
# PR23 — ParagraphMemberExtractor unit tests
# ─────────────────────────────────────────────────────────────────────────────

from research_group_agent.paragraph_member_extractor import ParagraphMemberExtractor


SIMPLE_PARAGRAPH_MEMBERS_HTML = """
<!DOCTYPE html>
<html>
<head><title>Legacy Lab Page</title></head>
<body>
  <p>John Smith
PhD Student</p>
  <p>Jane Doe
Postdoctoral Researcher</p>
  <p>Alice Zhang (PhD Student)</p>
</body>
</html>
"""

PARAGRAPH_WITH_HOMEPAGE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Tianyin Xu Group</title></head>
<body>
  <p><a href="https://yulistic.github.io">Jongyul Kim</a>, Postdoc Research Fellow (Fall 2023 - now)</p>
  <p><a href="https://jiyuan.is">Jiyuan Zhang</a>, PhD Candidate (Fall 2022 - now)</p>
  <p><a href="https://cathy-cai.page/">Cathy Cai</a>, PhD Student (Fall 2024 - now)</p>
  <p><a href="https://hacksonclark.github.io">Jackson Clark</a>, PhD Candidate (Fall 2024 - now)</p>
</body>
</html>
"""

PARAGRAPH_IN_MEMBER_SECTION_HTML = """
<!DOCTYPE html>
<html>
<head><title>Sectioned Lab Page</title></head>
<body>
  <h2>Current PhD Students</h2>
  <p>Dan Kim
PhD Student</p>
  <p>Eva Martinez
PhD Student</p>
</body>
</html>
"""

UL_LI_WITH_PARAGRAPH_MEMBERS_HTML = """
<!DOCTYPE html>
<html>
<head><title>Mixed Layout Lab</title></head>
<body>
  <h2>Current Members</h2>
  <ul>
    <li><a href="https://example.edu/~jw">Jian Wang</a> – PhD Student</li>
    <li><a href="https://example.edu/~ac">Alice Chen</a> – Postdoc</li>
  </ul>
  <h2>Research Overview</h2>
  <p>We study distributed systems at scale.</p>
  <p><a href="https://example.edu/~bs">Bob Smith</a>, Research Scientist</p>
  <p><a href="https://example.edu/~cd">Carol Davis</a>, PhD Student</p>
  <p><a href="https://example.edu/~ef">Eve Foster</a>, Postdoc</p>
</body>
</html>
"""

PUBLICATION_PARAGRAPHS_HTML = """
<!DOCTYPE html>
<html>
<head><title>Publications Page</title></head>
<body>
  <h2>Publications</h2>
  <p>2025 Best Paper Award at ASPLOS'25 (cxlfork)</p>
  <p>Yan Sun, Jongyul Kim, Douglas Yu, Jiyuan Zhang, Siyuan Chai, Michael Jaemin Kim. M5: Mastering page migration. ASPLOS 2025.</p>
  <p>The Morning Paper's coverage of PCheck (article)</p>
  <p><a href="https://example.edu/~alice">Alice Wang</a>, PhD Student</p>
</body>
</html>
"""

LONG_PARAGRAPH_HTML = """
<!DOCTYPE html>
<html>
<head><title>Long Text Page</title></head>
<body>
  <p>""" + ("Alice Wang, PhD Student. " * 30) + """</p>
  <p><a href="https://example.edu/~bob">Bob Chen</a>, Postdoc</p>
  <p><a href="https://example.edu/~carol">Carol Davis</a>, PhD Student</p>
  <p><a href="https://example.edu/~dan">Dan Kim</a>, Research Scientist</p>
</body>
</html>
"""

BELOW_THRESHOLD_PARAGRAPH_HTML = """
<!DOCTYPE html>
<html>
<head><title>Small Page</title></head>
<body>
  <p><a href="https://example.edu/~anna">Anna Brown</a>, PhD Student</p>
  <p><a href="https://example.edu/~ben">Ben White</a>, Postdoc</p>
</body>
</html>
"""


class TestParagraphMemberExtractor(unittest.TestCase):
    """PR23: tests for ParagraphMemberExtractor — legacy paragraph layouts."""

    def _extract(self, html: str, base: str = "https://example.edu/") -> list:
        extractor = ParagraphMemberExtractor()
        already_seen: set[str] = set()
        return extractor.extract(html, base, already_seen)

    def test_simple_paragraph_members_extracted(self):
        entries = self._extract(SIMPLE_PARAGRAPH_MEMBERS_HTML)
        names = {e.name for e in entries}
        self.assertIn("John Smith", names)
        self.assertIn("Jane Doe", names)
        self.assertIn("Alice Zhang", names)

    def test_simple_paragraph_role_hints_present(self):
        entries = self._extract(SIMPLE_PARAGRAPH_MEMBERS_HTML)
        john = next(e for e in entries if e.name == "John Smith")
        self.assertIsNotNone(john.role_hint)
        self.assertIn("phd", john.role_hint.lower())

    def test_paragraph_with_homepage_link_resolves_url(self):
        entries = self._extract(PARAGRAPH_WITH_HOMEPAGE_HTML, "https://tianyin.github.io/")
        jongyul = next(e for e in entries if e.name == "Jongyul Kim")
        self.assertIsNotNone(jongyul.profile_url)
        self.assertIn("yulistic", jongyul.profile_url)

    def test_multiple_consecutive_members_extracted(self):
        entries = self._extract(PARAGRAPH_WITH_HOMEPAGE_HTML)
        self.assertGreaterEqual(len(entries), 4)

    def test_in_member_section_extracts_below_standalone_threshold(self):
        entries = self._extract(PARAGRAPH_IN_MEMBER_SECTION_HTML)
        names = {e.name for e in entries}
        self.assertIn("Dan Kim", names)
        self.assertIn("Eva Martinez", names)

    def test_publication_paragraphs_not_extracted(self):
        entries = self._extract(PUBLICATION_PARAGRAPHS_HTML)
        names = {e.name for e in entries}
        self.assertNotIn("Yan Sun", names)
        self.assertNotIn("Alice Wang", names)

    def test_long_paragraph_ignored(self):
        entries = self._extract(LONG_PARAGRAPH_HTML)
        names = {e.name for e in entries}
        self.assertNotIn("Alice Wang", names)
        self.assertIn("Bob Chen", names)

    def test_below_threshold_standalone_not_extracted(self):
        entries = self._extract(BELOW_THRESHOLD_PARAGRAPH_HTML)
        self.assertEqual(len(entries), 0)

    def test_entries_marked_in_member_section(self):
        entries = self._extract(SIMPLE_PARAGRAPH_MEMBERS_HTML)
        self.assertTrue(all(e.in_member_section for e in entries))
        self.assertTrue(all(e.section_name == "paragraph" for e in entries))

    def test_already_seen_names_not_duplicated(self):
        extractor = ParagraphMemberExtractor()
        already_seen = {"john smith", "jane doe"}
        entries = extractor.extract(
            SIMPLE_PARAGRAPH_MEMBERS_HTML, "https://example.edu/", already_seen
        )
        names = {e.name for e in entries}
        self.assertNotIn("John Smith", names)
        self.assertNotIn("Jane Doe", names)
        self.assertIn("Alice Zhang", names)


class TestMemberPageParserPR23Regression(unittest.TestCase):
    """Verify that PR23 (paragraph extractor) does not break existing parsing."""

    def test_ul_li_layout_still_works(self):
        parsed = MemberPageParser().parse(
            MEMBER_PAGE_HTML, base_url="https://example.edu/"
        )
        names = {e.name for e in parsed.entries}
        self.assertIn("Jian Wang", names)
        self.assertIn("Alice Chen", names)

    def test_heading_card_count_zero_for_list_only_page(self):
        parsed = MemberPageParser().parse(
            MEMBER_PAGE_HTML, base_url="https://example.edu/"
        )
        self.assertEqual(parsed.heading_card_count, 0)

    def test_paragraph_member_count_zero_for_list_only_page(self):
        parsed = MemberPageParser().parse(
            MEMBER_PAGE_HTML, base_url="https://example.edu/"
        )
        self.assertEqual(parsed.paragraph_member_count, 0)

    def test_mixed_layout_combines_ul_and_paragraph_members(self):
        parsed = MemberPageParser().parse(
            UL_LI_WITH_PARAGRAPH_MEMBERS_HTML, base_url="https://example.edu/"
        )
        names = {e.name for e in parsed.entries}
        self.assertIn("Jian Wang", names)
        self.assertIn("Alice Chen", names)
        self.assertIn("Bob Smith", names)
        self.assertIn("Carol Davis", names)
        self.assertIn("Eve Foster", names)
        self.assertGreater(parsed.paragraph_member_count, 0)

    def test_bootstrap_cards_via_main_parser_still_work(self):
        parsed = MemberPageParser().parse(
            BOOTSTRAP_CARD_HTML, base_url="https://rise.cs.berkeley.edu/people/"
        )
        names = {e.name for e in parsed.entries}
        self.assertIn("Alice Wang", names)
        self.assertIn("Bob Chen", names)
        self.assertIn("Carol Davis", names)
        self.assertGreater(parsed.heading_card_count, 0)

    def test_ul_li_with_heading_cards_still_works(self):
        parsed = MemberPageParser().parse(
            UL_LI_WITH_HEADING_CARDS_HTML, base_url="https://example.edu/"
        )
        names = {e.name for e in parsed.entries}
        self.assertIn("Jian Wang", names)
        self.assertIn("Bob Smith", names)
        self.assertGreater(parsed.heading_card_count, 0)


if __name__ == "__main__":
    unittest.main()
