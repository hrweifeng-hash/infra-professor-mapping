"""PR29 — AdaptiveMemberLimiter unit and integration tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from research_group_agent.adaptive_member_limiter import (
    LEGACY_MEMBER_CAP,
    LARGE_CLEAN_GROUP_CAP,
    MEDIUM_DEPT_CAP,
    AdaptiveMemberLimiter,
    format_adaptive_member_limit_log,
)
from research_group_agent.department_scope_detector import DepartmentScopeResult
from research_group_agent.models import MemberRole, MemberStatus
from research_group_agent.parser import MemberPageEntry, ParsedMemberPage
from research_group_agent.providers.stub import StubResearchGroupProvider


_FIRST = (
    "Alice", "Bob", "Carol", "David", "Emma", "Frank", "Grace", "Henry",
    "Irene", "Jack", "Kate", "Leo", "Mia", "Noah", "Olivia", "Paul",
    "Quinn", "Rose", "Sam", "Tina", "Uma", "Victor", "Wendy", "Xavier",
    "Yara", "Zane", "Aaron", "Bella", "Caleb", "Diana", "Ethan", "Fiona",
    "George", "Hannah", "Isaac", "Julia", "Kevin", "Laura", "Mason", "Nina",
    "Oscar", "Paula", "Ryan", "Sara", "Tyler", "Ursula", "Vince", "Willa",
    "Xander", "Yvonne", "Zach", "Abigail", "Benjamin", "Chloe", "Daniel",
    "Elena", "Felix", "Gina", "Harvey", "Iris", "Jacob", "Kylie", "Liam",
    "Maya", "Nathan", "Owen", "Penny", "Quincy", "Rachel", "Simon", "Tara",
)
_LAST = (
    "Chen", "Smith", "Lee", "Wang", "Kim", "Patel", "Brown", "Davis",
    "Miller", "Wilson", "Moore", "Taylor", "Anderson", "Thomas", "Jackson",
    "White", "Harris", "Martin", "Thompson", "Garcia", "Martinez", "Robinson",
    "Clark", "Rodriguez", "Lewis", "Walker", "Hall", "Allen", "Young", "King",
)


def _entries(count: int) -> list[MemberPageEntry]:
    entries: list[MemberPageEntry] = []
    for index in range(count):
        name = f"{_FIRST[index % len(_FIRST)]} {_LAST[index % len(_LAST)]}"
        entries.append(
            MemberPageEntry(
                name=name,
                profile_url=f"https://lab.example.edu/~user{index}/",
                section_name="Students",
                section_role=MemberRole.PHD_STUDENT,
                member_status=MemberStatus.CURRENT,
                in_member_section=True,
                role_hint="PhD Student",
                raw_text=f"{name} – PhD Student",
            )
        )
    return entries


def _scope(*, department: bool, confidence: float) -> DepartmentScopeResult:
    return DepartmentScopeResult(
        is_department_page=department,
        confidence=confidence,
        matched_rules=["test"],
        page_url="https://example.edu/page",
        parsed_entry_count=0,
    )


class TestAdaptiveMemberLimiterRules(unittest.TestCase):
    def setUp(self) -> None:
        self.limiter = AdaptiveMemberLimiter()

    def test_clean_group_no_cap(self):
        parsed = ParsedMemberPage(page_title="NetSys Lab", entries=_entries(35))
        result = self.limiter.compute(parsed, _scope(department=False, confidence=0.1))
        self.assertTrue(result.unlimited)
        self.assertIn("clean_research_group", result.rules_applied)

    def test_very_small_group_no_cap(self):
        parsed = ParsedMemberPage(page_title="Small Lab", entries=_entries(12))
        result = self.limiter.compute(parsed, _scope(department=False, confidence=0.1))
        self.assertTrue(result.unlimited)
        self.assertIn("very_small_group", result.rules_applied)

    def test_large_clean_group_cap_60(self):
        parsed = ParsedMemberPage(page_title="Big Lab", entries=_entries(75))
        result = self.limiter.compute(parsed, _scope(department=False, confidence=0.1))
        self.assertFalse(result.unlimited)
        self.assertEqual(result.member_limit, LARGE_CLEAN_GROUP_CAP)
        self.assertIn("large_clean_group", result.rules_applied)

    def test_department_high_confidence_cap_20(self):
        parsed = ParsedMemberPage(page_title="Faculty Directory", entries=_entries(100))
        result = self.limiter.compute(parsed, _scope(department=True, confidence=0.85))
        self.assertEqual(result.member_limit, LEGACY_MEMBER_CAP)
        self.assertIn("department_high_confidence", result.rules_applied)

    def test_medium_confidence_department_cap_30(self):
        parsed = ParsedMemberPage(page_title="Department People", entries=_entries(80))
        result = self.limiter.compute(parsed, _scope(department=True, confidence=0.55))
        self.assertEqual(result.member_limit, MEDIUM_DEPT_CAP)
        self.assertIn("medium_confidence_department", result.rules_applied)

    def test_department_overrides_small_group_rule(self):
        parsed = ParsedMemberPage(page_title="Faculty", entries=_entries(10))
        result = self.limiter.compute(parsed, _scope(department=True, confidence=0.9))
        self.assertEqual(result.member_limit, LEGACY_MEMBER_CAP)
        self.assertFalse(result.unlimited)


class TestAdaptiveMemberLimitLog(unittest.TestCase):
    def test_log_format_includes_required_fields(self):
        from research_group_agent.adaptive_member_limiter import AdaptiveMemberLimitResult

        text = format_adaptive_member_limit_log(
            professor_name="Alice Smith",
            parsed_members=45,
            exported_members=20,
            limit_result=AdaptiveMemberLimitResult(
                member_limit=20,
                confidence="High",
                reason="test cap",
                rules_applied=["department_high_confidence"],
            ),
        )
        self.assertIn("professor=Alice Smith", text)
        self.assertIn("parsed_members=45", text)
        self.assertIn("exported_members=20", text)
        self.assertIn("applied_limit=20", text)
        self.assertIn("confidence=High", text)


class TestStubProviderIntegration(unittest.TestCase):
    def test_clean_group_exports_beyond_legacy_cap(self):
        parsed = ParsedMemberPage(page_title="Systems Lab", entries=_entries(27))
        scope = _scope(department=False, confidence=0.1)
        result = StubResearchGroupProvider().extract_members(
            "",
            parsed,
            "Advisor Name",
            page_url="https://lab.example.edu/members",
            department_scope=scope,
        )
        self.assertEqual(len(result.members), 27)
        self.assertTrue(result.adaptive_limit_unlimited)

    def test_department_page_stays_capped(self):
        parsed = ParsedMemberPage(page_title="Faculty Directory", entries=_entries(35))
        scope = _scope(department=True, confidence=0.85)
        result = StubResearchGroupProvider().extract_members(
            "",
            parsed,
            "Advisor Name",
            page_url="https://www.cs.example.edu/people/faculty/",
            department_scope=scope,
        )
        self.assertEqual(len(result.members), LEGACY_MEMBER_CAP)
        self.assertFalse(result.adaptive_limit_unlimited)
        self.assertEqual(result.adaptive_member_limit, LEGACY_MEMBER_CAP)

    def test_large_clean_group_capped_at_60(self):
        parsed = ParsedMemberPage(page_title="Huge Lab", entries=_entries(70))
        scope = _scope(department=False, confidence=0.1)
        result = StubResearchGroupProvider().extract_members(
            "",
            parsed,
            "Advisor Name",
            page_url="https://lab.example.edu/team",
            department_scope=scope,
        )
        self.assertEqual(len(result.members), LARGE_CLEAN_GROUP_CAP)

    def test_small_group_uncapped(self):
        parsed = ParsedMemberPage(page_title="Tiny Lab", entries=_entries(8))
        scope = _scope(department=False, confidence=0.1)
        result = StubResearchGroupProvider().extract_members(
            "",
            parsed,
            "Advisor Name",
            department_scope=scope,
        )
        self.assertEqual(len(result.members), 8)
        self.assertTrue(result.adaptive_limit_unlimited)

    def test_medium_confidence_department_cap_30(self):
        parsed = ParsedMemberPage(page_title="Graduate Students", entries=_entries(40))
        scope = _scope(department=True, confidence=0.55)
        result = StubResearchGroupProvider().extract_members(
            "",
            parsed,
            "Advisor Name",
            page_url="https://www.cs.example.edu/directory/graduate-students",
            department_scope=scope,
        )
        self.assertEqual(len(result.members), MEDIUM_DEPT_CAP)


class TestRegression(unittest.TestCase):
    def test_legacy_cap_constant_unchanged(self):
        self.assertEqual(StubResearchGroupProvider.MAX_MEMBERS_PER_GROUP, LEGACY_MEMBER_CAP)

    def test_zero_members_no_error(self):
        parsed = ParsedMemberPage(page_title="Empty", entries=[])
        scope = _scope(department=False, confidence=0.0)
        result = StubResearchGroupProvider().extract_members(
            "",
            parsed,
            "Advisor Name",
            department_scope=scope,
        )
        self.assertEqual(result.members, [])


if __name__ == "__main__":
    unittest.main()
