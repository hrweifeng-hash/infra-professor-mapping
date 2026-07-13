"""
PR25 — Navigation Quality Improvement: regression tests.

Positive:
  ✓ people page beats faculty page
  ✓ members page beats collaborator page
  ✓ students page beats department page

Negative:
  ✓ existing homepage-first behaviour unchanged
  ✓ PR24 paragraph recognition unchanged
  ✓ no ranking regressions on known-good candidates
"""

from __future__ import annotations

import unittest

from research_group_agent.candidate_page import (
    CandidatePage,
    CandidatePageRanker,
    NavigationGuard,
    PAGE_TYPE_HOMEPAGE,
    PAGE_TYPE_LAB,
    PAGE_TYPE_MEMBERS,
    PAGE_TYPE_OTHER,
    PAGE_TYPE_PEOPLE,
    PAGE_TYPE_STUDENTS,
    RankingBonusConfig,
)
from research_group_agent.homepage_member_detector import (
    HomepageMemberDetector,
    MIN_PARAGRAPH_STRUCTURE_COUNT,
)
from research_group_agent.models import PIPELINE_VERSION
from research_group_agent.page_classifier import PageClassifier
from research_group_agent.parser import MemberPageParser

from tests.test_pr22_homepage_navigation import (
    _HOMEPAGE_WITH_MEMBERS,
    _make_professor,
)
from tests.test_pr24_paragraph_layout_recognition import (
    _PARAGRAPH_ONLY_MEMBER_PAGE,
)


class TestPR25RankingPositive(unittest.TestCase):
    """PR25 positive ranking tests."""

    def _rank(self, *candidates: CandidatePage) -> list[CandidatePage]:
        return CandidatePageRanker(enable_navigation_evidence=False).rank(list(candidates))

    def test_people_page_beats_faculty_page(self):
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
        ranked = self._rank(people, faculty)
        self.assertEqual(ranked[0].url, people.url)
        self.assertGreater(ranked[0].score, ranked[1].score)

    def test_members_page_beats_collaborator_page(self):
        members = CandidatePage(
            url="https://ada.example.edu/lab/members",
            page_type=PAGE_TYPE_MEMBERS,
            anchor_text="Current Members",
            graph_confidence=0.85,
        )
        collaborator = CandidatePage(
            url="https://cs.university.edu/people/frank-castle",
            page_type=PAGE_TYPE_OTHER,
            anchor_text="Frank Castle",
            graph_confidence=0.8,
        )
        ranker = CandidatePageRanker(enable_navigation_evidence=False)
        members_scored = ranker.rank([members], min_score=0.0)[0]
        collab_scored = ranker.rank([collaborator], min_score=0.0)[0]
        self.assertGreater(members_scored.score, collab_scored.score)

    def test_students_page_beats_department_page(self):
        students = CandidatePage(
            url="https://ada.example.edu/students.html",
            page_type=PAGE_TYPE_STUDENTS,
            anchor_text="PhD Students",
            graph_confidence=0.8,
        )
        department = CandidatePage(
            url="https://cs.university.edu/academics/undergraduate",
            page_type=PAGE_TYPE_OTHER,
            anchor_text="Undergraduate Program",
            graph_confidence=0.75,
        )
        ranker = CandidatePageRanker(enable_navigation_evidence=False)
        students_scored = ranker.rank([students], min_score=0.0)[0]
        dept_scored = ranker.rank([department], min_score=0.0)[0]
        self.assertGreater(students_scored.score, dept_scored.score)

    def test_ranking_evidence_includes_explainability_fields(self):
        ranker = CandidatePageRanker(enable_navigation_evidence=False)
        candidate = CandidatePage(
            url="https://ada.example.edu/people.html",
            page_type=PAGE_TYPE_PEOPLE,
            anchor_text="People",
            graph_confidence=0.8,
        )
        scored = ranker.rank([candidate])[0]
        evidence = " ".join(scored.evidence)
        self.assertIn("rank_type:", evidence)
        self.assertIn("rank_anchor:", evidence)
        self.assertIn("rank_penalty:", evidence)
        self.assertIn("rank_final:", evidence)


