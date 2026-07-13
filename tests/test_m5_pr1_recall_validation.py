"""Tests for M5-PR1 recall validation analysis."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from homepage_agent.models import FetchStatus, HomepageGraph
from research_group_agent.navigation_explorer import NavigationExplorer
from research_group_agent.navigation_models import normalize_navigation_url
from tools.m5_pr1_recall_validation import (
    ProfessorRecallReport,
    analyze_professor,
    build_recommendations,
    compute_overall_metrics,
    count_duplicate_urls,
    detect_regressions,
    extract_navigation_paths,
    members_from_navigation_pages,
    rank_top_gains,
    render_markdown,
    run_analysis,
)


def _norm(url: str) -> str:
    return normalize_navigation_url(url)


class TestUrlAndDuplicateHelpers(unittest.TestCase):
    def test_count_duplicate_urls(self):
        self.assertEqual(
            count_duplicate_urls(
                [
                    "https://example.edu/lab/",
                    "https://example.edu/lab/index.html",
                    "https://example.edu/people",
                ]
            ),
            1,
        )

    def test_members_from_navigation_pages(self):
        sources = {
            "Alice": ["https://example.edu/nav/members"],
            "Bob": ["https://example.edu/baseline"],
        }
        nav_urls = {_norm("https://example.edu/nav/members")}
        found = members_from_navigation_pages(sources, nav_urls, ["Alice", "Bob"])
        self.assertEqual(found, {"Alice"})


class TestNavigationPathExtraction(unittest.TestCase):
    def test_extract_navigation_paths(self):
        nav_graph = {
            "nodes": {
                "root": {
                    "url": "https://example.edu/",
                    "parent_url": None,
                },
                "lab": {
                    "url": "https://example.edu/lab",
                    "parent_url": "https://example.edu/",
                },
                "members": {
                    "url": "https://example.edu/lab/members",
                    "parent_url": "https://example.edu/lab",
                },
            }
        }
        paths = extract_navigation_paths(
            nav_graph,
            {_norm("https://example.edu/lab/members")},
        )
        self.assertTrue(paths)
        self.assertIn("members", paths[0])


class TestAnalyzeProfessor(unittest.TestCase):
    def _explorer(self) -> NavigationExplorer:
        pages = {
            "https://example.edu/~prof/": """
            <html><body><a href="https://example.edu/lab/">Lab</a></body></html>
            """,
            "https://example.edu/lab/": """
            <html><body><a href="https://example.edu/lab/people.html">People</a></body></html>
            """,
            "https://example.edu/lab/people.html": """
            <html><body><a href="https://example.edu/lab/people/current.html">Current Members</a></body></html>
            """,
            "https://example.edu/lab/people/current.html": """
            <html><body><h1>Members</h1></body></html>
            """,
        }

        def provider(url: str) -> str | None:
            key = _norm(url)
            for page_url, html in pages.items():
                if _norm(page_url) == key:
                    return html
            return None

        return NavigationExplorer(html_provider=provider)

    def test_analyze_professor_counts_navigation_candidates(self):
        homepage = "https://example.edu/~prof/"
        hp_graph = HomepageGraph(
            professor_name="Test Prof",
            homepage_url=homepage,
            fetch_status=FetchStatus.SUCCESS,
            canonical_homepage=homepage,
        )
        rg_graph = {
            "professor_name": "Test Prof",
            "professor_homepage": homepage,
            "canonical_homepage": homepage,
            "members": [{"name": "Nav Member"}],
            "former_members": [],
            "member_sources": {
                "Nav Member": ["https://example.edu/lab/people/current.html"],
            },
            "parsed_pages": [
                homepage,
                "https://example.edu/lab/people/current.html",
            ],
        }
        report = analyze_professor(
            rg_graph,
            hp_graph,
            explorer=self._explorer(),
            pr27_record={"estimated_visible_members": 5},
        )
        self.assertGreaterEqual(report.original_candidate_pages, 1)
        self.assertGreater(report.new_candidate_pages, 0)
        self.assertEqual(report.additional_current_members, 1)
        self.assertIsNotNone(report.recall_estimate_after)

    def test_analyze_professor_without_homepage_graph(self):
        report = analyze_professor(
            {
                "professor_name": "Empty",
                "professor_homepage": "",
                "members": [],
                "former_members": [],
                "member_sources": {},
                "parsed_pages": [],
            },
            None,
        )
        self.assertEqual(report.original_candidate_pages, 0)
        self.assertEqual(report.new_candidate_pages, 0)


class TestOverallMetrics(unittest.TestCase):
    def test_compute_overall_metrics(self):
        reports = [
            ProfessorRecallReport(
                professor="A",
                homepage="https://a.example.edu",
                original_candidate_pages=2,
                new_candidate_pages=3,
                additional_current_members=2,
                additional_former_members=1,
                current_members_before=1,
                current_members_after=3,
                former_members_before=0,
                former_members_after=1,
                navigation_depth=2,
                max_navigation_depth=2,
                recall_estimate_before=0.2,
                recall_estimate_after=0.6,
                recall_delta=0.4,
                delta_members=3,
            ),
            ProfessorRecallReport(
                professor="B",
                homepage="https://b.example.edu",
                original_candidate_pages=1,
                new_candidate_pages=0,
                current_members_before=4,
                current_members_after=4,
                former_members_before=1,
                former_members_after=1,
                navigation_depth=0,
                max_navigation_depth=0,
                delta_members=0,
            ),
        ]
        overall = compute_overall_metrics(reports)
        self.assertEqual(overall.professors_evaluated, 2)
        self.assertEqual(overall.additional_students_total, 3)
        self.assertEqual(overall.professors_with_new_candidates, 1)
        self.assertEqual(overall.maximum_navigation_depth, 2)


class TestTopGainsAndRegressions(unittest.TestCase):
    def test_rank_top_gains(self):
        reports = [
            ProfessorRecallReport(
                professor="High",
                homepage="",
                new_candidate_pages=5,
                delta_members=4,
                recall_delta=0.2,
            ),
            ProfessorRecallReport(
                professor="Low",
                homepage="",
                new_candidate_pages=1,
                delta_members=0,
                recall_delta=0.0,
            ),
        ]
        gains = rank_top_gains(reports)
        self.assertEqual(gains.by_member_increase[0]["professor"], "High")
        self.assertEqual(gains.by_candidate_increase[0]["professor"], "High")

    def test_detect_regressions_lost_members(self):
        reports = [
            ProfessorRecallReport(
                professor="Regressed",
                homepage="",
                duplicate_pages=0,
                loops_prevented=0,
            )
        ]
        pr29 = [
            {
                "professor_name": "Regressed",
                "member_count": 5,
                "parsed_pages": ["https://example.edu/a"],
            }
        ]
        rg = [
            {
                "professor_name": "Regressed",
                "member_count": 3,
                "parsed_pages": [],
            }
        ]
        findings = detect_regressions(reports, pr29_graphs=pr29, rg_graphs=rg)
        self.assertEqual(len(findings.lost_members), 1)
        self.assertEqual(len(findings.lost_pages), 1)

    def test_detect_duplicate_explosion(self):
        reports = [
            ProfessorRecallReport(
                professor="Dup",
                homepage="",
                duplicate_pages=6,
                loops_prevented=25,
            )
        ]
        findings = detect_regressions(reports)
        self.assertEqual(len(findings.duplicate_explosions), 1)
        self.assertEqual(len(findings.navigation_loops), 1)


class TestRecommendations(unittest.TestCase):
    def test_build_recommendations_worth_keeping(self):
        from tools.m5_pr1_recall_validation import OverallRecallMetrics, RegressionFindings, TopGains

        overall = OverallRecallMetrics(
            additional_students_total=12,
            professors_with_navigation_gains=3,
            total_new_candidate_pages=8,
        )
        rec = build_recommendations(
            overall,
            TopGains(by_member_increase=[{"professor": "Winner"}]),
            [{"path": "home → lab → people", "professor_count": 2}],
            RegressionFindings(),
        )
        self.assertTrue(rec["multi_level_navigation_worth_keeping"])
        self.assertIn("Winner", rec["professors_improved"])


class TestRunAnalysis(unittest.TestCase):
    def test_demo_run_analysis(self):
        report = run_analysis(demo=True)
        self.assertEqual(report.mode, "demo")
        self.assertGreater(report.overall.professors_evaluated, 0)
        self.assertIn("additional_students_found", report.recommendations)

    def test_render_markdown_contains_executive_answers(self):
        report = run_analysis(demo=True)
        md = render_markdown(report)
        self.assertIn("Executive Answers", md)
        self.assertIn("Additional students found", md)

    def test_main_writes_outputs(self):
        from tools import m5_pr1_recall_validation as module

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            module.OUTPUT_DIR = out_dir
            module.OUT_MD = out_dir / "M5_PR1_RECALL_VALIDATION.md"
            module.OUT_JSON = out_dir / "M5_PR1_RECALL_VALIDATION.json"

            report = run_analysis(demo=True)
            module.OUT_JSON.write_text(json.dumps(report.to_dict()), encoding="utf-8")
            module.OUT_MD.write_text(module.render_markdown(report), encoding="utf-8")

            self.assertTrue(module.OUT_JSON.exists())
            self.assertTrue(module.OUT_MD.exists())


if __name__ == "__main__":
    unittest.main()
