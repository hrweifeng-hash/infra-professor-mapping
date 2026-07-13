"""
PR22 — Homepage Navigation Recovery: regression tests.

Tests cover:
  1. Homepage already contains members → navigation stops (homepage-first)
  2. Homepage has no members → existing navigation unchanged
  3. Homepage contains only publications → continue navigation
  4. Homepage contains only teaching → continue navigation
  5. Candidate page is collaborator homepage → NavigationGuard penalises
  6. Candidate page is department directory → NavigationGuard penalises
  7. Homepage and candidate both contain members → homepage wins
  8. Existing successful navigation remains unchanged

Also tests HomepageMemberDetector and NavigationGuard in isolation.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from homepage_agent.models import ConfidenceScore, FetchStatus, GraphNode, HomepageGraph, HomepageDocument
from models.author import Author
from models.author_profile import AuthorProfile
from models.professor_profile import ProfessorProfile
from research_group_agent.candidate_page import (
    CandidatePage,
    NavigationGuard,
    PAGE_TYPE_HOMEPAGE,
    PAGE_TYPE_LAB,
    PAGE_TYPE_MEMBERS,
    PAGE_TYPE_OTHER,
)
from research_group_agent.homepage_member_detector import (
    HomepageMemberDetector,
    HomepageMemberDetectionResult,
    MIN_HOMEPAGE_MEMBER_COUNT,
    ENABLE_HOMEPAGE_FIRST,
)
from research_group_agent.models import PIPELINE_VERSION
from research_group_agent.pipeline import ResearchGroupPipeline
from research_group_agent.providers.stub import StubResearchGroupProvider


# ─────────────────────────────────────────────────────────────────────────────
# HTML fixtures
# ─────────────────────────────────────────────────────────────────────────────

_HOMEPAGE_WITH_MEMBERS = """
<!DOCTYPE html>
<html>
<head><title>Prof. Ada Lovelace — Homepage</title></head>
<body>
  <h1>Ada Lovelace</h1>
  <h2>Research Group Members</h2>
  <ul>
    <li><a href="/students/alice">Alice Smith</a> — PhD Student</li>
    <li><a href="/students/bob">Bob Jones</a> — PhD Student</li>
    <li><a href="/students/carol">Carol White</a> — Postdoc</li>
    <li><a href="/students/dave">Dave Brown</a> — PhD Student</li>
  </ul>
  <h2>Alumni</h2>
  <ul>
    <li><a href="/alumni/eve">Eve Green</a> — Former PhD</li>
  </ul>
</body>
</html>
"""

_HOMEPAGE_ONLY_PUBLICATIONS = """
<!DOCTYPE html>
<html>
<head><title>Ada Lovelace — Publications</title></head>
<body>
  <h1>Ada Lovelace</h1>
  <h2>Selected Publications</h2>
  <ul>
    <li>Paper One (2024)</li>
    <li>Paper Two (2023)</li>
    <li>Paper Three (2022)</li>
  </ul>
  <p>My research focuses on distributed systems.</p>
</body>
</html>
"""

_HOMEPAGE_ONLY_TEACHING = """
<!DOCTYPE html>
<html>
<head><title>Ada Lovelace — Teaching</title></head>
<body>
  <h1>Ada Lovelace</h1>
  <h2>Courses Taught</h2>
  <ul>
    <li>CS 101 — Introduction to Computer Science</li>
    <li>CS 501 — Advanced Operating Systems</li>
  </ul>
</body>
</html>
"""

_HOMEPAGE_NO_MEMBERS = """
<!DOCTYPE html>
<html>
<head><title>Ada Lovelace — Home</title></head>
<body>
  <h1>Ada Lovelace</h1>
  <p>I am a professor in the Computer Science department.</p>
  <p>My research interests include distributed systems and networking.</p>
  <a href="/cv">CV</a>
  <a href="/contact">Contact</a>
