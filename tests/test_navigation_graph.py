"""M5-PR1 — Navigation graph and explorer tests."""

from __future__ import annotations

import unittest

from research_group_agent.candidate_page import (
    PAGE_TYPE_LAB,
    PAGE_TYPE_MEMBERS,
    PAGE_TYPE_PEOPLE,
    PAGE_TYPE_STUDENTS,
)
from research_group_agent.navigation_explorer import NavigationExplorer
from research_group_agent.navigation_graph import NavigationGraphBuilder
from research_group_agent.navigation_models import (
    VisitStatus,
    has_negative_signal,
    infer_page_type,
    is_candidate_page,
    is_expandable_link,
    normalize_navigation_url,
    should_ignore_url,
)


def _html_provider_factory(pages: dict[str, str]):
    """Return a callable that serves HTML by normalized URL key."""

    def provider(url: str) -> str | None:
        key = normalize_navigation_url(url)
        for page_url, html in pages.items():
            if normalize_navigation_url(page_url) == key:
                return html
        return None

    return provider


HOMEPAGE_HTML = """
<html><body>
  <nav>
    <a href="/lab/">Our Lab</a>
    <a href="/teaching/">Teaching</a>
    <a href="/news/">News</a>
  </nav>
</body></html>
"""

LAB_HTML = """
<html><body>
  <a href="/lab/people.html">People</a>
  <a href="/lab/publications">Publications</a>
</body></html>
"""

PEOPLE_HTML = """
<html><body>
  <a href="/lab/people/current.html">Current Members</a>
  <a href="/lab/people/alumni.html">Alumni</a>
</body></html>
"""

MEMBERS_HTML = """
<html><body><h1>Current Members</h1><ul><li>Alice</li></ul></body></html>
"""

CYCLE_HTML = """
<html><body>
  <a href="/lab/">Lab</a>
  <a href="/lab/people.html">People</a>
</body></html>
"""


class TestUrlNormalization(unittest.TestCase):
    def test_removes_fragment(self):
        self.assertEqual(
            normalize_navigation_url("https://example.edu/lab/#section"),
            "https://example.edu/lab",
        )

    def test_removes_trailing_slash(self):
        self.assertEqual(
            normalize_navigation_url("https://example.edu/lab/"),
            "https://example.edu/lab",
        )

    def test_collapses_duplicate_slashes(self):
        self.assertEqual(
            normalize_navigation_url("https://example.edu//lab//people"),
            "https://example.edu/lab/people",
        )

    def test_strips_default_index_page(self):
        self.assertEqual(
            normalize_navigation_url("https://example.edu/lab/index.html"),
            "https://example.edu/lab",
        )

    def test_duplicate_urls_normalize_identically(self):
        a = normalize_navigation_url("https://Example.edu/Lab/")
        b = normalize_navigation_url("https://example.edu/lab/index.html")
        self.assertEqual(a, b)


class TestUrlFiltering(unittest.TestCase):
    def test_ignore_mailto(self):
        self.assertTrue(should_ignore_url("mailto:prof@example.edu"))

    def test_ignore_javascript(self):
        self.assertTrue(should_ignore_url("javascript:void(0)"))

    def test_ignore_pdf(self):
        self.assertTrue(should_ignore_url("https://example.edu/paper.pdf"))

    def test_ignore_images(self):
        self.assertTrue(should_ignore_url("https://example.edu/logo.png"))

    def test_negative_teaching_signal(self):
        self.assertTrue(has_negative_signal("https://example.edu/teaching", "Teaching"))

    def test_negative_publications_signal(self):
        self.assertTrue(has_negative_signal("https://example.edu/publications", ""))


class TestPositiveNegativeLinks(unittest.TestCase):
    def test_positive_lab_link_expandable(self):
        self.assertTrue(is_expandable_link("https://example.edu/lab", "Our Lab"))

    def test_positive_people_link_expandable(self):
        self.assertTrue(is_expandable_link("https://example.edu/people", "People"))

    def test_negative_link_not_expandable(self):
        self.assertFalse(is_expandable_link("https://example.edu/courses", "Courses"))

    def test_neutral_link_not_expandable(self):
        self.assertFalse(is_expandable_link("https://example.edu/about", "About Us"))

    def test_members_page_is_candidate(self):
        self.assertTrue(
            is_candidate_page("https://example.edu/lab/members", "Current Members")
        )

    def test_lab_page_not_candidate_by_default(self):
        self.assertFalse(is_candidate_page("https://example.edu/lab", "Our Lab"))


