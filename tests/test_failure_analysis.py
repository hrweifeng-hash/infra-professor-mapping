"""Unit tests for tools/failure_analysis.py.

Covers the pure-logic functions (sorting, stats, record construction,
markdown/JSON rendering) without requiring disk I/O or a live pipeline run.
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.failure_analysis import (
    ProfessorRecord,
    ROOT_CAUSE_PLACEHOLDER,
    REVIEW_CATEGORIES,
    compute_stats,
    render_json,
    render_markdown,
    sort_for_review,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_record(
    name: str = "Alice Smith",
    navigation_success: bool = True,
    current_members: int = 5,
    former_members: int = 1,
    fetch_status: str = "success",
    heading_card_count: int | None = 0,
    errors: list[str] | None = None,
) -> ProfessorRecord:
    return ProfessorRecord(
        professor_name=name,
        homepage_url=f"https://example.edu/~{name.lower().replace(' ', '')}",
        candidate_pages=3,
        navigation_success=navigation_success,
        group_page_url="https://example.edu/lab/" if navigation_success else None,
        group_page_type="lab_page" if navigation_success else None,
        fetch_status=fetch_status,
        pages_parsed=2,
        pages_successful=1,
        pages_failed=1,
        current_members=current_members,
        former_members=former_members,
        heading_card_count=heading_card_count,
        parser_used="heuristic",
        errors=errors or [],
        parsed_page_urls=[],
    )


# ── Tests: sorting ────────────────────────────────────────────────────────────


class TestSortForReview(unittest.TestCase):
    def test_navigation_failures_come_first(self):
        nav_ok = _make_record("Bob Jones", navigation_success=True, current_members=5)
        nav_fail = _make_record("Alice Smith", navigation_success=False, current_members=0)
        result = sort_for_review([nav_ok, nav_fail])
        self.assertFalse(result[0].navigation_success)
        self.assertTrue(result[1].navigation_success)

    def test_zero_member_before_nonzero_within_nav_success(self):
        has_members = _make_record("Carol White", navigation_success=True, current_members=3)
        zero_members = _make_record("Dave Brown", navigation_success=True, current_members=0)
        result = sort_for_review([has_members, zero_members])
        self.assertEqual(result[0].current_members, 0)
        self.assertEqual(result[1].current_members, 3)

    def test_sorted_by_ascending_member_count_within_same_tier(self):
        r3 = _make_record("Carol", navigation_success=True, current_members=3)
        r1 = _make_record("Dave", navigation_success=True, current_members=1)
        r8 = _make_record("Eve", navigation_success=True, current_members=8)
        result = sort_for_review([r3, r1, r8])
        counts = [r.current_members for r in result]
        # Zero-members tier first, then ascending non-zero — r1 < r3 < r8
        self.assertEqual(counts, [1, 3, 8])

    def test_alphabetical_within_same_tier(self):
        r_z = _make_record("Zara Lee", navigation_success=True, current_members=0)
        r_a = _make_record("Amy Park", navigation_success=True, current_members=0)
        result = sort_for_review([r_z, r_a])
        self.assertEqual(result[0].professor_name, "Amy Park")
        self.assertEqual(result[1].professor_name, "Zara Lee")

    def test_empty_list_returns_empty(self):
        self.assertEqual(sort_for_review([]), [])

    def test_single_record_unchanged(self):
        r = _make_record()
        self.assertEqual(sort_for_review([r]), [r])


# ── Tests: statistics ─────────────────────────────────────────────────────────


class TestComputeStats(unittest.TestCase):
    def _records(self) -> list[ProfessorRecord]:
        return [
            _make_record("A", navigation_success=True,  current_members=0,  former_members=1),
            _make_record("B", navigation_success=True,  current_members=3,  former_members=0),
            _make_record("C", navigation_success=True,  current_members=10, former_members=5),
            _make_record("D", navigation_success=False, current_members=0,  former_members=0,
                         fetch_status="skipped"),
        ]

    def test_total_professors(self):
        stats = compute_stats(self._records())
        self.assertEqual(stats["total_professors"], 4)

    def test_navigation_counts(self):
        stats = compute_stats(self._records())
        self.assertEqual(stats["navigation_success_count"], 3)
        self.assertEqual(stats["navigation_failure_count"], 1)

    def test_zero_member_count(self):
        stats = compute_stats(self._records())
        self.assertEqual(stats["professors_zero_members"], 2)  # A and D

    def test_member_band_counts(self):
        stats = compute_stats(self._records())
        self.assertEqual(stats["professors_one_to_five_members"], 1)   # B
        self.assertEqual(stats["professors_more_than_five_members"], 1) # C

    def test_total_current_and_former(self):
        stats = compute_stats(self._records())
        self.assertEqual(stats["total_current_members"], 13)   # 0+3+10+0
        self.assertEqual(stats["total_former_members"], 6)     # 1+0+5+0

    def test_average_members(self):
        stats = compute_stats(self._records())
        self.assertAlmostEqual(stats["average_current_members"], 13 / 4, places=1)

    def test_fetch_status_distribution_present(self):
        stats = compute_stats(self._records())
        dist = stats["fetch_status_distribution"]
        self.assertIn("success", dist)
        self.assertIn("skipped", dist)
        self.assertEqual(dist["skipped"], 1)

    def test_empty_records_no_crash(self):
        stats = compute_stats([])
        self.assertEqual(stats["total_professors"], 0)
        self.assertEqual(stats["average_current_members"], 0.0)


# ── Tests: ProfessorRecord ────────────────────────────────────────────────────


class TestProfessorRecord(unittest.TestCase):
    def test_total_members_property(self):
        r = _make_record(current_members=4, former_members=2)
        self.assertEqual(r.total_members, 6)

    def test_root_cause_default_is_unknown(self):
        r = _make_record()
        self.assertEqual(r.root_cause, ROOT_CAUSE_PLACEHOLDER)

    def test_to_dict_contains_total_members(self):
        r = _make_record(current_members=3, former_members=1)
        d = r.to_dict()
        self.assertEqual(d["total_members"], 4)

    def test_to_dict_heading_card_count_null_when_none(self):
        r = _make_record(heading_card_count=None)
        d = r.to_dict()
        self.assertIsNone(d["heading_card_count"])

    def test_heading_card_count_value_preserved(self):
        r = _make_record(heading_card_count=7)
        d = r.to_dict()
        self.assertEqual(d["heading_card_count"], 7)


# ── Tests: markdown rendering ─────────────────────────────────────────────────


class TestRenderMarkdown(unittest.TestCase):
    def _render(self) -> str:
        records = sort_for_review([
            _make_record("Nav Fail Prof", navigation_success=False, current_members=0,
                         fetch_status="skipped"),
            _make_record("Zero Member Prof", navigation_success=True, current_members=0,
                         fetch_status="page_rejected"),
            _make_record("Few Members Prof", navigation_success=True, current_members=3),
            _make_record("Good Prof", navigation_success=True, current_members=10),
        ])
        stats = compute_stats(records)
        return render_markdown(records, stats, Path("data/output/pr21_research_group_graph.json"))

    def test_contains_summary_stats_header(self):
        md = self._render()
        self.assertIn("## Summary Statistics", md)
        self.assertIn("Total professors", md)

    def test_contains_all_review_categories(self):
        md = self._render()
        for cat in REVIEW_CATEGORIES:
            self.assertIn(cat, md)

    def test_navigation_failure_section_present(self):
        md = self._render()
        self.assertIn("Navigation Failures", md)
        self.assertIn("Nav Fail Prof", md)

    def test_zero_member_section_present(self):
        md = self._render()
        self.assertIn("Zero Members Extracted", md)
        self.assertIn("Zero Member Prof", md)

    def test_root_cause_placeholder_present(self):
        md = self._render()
        self.assertIn(ROOT_CAUSE_PLACEHOLDER, md)

    def test_checklist_items_not_auto_checked(self):
        md = self._render()
        self.assertNotIn("- [x]", md)
        self.assertIn("- [ ]", md)

    def test_sorting_order_in_output(self):
        md = self._render()
        nav_fail_pos = md.index("Nav Fail Prof")
        zero_pos = md.index("Zero Member Prof")
        few_pos = md.index("Few Members Prof")
        good_pos = md.index("Good Prof")
        # Failures before successes; zero before non-zero; fewer before more
        self.assertLess(nav_fail_pos, zero_pos)
        self.assertLess(zero_pos, few_pos)
        self.assertLess(few_pos, good_pos)


# ── Tests: JSON rendering ─────────────────────────────────────────────────────


class TestRenderJson(unittest.TestCase):
    def _render(self) -> dict:
        records = sort_for_review([_make_record(), _make_record("Bob Jones")])
        stats = compute_stats(records)
        raw = render_json(records, stats, Path("test.json"))
        return json.loads(raw)

    def test_top_level_keys_present(self):
        data = self._render()
        for key in ("generated_at", "source", "stats", "review_categories", "professors"):
            self.assertIn(key, data)

    def test_review_categories_match_constant(self):
        data = self._render()
        self.assertEqual(data["review_categories"], list(REVIEW_CATEGORIES))

    def test_professors_list_length(self):
        data = self._render()
        self.assertEqual(len(data["professors"]), 2)

    def test_each_professor_has_root_cause(self):
        data = self._render()
        for p in data["professors"]:
            self.assertIn("root_cause", p)
            self.assertEqual(p["root_cause"], ROOT_CAUSE_PLACEHOLDER)

    def test_json_is_valid(self):
        records = [_make_record()]
        stats = compute_stats(records)
        raw = render_json(records, stats, Path("x.json"))
        parsed = json.loads(raw)
        self.assertIsInstance(parsed, dict)


if __name__ == "__main__":
    unittest.main()