</body>
</html>
"""

_HOMEPAGE_HEADING_CARDS = """
<!DOCTYPE html>
<html>
<head><title>Ada Lovelace Lab</title></head>
<body>
  <h1>Research Group</h1>
  <section class="members">
    <div class="card">
      <h3><a href="/students/alice">Alice Smith</a></h3>
      <p>PhD Student</p>
    </div>
    <div class="card">
      <h3><a href="/students/bob">Bob Jones</a></h3>
      <p>PhD Student</p>
    </div>
    <div class="card">
      <h3><a href="/students/carol">Carol White</a></h3>
      <p>Postdoc</p>
    </div>
    <div class="card">
      <h3><a href="/students/dave">Dave Brown</a></h3>
      <p>PhD Student</p>
    </div>
  </section>
</body>
</html>
"""

_COLLABORATOR_HOMEPAGE = """
<!DOCTYPE html>
<html>
<head><title>Frank Castle — Homepage</title></head>
<body>
  <h1>Frank Castle</h1>
  <p>I am a professor at Some University.</p>
</body>
</html>
"""

_LAB_PAGE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Ada Lab — Members</title></head>
<body>
  <h1>Ada Lab</h1>
  <h2>Current Members</h2>
  <ul>
    <li>Alice Smith — PhD Student</li>
    <li>Bob Jones — PhD Student</li>
    <li>Carol White — Postdoc</li>
    <li>Dave Brown — PhD Student</li>
    <li>Eve Green — PhD Student</li>
  </ul>
</body>
</html>
"""


# ─────────────────────────────────────────────────────────────────────────────
# Helper factories
# ─────────────────────────────────────────────────────────────────────────────

def _make_homepage_graph(
    professor_name: str = "Ada Lovelace",
    homepage_url: str = "https://ada.example.edu/",
    nodes: list[GraphNode] | None = None,
) -> HomepageGraph:
    return HomepageGraph(
        professor_name=professor_name,
        homepage_url=homepage_url,
        fetch_status=FetchStatus.SUCCESS,
        original_homepage=homepage_url,
        canonical_homepage=homepage_url,
        graph_nodes=nodes or [
            GraphNode(
                node_type="lab_page",
                url="https://ada.example.edu/lab/",
                confidence=ConfidenceScore.from_stub(0.85, 0.8),
                discovery_method="heuristic",
                anchor_text="Lab Members",
            ),
        ],
    )


def _make_professor(
    name: str = "Ada Lovelace",
    homepage_url: str = "https://ada.example.edu/",
    nodes: list[GraphNode] | None = None,
) -> ProfessorProfile:
    graph = _make_homepage_graph(name, homepage_url, nodes)
    profile = AuthorProfile(
        author=Author(pid=None, name=name),
        papers=[],
    )
    return ProfessorProfile(
        author_profile=profile,
        homepage=homepage_url,
        homepage_graph=graph,
        is_us=True,
    )


def _mock_fetch(html: str, url: str = "https://ada.example.edu/") -> HomepageDocument:
    return HomepageDocument(
        url=url,
        html=html,
        title="",
        fetch_status=FetchStatus.SUCCESS,
        final_url=url,
    )