class TestPageTypeInference(unittest.TestCase):
    def test_infer_people(self):
        self.assertEqual(
            infer_page_type("https://example.edu/people", "People"),
            PAGE_TYPE_PEOPLE,
        )

    def test_infer_students(self):
        self.assertEqual(
            infer_page_type("https://example.edu/students", "Graduate Students"),
            PAGE_TYPE_STUDENTS,
        )

    def test_infer_members(self):
        self.assertEqual(
            infer_page_type("https://example.edu/members", "Members"),
            PAGE_TYPE_MEMBERS,
        )

    def test_infer_lab(self):
        self.assertEqual(
            infer_page_type("https://example.edu/lab", "Our Lab"),
            PAGE_TYPE_LAB,
        )


class TestNavigationGraphBuilder(unittest.TestCase):
    def test_create_root_node(self):
        graph = NavigationGraphBuilder().create("https://example.edu/~prof/")
        self.assertIn(normalize_navigation_url("https://example.edu/~prof/"), graph.nodes)
        root = graph.nodes[normalize_navigation_url("https://example.edu/~prof/")]
        self.assertEqual(root.depth, 0)
        self.assertIsNone(root.parent_url)


class TestNavigationExplorerBfs(unittest.TestCase):
    def _explorer(self, pages: dict[str, str]) -> NavigationExplorer:
        return NavigationExplorer(
            max_depth=3,
            max_pages=150,
            html_provider=_html_provider_factory(pages),
        )

    def test_bfs_discovers_multi_level_chain(self):
        pages = {
            "https://example.edu/~prof/": HOMEPAGE_HTML,
            "https://example.edu/lab/": LAB_HTML,
            "https://example.edu/lab/people.html": PEOPLE_HTML,
            "https://example.edu/lab/people/current.html": MEMBERS_HTML,
        }
        explorer = self._explorer(pages)
        graph, candidates = explorer.explore("https://example.edu/~prof/")

        candidate_urls = {normalize_navigation_url(c.url) for c in candidates}
        self.assertIn(normalize_navigation_url("https://example.edu/lab/people/current.html"), candidate_urls)
        self.assertGreaterEqual(graph.statistics.pages_visited, 3)

    def test_bfs_deterministic_order(self):
        pages = {
            "https://example.edu/": """
            <html><body>
              <a href="/z-lab">Z Lab</a>
              <a href="/a-lab">A Lab</a>
            </body></html>
            """,
            "https://example.edu/a-lab": "<html><body><a href='/a-lab/people'>People</a></body></html>",
            "https://example.edu/z-lab": "<html><body><a href='/z-lab/people'>People</a></body></html>",
            "https://example.edu/a-lab/people": MEMBERS_HTML,
            "https://example.edu/z-lab/people": MEMBERS_HTML,
        }
        explorer = self._explorer(pages)
        graph1, _ = explorer.explore("https://example.edu/")
        explorer2 = self._explorer(pages)
        graph2, _ = explorer2.explore("https://example.edu/")
        self.assertEqual(
            [edge.to_url for edge in graph1.edges],
            [edge.to_url for edge in graph2.edges],
        )

    def test_depth_limit_stops_expansion(self):
        pages = {
            "https://example.edu/": '<html><body><a href="/lab">Lab</a></body></html>',
            "https://example.edu/lab": '<html><body><a href="/lab/people">People</a></body></html>',
            "https://example.edu/lab/people": '<html><body><a href="/lab/people/members">Members</a></body></html>',
            "https://example.edu/lab/people/members": MEMBERS_HTML,
        }
        explorer = NavigationExplorer(
            max_depth=1,
            max_pages=150,
            html_provider=_html_provider_factory(pages),
        )
        graph, _ = explorer.explore("https://example.edu/")
        self.assertLessEqual(graph.statistics.maximum_depth, 1)

    def test_page_budget_limit(self):
        links = "".join(f'<a href="/page{i}">Lab {i}</a>' for i in range(20))
        pages = {
            "https://example.edu/": f"<html><body>{links}</body></html>",
        }
        explorer = NavigationExplorer(
            max_depth=3,
            max_pages=5,
            html_provider=_html_provider_factory(pages),
        )
        graph, _ = explorer.explore("https://example.edu/")
        self.assertLessEqual(graph.statistics.pages_visited, 5)

    def test_loop_prevention(self):
        pages = {
            "https://example.edu/": CYCLE_HTML,
            "https://example.edu/lab/": CYCLE_HTML,
            "https://example.edu/lab/people.html": MEMBERS_HTML,
        }
        explorer = self._explorer(pages)
        graph, _ = explorer.explore("https://example.edu/")
        self.assertGreater(graph.statistics.loops_prevented, 0)

    def test_skips_negative_links(self):
        pages = {
            "https://example.edu/": HOMEPAGE_HTML,
            "https://example.edu/lab/": LAB_HTML,
            "https://example.edu/lab/people.html": PEOPLE_HTML,
            "https://example.edu/lab/people/current.html": MEMBERS_HTML,
            "https://example.edu/teaching/": "<html><body>Teaching</body></html>",
            "https://example.edu/news/": "<html><body>News</body></html>",
        }
        explorer = self._explorer(pages)
        graph, _ = explorer.explore("https://example.edu/")
        visited = {normalize_navigation_url(url) for url in graph.visited_urls}
        self.assertNotIn(normalize_navigation_url("https://example.edu/teaching/"), visited)
        self.assertNotIn(normalize_navigation_url("https://example.edu/news/"), visited)

    def test_collect_candidate_pages_source_type(self):
        pages = {
            "https://example.edu/": HOMEPAGE_HTML,
            "https://example.edu/lab/": LAB_HTML,
            "https://example.edu/lab/people.html": PEOPLE_HTML,
            "https://example.edu/lab/people/current.html": MEMBERS_HTML,
        }
        explorer = self._explorer(pages)
        _, candidates = explorer.explore("https://example.edu/")
        self.assertTrue(candidates)
        for candidate in candidates:
            self.assertEqual(candidate.source_node_type, "navigation_explorer")

    def test_respects_already_seen(self):
        pages = {
            "https://example.edu/": HOMEPAGE_HTML,
            "https://example.edu/lab/": LAB_HTML,
            "https://example.edu/lab/people.html": MEMBERS_HTML,
        }
        explorer = self._explorer(pages)
        seen = {normalize_navigation_url("https://example.edu/lab/people.html")}
        _, candidates = explorer.explore("https://example.edu/", already_seen=seen)
        candidate_urls = {normalize_navigation_url(c.url) for c in candidates}
        self.assertNotIn(normalize_navigation_url("https://example.edu/lab/people.html"), candidate_urls)

    def test_discover_links_sorts_alphabetically(self):
        html = """
        <html><body>
          <a href="/z-page">People Z</a>
          <a href="/a-page">People A</a>
        </body></html>
        """
        explorer = NavigationExplorer(html_provider=lambda _u: html)
        links = explorer.discover_links(html, "https://example.edu/")
        urls = [link.url for link in links]
        self.assertEqual(urls, sorted(urls, key=normalize_navigation_url))

    def test_depth_distribution_tracked(self):
        pages = {
            "https://example.edu/": HOMEPAGE_HTML,
            "https://example.edu/lab/": LAB_HTML,
            "https://example.edu/lab/people.html": PEOPLE_HTML,
            "https://example.edu/lab/people/current.html": MEMBERS_HTML,
        }
        explorer = self._explorer(pages)
        graph, _ = explorer.explore("https://example.edu/")
        self.assertIn("0", graph.statistics.depth_distribution)


class TestNavigationGraphSerialization(unittest.TestCase):
    def test_to_dict_includes_statistics(self):
        graph = NavigationGraphBuilder().create("https://example.edu/")
        graph.finalize_statistics()
        payload = graph.to_dict()
        self.assertIn("statistics", payload)
        self.assertIn("framework_version", payload)
        self.assertEqual(payload["root_url"], "https://example.edu/")


if __name__ == "__main__":
    unittest.main()
