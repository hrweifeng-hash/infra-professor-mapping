"""PR32 — Homepage Recovery & Lab Discovery tests."""

from __future__ import annotations

import unittest

from homepage_agent.homepage_recovery import (
    METHOD_CANONICAL,
    METHOD_HTTP_REDIRECT,
    METHOD_META_REFRESH,
    METHOD_MOVED_PAGE,
    HomepageRecovery,
)
from research_group_agent.candidate_page import (
    CandidatePage,
    CandidatePageRanker,
    PAGE_TYPE_LAB,
    PAGE_TYPE_LAB_HOME,
    PAGE_TYPE_MEMBERS,
    PAGE_TYPE_PEOPLE,
    PAGE_TYPE_TEAM,
)
from research_group_agent.lab_discovery import LabDiscovery


class TestHomepageRecovery(unittest.TestCase):
    def setUp(self) -> None:
        self.recovery = HomepageRecovery()

    def test_http_redirect_recovery(self) -> None:
        result = self.recovery.recover(
            "http://old.edu/~prof/",
            "<html><body>Welcome</body></html>",
            final_url="http://new.edu/~prof/",
        )
        self.assertTrue(result.was_recovered)
        self.assertEqual(result.method, METHOD_HTTP_REDIRECT)
        self.assertEqual(result.recovered_url, "http://new.edu/~prof/")

    def test_meta_refresh_recovery(self) -> None:
        html = """
        <html>
        <head>
          <meta http-equiv="refresh" content="0;url=https://new.site.edu/~smith">
        </head>
        <body>Moved</body>
        </html>
        """
        result = self.recovery.recover(
            "http://old.edu/~smith",
            html,
        )
        self.assertTrue(result.was_recovered)
        self.assertEqual(result.method, METHOD_META_REFRESH)
        self.assertIn("new.site.edu", result.recovered_url or "")

    def test_canonical_recovery(self) -> None:
        html = """
        <html>
        <head>
          <link rel="canonical" href="https://prof.edu/homepage/">
        </head>
        <body>Stub page</body>
        </html>
        """
        result = self.recovery.recover(
            "https://dept.edu/faculty/smith",
            html,
        )
        self.assertTrue(result.was_recovered)
        self.assertEqual(result.method, METHOD_CANONICAL)

    def test_moved_page_recovery(self) -> None:
        html = """
        <html><body>
          <p>I moved to University of Michigan.</p>
          <p>Please visit my <a href="https://michigan.edu/~smith">new homepage</a>.</p>
        </body></html>
        """
        result = self.recovery.recover(
            "https://old.edu/~smith",
            html,
        )
        self.assertTrue(result.was_recovered)
        self.assertEqual(result.method, METHOD_MOVED_PAGE)
        self.assertIn("michigan.edu", result.recovered_url or "")

    def test_no_recovery_when_page_is_active(self) -> None:
        html = "<html><body><h1>Ada Lovelace</h1><p>Research</p></body></html>"
        result = self.recovery.recover(
            "https://example.edu/~ada",
            html,
            final_url="https://example.edu/~ada",
        )
        self.assertFalse(result.was_recovered)


class TestLabDiscovery(unittest.TestCase):
    def setUp(self) -> None:
        self.discovery = LabDiscovery()

    def test_discovers_lab_from_anchor_text(self) -> None:
        html = """
        <html><body>
          <nav>
            <a href="https://orderlab.systems/">OrderLab</a>
            <a href="/contact">Contact</a>
          </nav>
          <p>I lead the OrderLab research group.</p>
        </body></html>
        """
        candidates = self.discovery.discover(html, "https://example.edu/~huang")
        self.assertTrue(any("orderlab" in c.url.lower() for c in candidates))
        self.assertTrue(all(c.page_type == PAGE_TYPE_LAB_HOME for c in candidates))

    def test_discovers_lab_from_url_signals(self) -> None:
        html = """
        <html><body>
          <a href="https://netlab.cs.wisc.edu/">NetLab</a>
        </body></html>
        """
        candidates = self.discovery.discover(html, "https://wisc.edu/~liu")
        self.assertTrue(any("netlab" in c.url.lower() for c in candidates))

    def test_navigation_menu_lab_signal(self) -> None:
        html = """
        <html><body>
          <nav>
            <a href="/lab">Lab</a>
            <a href="/team">Team</a>
            <a href="/publications">Publications</a>
          </nav>
        </body></html>
        """
        candidates = self.discovery.discover(html, "https://example.edu/~prof")
        urls = [c.url for c in candidates]
        self.assertIn("https://example.edu/lab", urls)

    def test_deduplicates_seen_urls(self) -> None:
        html = '<html><body><a href="/lab">Our Lab</a></body></html>'
        seen = {"https://example.edu/lab"}
        candidates = self.discovery.discover(
            html, "https://example.edu/~prof", already_seen=seen,
        )
        self.assertEqual(candidates, [])


class TestLabHomeRanking(unittest.TestCase):
    def test_lab_home_ranks_above_team_and_members(self) -> None:
        ranker = CandidatePageRanker(enable_navigation_evidence=False)
        candidates = [
            CandidatePage(url="https://lab.edu/team", page_type=PAGE_TYPE_TEAM),
            CandidatePage(url="https://lab.edu/", page_type=PAGE_TYPE_LAB_HOME),
            CandidatePage(url="https://lab.edu/members", page_type=PAGE_TYPE_MEMBERS),
            CandidatePage(url="https://dept.edu/faculty", page_type=PAGE_TYPE_PEOPLE),
        ]
        ranked = ranker.rank(candidates, top_n=4, min_score=0.0)
        types = [c.page_type for c in ranked]
        self.assertLess(types.index(PAGE_TYPE_LAB_HOME), types.index(PAGE_TYPE_TEAM))
        self.assertLess(types.index(PAGE_TYPE_LAB_HOME), types.index(PAGE_TYPE_MEMBERS))


if __name__ == "__main__":
    unittest.main()