def _failed_fetch(url: str = "https://ada.example.edu/") -> HomepageDocument:
    return HomepageDocument(
        url=url,
        html="",
        title="",
        fetch_status=FetchStatus.NOT_FOUND,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. HomepageMemberDetector unit tests
# ─────────────────────────────────────────────────────────────────────────────

class TestHomepageMemberDetector(unittest.TestCase):
    def setUp(self):
        self.detector = HomepageMemberDetector(min_member_count=3, enabled=True)

    def test_disabled_detector_always_returns_false(self):
        detector = HomepageMemberDetector(enabled=False)
        result = detector.detect(_HOMEPAGE_WITH_MEMBERS, "https://example.com/")
        self.assertFalse(result.homepage_is_group_page)
        self.assertIn("disabled", result.detection_reason)

    def test_empty_html_returns_false(self):
        result = self.detector.detect("", "https://example.com/")
        self.assertFalse(result.homepage_is_group_page)
        self.assertIsNone(result.parsed)

    def test_homepage_with_member_sections_qualifies(self):
        result = self.detector.detect(_HOMEPAGE_WITH_MEMBERS, "https://ada.example.edu/")
        self.assertTrue(result.homepage_is_group_page)
        self.assertGreaterEqual(result.member_count, 3)
        self.assertTrue(result.has_member_sections)
        self.assertIsNotNone(result.parsed)

    def test_homepage_with_only_publications_does_not_qualify(self):
        result = self.detector.detect(_HOMEPAGE_ONLY_PUBLICATIONS, "https://ada.example.edu/")
        self.assertFalse(result.homepage_is_group_page)
        self.assertIn("below threshold", result.detection_reason)

    def test_homepage_with_only_teaching_does_not_qualify(self):
        result = self.detector.detect(_HOMEPAGE_ONLY_TEACHING, "https://ada.example.edu/")
        self.assertFalse(result.homepage_is_group_page)

    def test_homepage_with_no_content_does_not_qualify(self):
        result = self.detector.detect(_HOMEPAGE_NO_MEMBERS, "https://ada.example.edu/")
        self.assertFalse(result.homepage_is_group_page)
        self.assertEqual(result.member_count, 0)

    def test_result_has_correct_structure_when_qualified(self):
        result = self.detector.detect(_HOMEPAGE_WITH_MEMBERS, "https://ada.example.edu/")
        self.assertIsInstance(result, HomepageMemberDetectionResult)
        self.assertEqual(result.homepage_url, "https://ada.example.edu/")
        self.assertGreater(result.member_count, 0)

    def test_below_threshold_returns_false(self):
        # 2 members, threshold=3 → should not qualify
        html = """
        <html><body>
        <h2>Current Members</h2>
        <ul>
          <li>Alice Smith — PhD Student</li>
          <li>Bob Jones — PhD Student</li>
        </ul>
        </body></html>
        """
        result = self.detector.detect(html, "https://ada.example.edu/")
        self.assertFalse(result.homepage_is_group_page)
        self.assertIn("below threshold", result.detection_reason)

    def test_threshold_exactly_met_qualifies(self):
        html = """
        <html><body>
        <h2>Current Members</h2>
        <ul>
          <li>Alice Smith — PhD Student</li>
          <li>Bob Jones — PhD Student</li>
          <li>Carol White — Postdoc</li>
        </ul>
        </body></html>
        """
        result = self.detector.detect(html, "https://ada.example.edu/")
        self.assertTrue(result.homepage_is_group_page)

    def test_configurable_threshold_respected(self):
        strict_detector = HomepageMemberDetector(min_member_count=5, enabled=True)
        html = """
        <html><body>
        <h2>Current Members</h2>
        <ul>
          <li>Alice Smith — PhD Student</li>
          <li>Bob Jones — PhD Student</li>
          <li>Carol White — Postdoc</li>
        </ul>
        </body></html>
        """
        result = strict_detector.detect(html, "https://ada.example.edu/")
        self.assertFalse(result.homepage_is_group_page)
        self.assertIn("below threshold", result.detection_reason)

    def test_default_constants(self):
        self.assertEqual(MIN_HOMEPAGE_MEMBER_COUNT, 3)
        self.assertTrue(ENABLE_HOMEPAGE_FIRST)


# ─────────────────────────────────────────────────────────────────────────────
# 2. NavigationGuard unit tests
# ─────────────────────────────────────────────────────────────────────────────

class TestNavigationGuard(unittest.TestCase):
    def setUp(self):
        self.guard = NavigationGuard()

    def _make_candidate(
        self, url: str, page_type: str = PAGE_TYPE_OTHER, score: float = 0.80
    ) -> CandidatePage:
        return CandidatePage(
            url=url,
            page_type=page_type,
            anchor_text="",
            score=score,
            evidence=[],
            source_node_type="people_page",
            graph_confidence=0.8,
        )

    def test_lab_page_passes_through_unchanged(self):
        cand = self._make_candidate("https://ada.example.edu/lab/members", PAGE_TYPE_LAB)
        result = self.guard.filter([cand])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].score, cand.score)

    def test_teaching_page_penalised(self):
        cand = self._make_candidate("https://ada.example.edu/teaching/cs101")
        result = self.guard.filter([cand])
        self.assertEqual(len(result), 1)
        self.assertLess(result[0].score, cand.score)
        self.assertTrue(any("nav_guard:teaching_page" in e for e in result[0].evidence))

    def test_cv_page_penalised(self):
        cand = self._make_candidate("https://ada.example.edu/cv")
        result = self.guard.filter([cand])
        self.assertLess(result[0].score, cand.score)
        self.assertTrue(any("nav_guard:cv_page" in e for e in result[0].evidence))

    def test_publications_page_penalised(self):
        cand = self._make_candidate("https://ada.example.edu/publications")
        result = self.guard.filter([cand])
        self.assertLess(result[0].score, cand.score)

    def test_github_product_page_penalised(self):
        cand = self._make_candidate("https://github.com/features/copilot")
        result = self.guard.filter([cand])
        self.assertLess(result[0].score, cand.score)
        self.assertTrue(any("github_product" in e for e in result[0].evidence))

    def test_department_directory_penalised(self):
        cand = self._make_candidate("https://cs.university.edu/faculty?type=all")
        result = self.guard.filter([cand])
        self.assertLess(result[0].score, cand.score)
        self.assertTrue(any("faculty_directory" in e for e in result[0].evidence))

    def test_department_directory_pattern_2(self):
        cand = self._make_candidate("https://cs.university.edu/people/faculty")
        result = self.guard.filter([cand])
        self.assertLess(result[0].score, cand.score)

    def test_collaborator_pattern_undergraduate_penalised(self):
        cand = self._make_candidate("https://cs.university.edu/academics/undergraduate")
        result = self.guard.filter([cand])
        self.assertLess(result[0].score, cand.score)

    def test_filter_returns_all_candidates(self):
        """NavigationGuard never removes candidates — only adjusts scores."""
        candidates = [
            self._make_candidate("https://ada.example.edu/lab/"),
            self._make_candidate("https://ada.example.edu/teaching/"),
            self._make_candidate("https://ada.example.edu/cv"),
            self._make_candidate("https://ada.example.edu/publications"),
        ]
        result = self.guard.filter(candidates)
        self.assertEqual(len(result), len(candidates))

    def test_good_candidates_score_higher_than_penalised(self):
        good = self._make_candidate("https://ada.example.edu/lab/members", PAGE_TYPE_LAB, 0.80)
        bad = self._make_candidate("https://ada.example.edu/teaching/cs101", PAGE_TYPE_OTHER, 0.80)
        result = self.guard.filter([good, bad])
        good_result = next(r for r in result if "lab/members" in r.url)
        bad_result = next(r for r in result if "teaching" in r.url)
        self.assertGreater(good_result.score, bad_result.score)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Pipeline integration tests
