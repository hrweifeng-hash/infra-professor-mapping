import unittest

from homepage_agent.homepage_resolver import CanonicalHomepageResolver, HomepagePageType
from homepage_agent.models import ConfidenceScore, FetchStatus, GraphNode, HomepageGraph


class TestCanonicalHomepageResolver(unittest.TestCase):
    def test_personal_github_io_is_not_upgraded(self):
        graph = HomepageGraph(
            professor_name="Test Professor",
            homepage_url="https://prof.github.io/",
            fetch_status=FetchStatus.SUCCESS,
            graph_nodes=[],
        )
        resolved = CanonicalHomepageResolver().resolve(graph)
        self.assertEqual(resolved.canonical_homepage, "https://prof.github.io/")
        self.assertEqual(resolved.homepage_resolution_method, "already_personal")

    def test_rejects_department_navigation_links(self):
        graph = HomepageGraph(
            professor_name="Test Professor",
            homepage_url="https://www.cs.princeton.edu/people/profile/test",
            fetch_status=FetchStatus.SUCCESS,
            graph_nodes=[
                GraphNode(
                    node_type="contact_page",
                    url="https://www.cs.princeton.edu/courses/schedule",
                    confidence=ConfidenceScore.from_stub(0.9, 0.8),
                    discovery_method="heuristic",
                    anchor_text="Courses",
                ),
                GraphNode(
                    node_type="contact_page",
                    url="https://eecs.berkeley.edu/people/",
                    confidence=ConfidenceScore.from_stub(0.9, 0.8),
                    discovery_method="heuristic",
                    anchor_text="People",
                ),
            ],
        )
        resolver = CanonicalHomepageResolver()
        url, score, _anchor = resolver._find_personal_link(graph, graph.homepage_url)
        self.assertIsNone(url)
        self.assertLess(score, 0.65)

    def test_custom_personal_domain_classified(self):
        self.assertEqual(
            CanonicalHomepageResolver.classify_url("https://vincen.tl/"),
            HomepagePageType.PERSONAL_HOMEPAGE,
        )

    def test_homes_path_classified_as_personal(self):
        self.assertEqual(
            CanonicalHomepageResolver.classify_url(
                "http://www.cs.washington.edu/homes/arvind/"
            ),
            HomepagePageType.PERSONAL_HOMEPAGE,
        )

    def test_blocks_social_and_corporate_urls(self):
        resolver = CanonicalHomepageResolver()
        for url in (
            "https://www.facebook.com/PrincetonCS",
            "https://www.nvidia.com",
            "https://sites.google.com/cs.washington.edu/arvind/publications",
        ):
            score = resolver._score_personal_link("Homepage", url, "https://example.edu/profile")
            self.assertEqual(score, 0.0, msg=url)

    def test_finds_personal_link_in_cached_html(self):
        graph = HomepageGraph(
            professor_name="Test Professor",
            homepage_url="https://www.cs.princeton.edu/people/profile/test",
            fetch_status=FetchStatus.SUCCESS,
            graph_nodes=[
                GraphNode(
                    node_type="contact_page",
                    url="https://test-prof.github.io/",
                    confidence=ConfidenceScore.from_stub(0.9, 0.8),
                    discovery_method="heuristic",
                    anchor_text="Personal Homepage",
                ),
            ],
        )
        resolver = CanonicalHomepageResolver()
        url, score, anchor = resolver._find_personal_link(
            graph, graph.homepage_url
        )
        self.assertEqual(url, "https://test-prof.github.io/")
        self.assertGreaterEqual(score, 0.65)


if __name__ == "__main__":
    unittest.main()