class TestPR25RankingNegative(unittest.TestCase):
    """PR25 negative / regression tests."""

    def test_homepage_first_behaviour_unchanged(self):
        """Homepage with members must still be selected as the primary group page."""
        import tests.test_pr22_homepage_navigation as nav_tests

        pipeline = nav_tests.TestPipelineHomepageFirst()._make_pipeline(
            nav_tests._HOMEPAGE_WITH_MEMBERS
        )
        professor = nav_tests._make_professor()
        graph = pipeline.analyze(professor, professor.homepage_graph)

        self.assertGreater(graph.member_count, 0)
        self.assertIsNotNone(graph.group_page)
        self.assertEqual(
            graph.group_page.url.rstrip("/"),
            professor.homepage_graph.canonical_homepage.rstrip("/"),
        )

    def test_pr24_paragraph_recognition_unchanged(self):
        """Paragraph layout detection from PR24 must remain intact."""
        detector = HomepageMemberDetector()
        result = detector.detect(_PARAGRAPH_ONLY_MEMBER_PAGE, "https://example.edu/")
        self.assertTrue(result.has_paragraph_layout)
        self.assertGreaterEqual(
            result.parsed.paragraph_member_count if result.parsed else 0,
            MIN_PARAGRAPH_STRUCTURE_COUNT,
        )

        parser = MemberPageParser()
        parsed = parser.parse(_PARAGRAPH_ONLY_MEMBER_PAGE, base_url="https://example.edu/")
        classifier = PageClassifier()
        classification = classifier.classify(
            parsed=parsed,
            page_url="https://example.edu/",
            page_title="Lab Members",
        )
        self.assertTrue(classification.is_acceptable)

    def test_lab_page_still_beats_homepage(self):
        ranker = CandidatePageRanker(enable_navigation_evidence=False)
        lab = CandidatePage(
            url="https://ada.example.edu/lab/",
            page_type=PAGE_TYPE_LAB,
            graph_confidence=0.9,
        )
        home = CandidatePage(
            url="https://ada.example.edu/",
            page_type=PAGE_TYPE_HOMEPAGE,
            graph_confidence=1.0,
        )
        ranked = ranker.rank([lab, home])
        self.assertEqual(ranked[0].page_type, PAGE_TYPE_LAB)

    def test_navigation_guard_never_removes_candidates(self):
        guard = NavigationGuard()
        candidates = [
            CandidatePage(url="https://ada.example.edu/lab/", page_type=PAGE_TYPE_LAB, score=0.9),
            CandidatePage(url="https://ada.example.edu/teaching/", page_type=PAGE_TYPE_OTHER, score=0.8),
            CandidatePage(url="https://ada.example.edu/cv", page_type=PAGE_TYPE_OTHER, score=0.7),
        ]
        result = guard.filter(candidates)
        self.assertEqual(len(result), len(candidates))

    def test_configurable_bonus_amounts(self):
        config = RankingBonusConfig(
            url_bonuses=(("people", 0.50),),
            anchor_bonuses=(),
            max_total_bonus=0.50,
        )
        ranker = CandidatePageRanker(bonus_config=config, enable_navigation_evidence=False)
        candidate = CandidatePage(
            url="https://ada.example.edu/people.html",
            page_type=PAGE_TYPE_PEOPLE,
        )
        scored = ranker.rank([candidate])[0]
        self.assertIn("rank_anchor:+0.50", scored.evidence)

    def test_pipeline_version_is_pr32(self):
        self.assertEqual(PIPELINE_VERSION, "PR32")


class TestNavigationGuardPR25Expansion(unittest.TestCase):
    """Unit tests for PR25 NavigationGuard pattern expansion."""

    def setUp(self):
        self.guard = NavigationGuard()

    def _penalty(self, url: str, anchor: str = "") -> float:
        cand = CandidatePage(url=url, page_type=PAGE_TYPE_OTHER, anchor_text=anchor)
        amount, _ = self.guard.compute_penalty(cand)
        return amount

    def test_staff_page_penalised(self):
        self.assertGreater(self._penalty("https://cs.university.edu/staff/"), 0)

    def test_administration_page_penalised(self):
        self.assertGreater(self._penalty("https://cs.university.edu/administration/"), 0)

    def test_people_without_member_keywords_penalised(self):
        self.assertGreater(
            self._penalty("https://cs.university.edu/people/", anchor="Directory"),
            0,
        )

    def test_people_with_member_keywords_not_penalised(self):
        self.assertEqual(
            self._penalty(
                "https://ada.example.edu/people/members",
                anchor="Current Members",
            ),
            0,
        )

    def test_collaborator_people_page_penalised(self):
        self.assertGreater(
            self._penalty(
                "https://cs.university.edu/people/frank-castle",
                anchor="Frank Castle",
            ),
            0,
        )

    def test_syllabus_penalised(self):
        self.assertGreater(self._penalty("https://ada.example.edu/syllabus"), 0)


if __name__ == "__main__":
    unittest.main()