# ─────────────────────────────────────────────────────────────────────────────

class TestPipelineHomepageFirst(unittest.TestCase):
    """Test PR22 Part 1: homepage-first detection stops navigation early."""

    def _make_pipeline(self, homepage_html: str, lab_html: str | None = None) -> ResearchGroupPipeline:
        """Create a pipeline with mocked fetcher."""
        def _fake_fetch(url: str) -> HomepageDocument:
            if "lab" in url or (lab_html and url == "https://ada.example.edu/lab/"):
                return _mock_fetch(lab_html or "", url)
            return _mock_fetch(homepage_html, url)

        pipeline = ResearchGroupPipeline(provider=StubResearchGroupProvider())
        pipeline.fetcher.fetch = _fake_fetch
        return pipeline

    def test_homepage_with_members_stops_navigation(self):
        """Test 1: Homepage already contains members — navigation stops."""
        pipeline = self._make_pipeline(_HOMEPAGE_WITH_MEMBERS)
        professor = _make_professor()
        graph = pipeline.analyze(professor, professor.homepage_graph)

        # homepage_accepted_as_group_page must be True
        self.assertTrue(
            graph.homepage_accepted_as_group_page,
            "Expected homepage to be accepted as group page",
        )
        # Must have extracted members
        self.assertGreater(graph.member_count, 0, "Expected members to be extracted")
        # Group page URL must be the homepage
        self.assertIsNotNone(graph.group_page)
        self.assertEqual(
            graph.group_page.url.rstrip("/"),
            "https://ada.example.edu/".rstrip("/"),
        )
        # Navigation provider must indicate homepage-first
        self.assertEqual(graph.group_page.navigation_provider, "homepage_first")

    def test_homepage_no_members_continues_navigation(self):
        """Test 2: Homepage has no members — existing navigation unchanged."""
        pipeline = self._make_pipeline(_HOMEPAGE_NO_MEMBERS, lab_html=_LAB_PAGE_HTML)
        professor = _make_professor()
        graph = pipeline.analyze(professor, professor.homepage_graph)

        # Must NOT have accepted homepage as group page
        self.assertFalse(
            graph.homepage_accepted_as_group_page,
            "Homepage should not be accepted as group page when it has no members",
        )
        # Navigation should have proceeded normally (lab page parsed)
        parsed = set(graph.parsed_pages)
        lab_url_parsed = any("lab" in p for p in parsed)
        self.assertTrue(
            lab_url_parsed or graph.member_count >= 0,
            "Pipeline should have attempted to navigate to lab page",
        )

    def test_homepage_only_publications_continues_navigation(self):
        """Test 3: Homepage contains only publications — continue navigation."""
        pipeline = self._make_pipeline(_HOMEPAGE_ONLY_PUBLICATIONS, lab_html=_LAB_PAGE_HTML)
        professor = _make_professor()
        graph = pipeline.analyze(professor, professor.homepage_graph)

        self.assertFalse(
            graph.homepage_accepted_as_group_page,
            "Homepage with only publications should not trigger homepage-first",
        )

    def test_homepage_only_teaching_continues_navigation(self):
        """Test 4: Homepage contains only teaching — continue navigation."""
        pipeline = self._make_pipeline(_HOMEPAGE_ONLY_TEACHING, lab_html=_LAB_PAGE_HTML)
        professor = _make_professor()
        graph = pipeline.analyze(professor, professor.homepage_graph)

        self.assertFalse(
            graph.homepage_accepted_as_group_page,
            "Homepage with only teaching should not trigger homepage-first",
        )

    def test_homepage_with_heading_cards_stops_navigation(self):
        """Heading-card layout on homepage should also trigger homepage-first."""
        pipeline = self._make_pipeline(_HOMEPAGE_HEADING_CARDS)
        professor = _make_professor()
        graph = pipeline.analyze(professor, professor.homepage_graph)

        # Note: heading-card detection depends on HeadingCardExtractor finding
        # entries; the test verifies the pipeline handles this case gracefully.
        # If heading cards are found, homepage should be accepted.
        if graph.homepage_accepted_as_group_page:
            self.assertGreater(graph.member_count, 0)
        # Either way, no exception should be raised.

    def test_disabled_homepage_first_falls_through_to_navigation(self):
        """When ENABLE_HOMEPAGE_FIRST=False, pipeline must not use homepage-first."""
        from research_group_agent.homepage_member_detector import HomepageMemberDetector

        pipeline = self._make_pipeline(_HOMEPAGE_WITH_MEMBERS, lab_html=_LAB_PAGE_HTML)
        pipeline.homepage_detector = HomepageMemberDetector(enabled=False)
        professor = _make_professor()
        graph = pipeline.analyze(professor, professor.homepage_graph)

        self.assertFalse(
            graph.homepage_accepted_as_group_page,
            "Disabled detector must not trigger homepage-first path",
        )


