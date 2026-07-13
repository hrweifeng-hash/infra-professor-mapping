"""
PR30 — Navigation Evidence Ranking: regression tests.

Positive:
  ✓ professor subpage with member evidence beats department directory
  ✓ ownership score dominates URL-only page type for department pages
  ✓ member evidence boosts professor-owned pages

Negative:
  ✓ PR25 scoring preserved when enable_navigation_evidence=False
  ✓ lab page still beats homepage
"""

from __future__ import annotations

import unittest

from research_group_agent.candidate_page import (
    CandidatePage,
    CandidatePageRanker,
    NavigationEvidence,
    NavigationEvidenceAnalyzer,
    NavigationGuard,
    NavigationOwnership,
    PAGE_TYPE_HOMEPAGE,
    PAGE_TYPE_LAB,
    PAGE_TYPE_MEMBERS,
    PAGE_TYPE_OTHER,
    PAGE_TYPE_PEOPLE,
    PAGE_TYPE_STUDENTS,
)
from research_group_agent.models import PIPELINE_VERSION


class TestPR30NavigationEvidence(unittest.TestCase):
    """PR30 positive ranking tests with navigation evidence enabled."""

    def _rank(self, *candidates: CandidatePage, homepage: str | None = None) -> list[CandidatePage]:
        return CandidatePageRanker(enable_navigation_evidence=True).rank(
            list(candidates),
            min_score=0.0,
            professor_homepage=homepage,
        )

    def test_professor_subpage_beats_department_directory(self):
        members = CandidatePage(
            url="https://ada.example.edu/lab/members",
            page_type=PAGE_TYPE_MEMBERS,
            anchor_text="Current Members",
            graph_confidence=0.85,
            navigation_evidence=NavigationEvidence(
                ownership=NavigationOwnership.PROFESSOR_SUBPAGE,
                member_sections=2,
                heading_cards=5,
                current_student_keywords=2,
            ),
        )
        department = CandidatePage(
            url="https://cs.university.edu/people/faculty",
            page_type=PAGE_TYPE_LAB,
            anchor_text="Faculty Directory",
            graph_confidence=0.90,
            navigation_evidence=NavigationEvidence(
                ownership=NavigationOwnership.DEPARTMENT,
                is_directory_page=True,
                directory_reason="department_path",
            ),
        )
        ranked = self._rank(members, department, homepage="https://ada.example.edu/")
        self.assertEqual(ranked[0].url, members.url)
        self.assertGreater(ranked[0].score, ranked[1].score)

    def test_member_evidence_boosts_professor_homepage(self):
        homepage = CandidatePage(
            url="https://ada.example.edu/",
            page_type=PAGE_TYPE_HOMEPAGE,
            graph_confidence=1.0,
            navigation_evidence=NavigationEvidence(
                ownership=NavigationOwnership.PROFESSOR_HOMEPAGE,
                member_sections=3,
                repeated_profiles=6,
                heading_cards=4,
                paragraph_members=3,
                current_student_keywords=2,
            ),
        )
        dept = CandidatePage(
            url="https://cs.university.edu/academics/undergraduate",
            page_type=PAGE_TYPE_LAB,
            graph_confidence=0.85,
            navigation_evidence=NavigationEvidence(
                ownership=NavigationOwnership.DEPARTMENT,
                is_directory_page=True,
                directory_reason="department_path",
            ),
        )
        ranked = self._rank(homepage, dept, homepage="https://ada.example.edu/")
        self.assertEqual(ranked[0].url, homepage.url)

    def test_evidence_fields_in_ranking_output(self):
        ranker = CandidatePageRanker(enable_navigation_evidence=True)
        candidate = CandidatePage(
            url="https://ada.example.edu/students.html",
            page_type=PAGE_TYPE_STUDENTS,
            navigation_evidence=NavigationEvidence(
                ownership=NavigationOwnership.PROFESSOR_SUBPAGE,
                current_student_keywords=3,
            ),
        )
        scored = ranker.rank([candidate], min_score=0.0)[0]
        evidence = " ".join(scored.evidence)
        self.assertIn("ownership:", evidence)
        self.assertIn("rank_ownership:", evidence)
        self.assertIn("rank_member_evidence:", evidence)
        self.assertIn("rank_final:", evidence)

    def test_analyzer_builds_evidence_from_html(self):
        html = """
        <html><body>
        <h2>Current PhD Students</h2>
        <ul><li>Alice Smith</li><li>Bob Jones</li><li>Carol Lee</li></ul>
        <h2>Postdocs</h2>
        <ul><li>Dan Wu</li></ul>
        </body></html>
        """
        evidence = NavigationEvidenceAnalyzer().analyze(
            url="https://ada.example.edu/members.html",
            professor_homepage="https://ada.example.edu/",
            page_type=PAGE_TYPE_MEMBERS,
            html=html,
        )
        self.assertTrue(evidence.html_available)
        self.assertGreater(evidence.current_student_keywords, 0)
        self.assertIn(
            evidence.ownership,
            {
                NavigationOwnership.PROFESSOR_SUBPAGE,
                NavigationOwnership.LAB_HOMEPAGE,
                NavigationOwnership.PROFESSOR_HOMEPAGE,
            },
        )


