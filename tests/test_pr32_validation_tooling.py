"""Tests for PR32 validation methodology and observability helpers."""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout

from tools.pr32_navigation_validation import (
    BASELINE_VERSION,
    align_cohorts,
    build_professor_comparisons,
    build_report,
    member_count,
    navigation_success,
    print_fetch_summary,
    print_recall_summary,
    recall_comparison,
    render_html,
)


def _graph(name: str, members: int, *, fetch_status: str = "success") -> dict:
    return {
        "professor_name": name,
        "fetch_status": fetch_status,
        "member_count": members,
        "current_member_count": members,
        "canonical_homepage": f"https://example.edu/~{name.lower().replace(' ', '')}/",
        "navigation_discovery": {},
        "parsed_pages": [],
    }


class TestPr32ValidationMethodology(unittest.TestCase):
    def test_align_cohorts_matches_by_professor_name(self) -> None:
        baseline = [_graph("Alice", 5), _graph("Bob", 0)]
        pr32 = [_graph("Bob", 3), _graph("Alice", 7), _graph("Carol", 1)]

        aligned_base, aligned_pr32, names, meta = align_cohorts(baseline, pr32)

        self.assertEqual(names, ["Alice", "Bob"])
        self.assertEqual(meta["overlap_count"], 2)
        self.assertEqual(meta["baseline_only"], [])
        self.assertEqual(meta["pr32_only"], ["Carol"])
        self.assertEqual(member_count(aligned_base[0]), 5)
        self.assertEqual(member_count(aligned_pr32[0]), 7)

    def test_recall_comparison_uses_matched_cohort_only(self) -> None:
        baseline = [_graph("Alice", 2), _graph("Bob", 0)]
        pr32 = [_graph("Alice", 5), _graph("Bob", 0), _graph("Extra", 10)]

        result = recall_comparison(baseline, pr32)

        self.assertEqual(result["cohort"]["overlap_count"], 2)
        self.assertEqual(result["baseline_total_members"], 2)
        self.assertEqual(result["pr32_total_members"], 5)
        self.assertEqual(result["total_members_delta"], 3)
        self.assertEqual(result["improved_professors"], 1)
        self.assertEqual(result["regressed_professors"], 0)
        self.assertEqual(result["unchanged_professors"], 1)
        self.assertEqual(result["methodology"]["baseline_version"], BASELINE_VERSION)

    def test_navigation_success_requires_fetch_and_members(self) -> None:
        self.assertTrue(navigation_success(_graph("Alice", 3)))
        self.assertFalse(navigation_success(_graph("Alice", 0)))
        self.assertFalse(
            navigation_success(_graph("Alice", 3, fetch_status="timeout"))
        )

    def test_professor_comparisons_sorted_by_absolute_delta(self) -> None:
        baseline = [_graph("Small", 10), _graph("Big", 1)]
        pr32 = [_graph("Small", 11), _graph("Big", 20)]
        aligned_base, aligned_pr32, names = align_cohorts(baseline, pr32)[:3]

        rows = build_professor_comparisons(aligned_base, aligned_pr32, names)
        self.assertEqual(rows[0]["professor"], "Big")
        self.assertEqual(rows[0]["delta"], 19)
        self.assertEqual(rows[0]["status"], "improved")
        self.assertEqual(rows[1]["professor"], "Small")
        self.assertEqual(rows[1]["status"], "improved")

    def test_recall_comparison_counts_regressions(self) -> None:
        baseline = [_graph("Alice", 10)]
        pr32 = [_graph("Alice", 4)]

        result = recall_comparison(baseline, pr32)

        self.assertEqual(result["improved_professors"], 0)
        self.assertEqual(result["regressed_professors"], 1)
        self.assertEqual(result["unchanged_professors"], 0)
        self.assertEqual(result["total_members_delta"], -6)

    def test_render_html_includes_comparison_table(self) -> None:
        report = build_report(
            [_graph("Alice", 2), _graph("Bob", 0)],
            [_graph("Alice", 5), _graph("Bob", 0)],
        )
        html_output = render_html(report)

        self.assertIn("Alice", html_output)
        self.assertIn("Improved", html_output)
        self.assertIn("Baseline Members", html_output)

    def test_print_recall_summary_outputs_net_deltas(self) -> None:
        recall = recall_comparison(
            [_graph("Alice", 2)],
            [_graph("Alice", 5)],
        )
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            print_recall_summary(recall)

        output = buffer.getvalue()
        self.assertIn("Improved professors: 1", output)
        self.assertIn("Navigation success:", output)
        self.assertIn("Current members:", output)


class TestPr32ValidationObservability(unittest.TestCase):
    def test_print_fetch_summary_outputs_metrics(self) -> None:
        summary = {
            "total_requests": 10,
            "successful": 8,
            "timeouts": 1,
            "network_errors": 0,
            "redirect_limit_exceeded": 1,
            "average_latency": 0.84,
            "p95_latency": 3.21,
            "slow_requests": 2,
        }

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            print_fetch_summary(summary)

        output = buffer.getvalue()
        self.assertIn("Fetch Summary", output)
        self.assertIn("Total requests: 10", output)
        self.assertIn("Successful: 8", output)
        self.assertIn("Timeouts: 1", output)
        self.assertIn("Redirect limit exceeded: 1", output)
        self.assertIn("Slow requests (>5s): 2", output)

    def test_print_fetch_summary_skipped_when_unavailable(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            print_fetch_summary(None)

        self.assertIn("unavailable", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