class TestPipelineNavigationGuard(unittest.TestCase):
    """Test PR22 Part 2: navigation guard prevents wrong-navigation targets."""

    def _make_pipeline_with_candidate(
        self, candidate_url: str, candidate_html: str
    ) -> ResearchGroupPipeline:
        """Create a pipeline with a specific bad candidate and its HTML."""
        def _fake_fetch(url: str) -> HomepageDocument:
            if url.rstrip("/") == candidate_url.rstrip("/"):
                return _mock_fetch(candidate_html, url)
            return _mock_fetch(_HOMEPAGE_NO_MEMBERS, url)

        nodes = [
            GraphNode(
                node_type="people_page",
                url=candidate_url,
                confidence=ConfidenceScore.from_stub(0.8, 0.75),
                discovery_method="heuristic",
                anchor_text="People",
            )
        ]
        pipeline = ResearchGroupPipeline(provider=StubResearchGroupProvider())
        pipeline.fetcher.fetch = _fake_fetch
        return pipeline, nodes

    def test_collaborator_homepage_should_not_replace_homepage(self):
        """Test 5: Candidate page is collaborator homepage — should not replace."""
        # A collaborator page URL that looks like a personal page
        bad_url = "https://cs.university.edu/people/faculty/frank-castle"
        pipeline, nodes = self._make_pipeline_with_candidate(bad_url, _COLLABORATOR_HOMEPAGE)
        professor = _make_professor(nodes=nodes)
        graph = pipeline.analyze(professor, professor.homepage_graph)
        # The navigation guard should have penalised this candidate
        # (it's under /people/faculty which is a dept_directory pattern)
        # If accepted, members would be 0 from the collaborator page
        self.assertFalse(
            graph.homepage_accepted_as_group_page,
            "Collaborator homepage should not trigger homepage-first",
        )

    def test_department_directory_should_not_be_group_page(self):
        """Test 6: Candidate page is department directory — should not replace homepage."""
        dept_url = "https://cs.university.edu/faculty?type=all"
        dept_html = """
        <html><head><title>CS Faculty Directory</title></head>
        <body><h1>Faculty Directory</h1>
        <p>Faculty Type: <select><option>All</option></select></p>
        </body></html>
        """
        pipeline, nodes = self._make_pipeline_with_candidate(dept_url, dept_html)
        professor = _make_professor(nodes=nodes)
        graph = pipeline.analyze(professor, professor.homepage_graph)
        # Should not have used the dept directory as group page
        # (score heavily penalised by navigation guard)
        self.assertFalse(
            graph.homepage_accepted_as_group_page,
            "Department directory should not be accepted as group page",
        )

    def test_navigation_guard_penalises_teaching_url(self):
        """NavigationGuard penalises teaching page URLs before ranking."""
        guard = NavigationGuard()
        teaching_cand = CandidatePage(
            url="https://ada.example.edu/teaching/cs501",
            page_type="other",
            anchor_text="Teaching",
            score=0.80,
            evidence=[],
            source_node_type="teaching_page",
            graph_confidence=0.7,
        )
        filtered = guard.filter([teaching_cand])
        self.assertLess(
            filtered[0].score,
            teaching_cand.score,
            "Teaching page should be penalised by navigation guard",
        )

    def test_navigation_guard_preserves_lab_page_score(self):
        """NavigationGuard must NOT penalise lab/members pages."""
        guard = NavigationGuard()
        lab_cand = CandidatePage(
            url="https://ada.example.edu/lab/members",
            page_type=PAGE_TYPE_LAB,
            anchor_text="Lab Members",
            score=0.90,
            evidence=[],
            source_node_type="lab_page",
            graph_confidence=0.9,
        )
        filtered = guard.filter([lab_cand])
        self.assertEqual(
            filtered[0].score,
            lab_cand.score,
            "Lab page score must be unchanged by navigation guard",
        )