class TestPR30BackwardCompatibility(unittest.TestCase):
    """Ensure PR25 scoring is unchanged when evidence is disabled."""

    def test_pr25_scoring_preserved_without_evidence(self):
        ranker = CandidatePageRanker(enable_navigation_evidence=False)
        people = CandidatePage(
            url="https://ada.example.edu/people.html",
            page_type=PAGE_TYPE_PEOPLE,
            anchor_text="People",
            graph_confidence=0.8,
        )
        faculty = CandidatePage(
            url="https://cs.university.edu/faculty?type=all",
            page_type=PAGE_TYPE_PEOPLE,
            anchor_text="Faculty Directory",
            graph_confidence=0.85,
        )
        ranked = ranker.rank([people, faculty], min_score=0.0)
        self.assertEqual(ranked[0].url, people.url)

    def test_lab_page_still_beats_homepage(self):
        ranker = CandidatePageRanker(enable_navigation_evidence=True)
        lab = CandidatePage(
            url="https://ada.example.edu/lab/",
            page_type=PAGE_TYPE_LAB,
            graph_confidence=0.9,
            navigation_evidence=NavigationEvidence(
                ownership=NavigationOwnership.LAB_HOMEPAGE,
                member_sections=2,
            ),
        )
        home = CandidatePage(
            url="https://ada.example.edu/",
            page_type=PAGE_TYPE_HOMEPAGE,
            graph_confidence=1.0,
            navigation_evidence=NavigationEvidence(
                ownership=NavigationOwnership.PROFESSOR_HOMEPAGE,
            ),
        )
        ranked = ranker.rank([lab, home], min_score=0.0, professor_homepage=home.url)
        self.assertEqual(ranked[0].page_type, PAGE_TYPE_LAB)

    def test_navigation_guard_accepts_evidence(self):
        guard = NavigationGuard()
        candidate = CandidatePage(
            url="https://cs.university.edu/",
            page_type=PAGE_TYPE_OTHER,
        )
        evidence = NavigationEvidence(
            ownership=NavigationOwnership.UNIVERSITY,
            is_directory_page=True,
            directory_reason="directory_title",
            member_sections=2,
        )
        penalty, rules = guard.compute_penalty(candidate, navigation_evidence=evidence)
        self.assertGreater(penalty, 0)
        self.assertTrue(any("nav_evidence:" in r for r in rules))

    def test_pipeline_version_is_pr30(self):
        self.assertEqual(PIPELINE_VERSION, "PR32")


if __name__ == "__main__":
    unittest.main()