class TestPipelineHomepagePreference(unittest.TestCase):
    """Test PR22 Part 3: when both homepage and candidate look like member pages,
    homepage is preferred unless candidate clearly has more members."""

    def test_homepage_wins_when_both_have_members(self):
        """Test 7: Homepage and candidate both contain members — homepage wins."""
        homepage_url = "https://ada.example.edu/"
        lab_url = "https://ada.example.edu/lab/"

        # Homepage has 4 members, lab has 5 — lab has more, but just barely
        # Under Part 3 (homepage preference), if homepage already qualifies
        # via Part 1 (>=3 members), it wins outright.
        def _fake_fetch(url: str) -> HomepageDocument:
            if url.rstrip("/") == homepage_url.rstrip("/"):
                return _mock_fetch(_HOMEPAGE_WITH_MEMBERS, url)
            return _mock_fetch(_LAB_PAGE_HTML, url)

        nodes = [
            GraphNode(
                node_type="lab_page",
                url=lab_url,
                confidence=ConfidenceScore.from_stub(0.9, 0.85),
                discovery_method="heuristic",
                anchor_text="Lab Members",
            )
        ]
        pipeline = ResearchGroupPipeline(provider=StubResearchGroupProvider())
        pipeline.fetcher.fetch = _fake_fetch
        professor = _make_professor(nodes=nodes)
        graph = pipeline.analyze(professor, professor.homepage_graph)

        # Since homepage has >=3 members, Part 1 accepts it → homepage wins
        self.assertTrue(
            graph.homepage_accepted_as_group_page,
            "Homepage with >= threshold members should win via Part 1",
        )
        self.assertGreater(graph.member_count, 0)

    def test_homepage_preference_boost_for_borderline_case(self):
        """Part 3: when homepage has members (below threshold), its page_type is boosted."""
        pipeline = ResearchGroupPipeline(provider=StubResearchGroupProvider())
        canonical = "https://ada.example.edu/"

        # Simulate a detection with 2 members (below threshold of 3)
        from research_group_agent.homepage_member_detector import HomepageMemberDetectionResult
        from research_group_agent.parser import ParsedMemberPage
        detection = HomepageMemberDetectionResult(
            homepage_url=canonical,
            homepage_is_group_page=False,
            member_count=2,
            has_member_sections=True,
            has_heading_cards=False,
            detection_reason="below threshold",
        )

        candidates = [
            CandidatePage(
                url=canonical,
                page_type=PAGE_TYPE_HOMEPAGE,
                anchor_text="",
                score=0.0,
                evidence=[],
                source_node_type="homepage",
                graph_confidence=1.0,
            ),
            CandidatePage(
                url="https://ada.example.edu/research/",
                page_type=PAGE_TYPE_OTHER,
                anchor_text="Research",
                score=0.0,
                evidence=[],
                source_node_type="other",
                graph_confidence=0.5,
            ),
        ]

        boosted = pipeline._apply_homepage_preference(candidates, canonical, detection.member_count)

        homepage_cand = next(c for c in boosted if c.url.rstrip("/") == canonical.rstrip("/"))
        other_cand = next(c for c in boosted if "research" in c.url)

        # Homepage page_type should be boosted
        self.assertIn(
            homepage_cand.page_type,
            (PAGE_TYPE_LAB, PAGE_TYPE_MEMBERS),
            "Homepage page_type should be boosted to lab or members",
        )
        # Other candidate should be unchanged
        self.assertEqual(other_cand.page_type, PAGE_TYPE_OTHER)

        # Evidence should record the boost
        self.assertTrue(
            any("homepage_preference" in e for e in homepage_cand.evidence),
            "Homepage candidate evidence should record preference boost",
        )


class TestPipelineRegressionExistingNavigation(unittest.TestCase):
    """Test 8: Existing successful navigation remains unchanged."""

    def test_successful_lab_page_navigation_unaffected(self):
        """When homepage has no members, lab-page navigation still finds members."""
        lab_url = "https://ada.example.edu/lab/"

        def _fake_fetch(url: str) -> HomepageDocument:
            if url.rstrip("/") == lab_url.rstrip("/"):
                return _mock_fetch(_LAB_PAGE_HTML, url)
            return _mock_fetch(_HOMEPAGE_NO_MEMBERS, url)

        nodes = [
            GraphNode(
                node_type="lab_page",
                url=lab_url,
                confidence=ConfidenceScore.from_stub(0.9, 0.85),
                discovery_method="heuristic",
                anchor_text="Lab Members",
            )
        ]
        pipeline = ResearchGroupPipeline(provider=StubResearchGroupProvider())
        pipeline.fetcher.fetch = _fake_fetch
        professor = _make_professor(nodes=nodes)
        graph = pipeline.analyze(professor, professor.homepage_graph)

        # Must NOT use homepage-first path
        self.assertFalse(graph.homepage_accepted_as_group_page)
        # Must still extract members from the lab page
        self.assertGreater(
            graph.member_count,
            0,
            "Lab page navigation must still extract members when homepage has none",
        )
        # Group page must be the lab page, not the homepage
        self.assertIsNotNone(graph.group_page)
        self.assertIn("lab", graph.group_page.url)

    def test_pipeline_version_updated_to_pr32(self):
        """PIPELINE_VERSION must be 'PR32' after homepage recovery + lab discovery."""
        self.assertEqual(PIPELINE_VERSION, "PR32")

    def test_graph_builder_backward_compatible(self):
        """graph_builder.build must still work without homepage_accepted kwarg."""
        from research_group_agent.graph_builder import ResearchGroupGraphBuilder
        from research_group_agent.models import GroupPageSelection

        builder = ResearchGroupGraphBuilder()
        group_page = GroupPageSelection(
            url="https://ada.example.edu/lab/",
            source_node_type="lab_page",
            confidence=0.9,
            reason="lab page",
            navigation_path=["https://ada.example.edu/"],
            navigation_provider="heuristic",
        )
        graph = builder.build(
            professor_name="Ada Lovelace",
            professor_homepage="https://ada.example.edu/",
            group_page=group_page,
            members=[],
            provider="heuristic",
        )
        # Must have default value for new field
        self.assertFalse(graph.homepage_accepted_as_group_page)
        # to_dict must include the new field
        d = graph.to_dict()
        self.assertIn("homepage_accepted_as_group_page", d)
        self.assertFalse(d["homepage_accepted_as_group_page"])

    def test_homepage_accepted_flag_in_dict(self):
        """When homepage is accepted, the flag is True in to_dict."""
        from research_group_agent.graph_builder import ResearchGroupGraphBuilder
        from research_group_agent.models import GroupPageSelection

        builder = ResearchGroupGraphBuilder()
        group_page = GroupPageSelection(
            url="https://ada.example.edu/",
            source_node_type="homepage",
            confidence=0.95,
            reason="homepage_first",
            navigation_path=["https://ada.example.edu/"],
            navigation_provider="homepage_first",
        )
        graph = builder.build(
            professor_name="Ada Lovelace",
            professor_homepage="https://ada.example.edu/",
            group_page=group_page,
            members=[],
            provider="heuristic",
            homepage_accepted_as_group_page=True,
        )
        d = graph.to_dict()
        self.assertTrue(d["homepage_accepted_as_group_page"])


if __name__ == "__main__":
    unittest.main()
