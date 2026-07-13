"""PR26 — DepartmentScopeDetector unit tests."""

from __future__ import annotations

import unittest

from research_group_agent.department_scope_detector import (
    DepartmentScopeDetector,
    DepartmentScopeResult,
    format_department_scope_log,
)
from research_group_agent.models import MemberRole, MemberStatus
from research_group_agent.parser import MemberPageEntry, MemberPageParser, ParsedMemberPage

FACULTY_DIRECTORY_HTML = """
<html><head><title>Faculty Directory</title></head><body>
  <h1>Faculty</h1>
  <ul>
    {faculty_rows}
  </ul>
</body></html>
"""

DEPARTMENT_PEOPLE_HTML = """
<html><head><title>Department People</title></head><body>
  <h1>All Members</h1>
  <ul>
    {rows}
  </ul>
</body></html>
"""

GRADUATE_DIRECTORY_HTML = """
<html><head><title>Graduate Students</title></head><body>
  <h1>Graduate Program</h1>
  <ul>
    {rows}
  </ul>
</body></html>
"""

INSTITUTE_DIRECTORY_HTML = """
<html><head><title>Institute Directory</title></head><body>
  <h1>Directory</h1>
  <ul>
    {rows}
  </ul>
</body></html>
"""

LAB_PAGE_HTML = """
<html><head><title>NetSys Lab</title></head><body>
  <h1>NetSys Lab Members</h1>
  <h2>Current Students</h2>
  <ul>
    <li><a href="https://example.edu/~alice/">Alice Chen</a> – PhD Student</li>
    <li><a href="https://example.edu/~bob/">Bob Smith</a> – Postdoc</li>
    <li><a href="https://example.edu/~carol/">Carol Lee</a> – PhD Student</li>
  </ul>
</body></html>
"""

HOMEPAGE_HTML = """
<html><head><title>Tianyin Xu</title></head><body>
  <h1>Tianyin Xu</h1>
  <h2>Students</h2>
  <p><a href="https://student1.example.edu/">Jane Doe</a> – PhD Student</p>
  <p><a href="https://student2.example.edu/">John Roe</a> – PhD Student</p>
</body></html>
"""

SMALL_LAB_HTML = """
<html><head><title>Small Systems Lab</title></head><body>
  <h1>Small Systems Lab</h1>
  <ul>
    <li><a href="https://lab.example.edu/~a/">Amy Alpha</a> – PhD Student</li>
    <li><a href="https://lab.example.edu/~b/">Ben Beta</a> – MS Student</li>
  </ul>
</body></html>
"""

RESEARCH_GROUP_HTML = """
<html><head><title>Princeton Systems Group</title></head><body>
  <h1>Princeton Systems Group</h1>
  <h2>Current Members</h2>
  <ul>
    <li><a href="https://example.edu/~jwang/">Jian Wang</a> – PhD Student</li>
    <li><a href="https://github.com/alicechen">Alice Chen</a> – Postdoc</li>
    <li><a href="https://scholar.google.com/citations?user=abc">Bob Smith</a> – Research Staff</li>
  </ul>
</body></html>
"""


def _faculty_rows(count: int) -> str:
    rows = []
    for index in range(count):
        rows.append(
            f'<li><a href="https://uni.edu/~prof{index}/">Prof {index} Smith</a>'
            f" – Associate Professor</li>"
        )
    return "\n".join(rows)


def _generic_rows(count: int, role: str = "PhD Student") -> str:
    rows = []
    for index in range(count):
        rows.append(
            f'<li><a href="https://uni.edu/~person{index}/">Person {index} Lee</a>'
            f" – {role}</li>"
        )
    return "\n".join(rows)


class TestDepartmentScopeDetectorPositive(unittest.TestCase):
    """Pages that should be classified as department-scale."""

    def setUp(self) -> None:
        self.detector = DepartmentScopeDetector()
        self.parser = MemberPageParser()

    def test_faculty_directory(self) -> None:
        html = FACULTY_DIRECTORY_HTML.format(faculty_rows=_faculty_rows(120))
        parsed = self.parser.parse(
            html,
            base_url="https://www.cs.university.edu/people/faculty/index.html",
        )
        result = self.detector.detect(
            parsed,
            page_url="https://www.cs.university.edu/people/faculty/index.html",
            page_title="Faculty Directory",
        )
        self.assertTrue(result.is_department_page)
        self.assertGreaterEqual(result.confidence, 0.70)
        self.assertIn("faculty keyword in URL", result.matched_rules)

    def test_large_roster_faculty_roles(self) -> None:
        entries = [
            MemberPageEntry(
                name=f"Prof {index} Smith",
                raw_text=f"Prof {index} Smith – Associate Professor",
                profile_url=f"https://uni.edu/~prof{index}/",
                role_hint="Associate Professor",
                section_role=MemberRole.PROFESSOR,
                in_member_section=True,
            )
            for index in range(124)
        ]
        parsed = ParsedMemberPage(page_title="Faculty Directory", entries=entries)
        result = self.detector.detect(
            parsed,
            page_url="https://www.cs.university.edu/people/faculty/index.html",
            page_title="Faculty Directory",
        )
        self.assertTrue(result.is_department_page)
        self.assertGreater(result.faculty_role_count, 20)
        self.assertIn("124 faculty roles", result.matched_rules)

    def test_department_people_page(self) -> None:
        html = DEPARTMENT_PEOPLE_HTML.format(rows=_generic_rows(110))
        parsed = self.parser.parse(
            html,
            base_url="https://www.eecs.university.edu/department/people/",
        )
        result = self.detector.detect(
            parsed,
            page_url="https://www.eecs.university.edu/department/people/",
            page_title="Department People",
        )
        self.assertTrue(result.is_department_page)
        self.assertIn("Department in page title", result.matched_rules)

    def test_graduate_directory(self) -> None:
        html = GRADUATE_DIRECTORY_HTML.format(rows=_generic_rows(150))
        parsed = self.parser.parse(
            html,
            base_url="https://csl.university.edu/directory/graduate-students",
        )
        result = self.detector.detect(
            parsed,
            page_url="https://csl.university.edu/directory/graduate-students",
            page_title="Graduate Students",
        )
        self.assertTrue(result.is_department_page)
        self.assertIn("graduate-students keyword in URL", result.matched_rules)

    def test_institute_member_directory(self) -> None:
        entries = [
            MemberPageEntry(
                name=f"Person {index} Lee",
                raw_text=f"Person {index} Lee – Research Staff",
                profile_url=f"https://uni.edu/~person{index}/",
                role_hint="Research Staff",
                in_member_section=True,
            )
            for index in range(80)
        ]
        parsed = ParsedMemberPage(page_title="Institute Directory", entries=entries)
        result = self.detector.detect(
            parsed,
            page_url="https://institute.university.edu/directory/staff/",
            page_title="Institute Directory",
        )
        self.assertTrue(result.is_department_page)
        self.assertGreaterEqual(result.parsed_entry_count, 50)


class TestDepartmentScopeDetectorNegative(unittest.TestCase):
    """Research-group pages that must not be flagged as department-scale."""

    def setUp(self) -> None:
        self.detector = DepartmentScopeDetector()
        self.parser = MemberPageParser()

    def test_scott_shenker_style_lab_page(self) -> None:
        parsed = self.parser.parse(
            LAB_PAGE_HTML,
            base_url="https://netsys.cs.berkeley.edu/people",
        )
        result = self.detector.detect(
            parsed,
            page_url="https://netsys.cs.berkeley.edu/people",
            page_title="NetSys Lab",
        )
        self.assertFalse(result.is_department_page)

    def test_tianyin_xu_homepage(self) -> None:
        parsed = self.parser.parse(
            HOMEPAGE_HTML,
            base_url="https://tianyin.github.io/",
        )
        result = self.detector.detect(
            parsed,
            page_url="https://tianyin.github.io/",
            page_title="Tianyin Xu",
        )
        self.assertFalse(result.is_department_page)

    def test_normal_research_group_page(self) -> None:
        parsed = self.parser.parse(
            RESEARCH_GROUP_HTML,
            base_url="https://example.edu/~prof/people.html",
        )
        result = self.detector.detect(
            parsed,
            page_url="https://example.edu/~prof/people.html",
            page_title="Princeton Systems Group",
        )
        self.assertFalse(result.is_department_page)

    def test_small_lab_homepage(self) -> None:
        parsed = self.parser.parse(
            SMALL_LAB_HTML,
            base_url="https://small-lab.example.edu/team/",
        )
        result = self.detector.detect(
            parsed,
            page_url="https://small-lab.example.edu/team/",
            page_title="Small Systems Lab",
        )
        self.assertFalse(result.is_department_page)


class TestDepartmentScopeDetectorRegression(unittest.TestCase):
    """Recognition-only guarantees — no extraction side effects."""

    def test_result_exposes_department_scope_alias(self) -> None:
        result = DepartmentScopeResult(
            is_department_page=True,
            confidence=0.9,
            matched_rules=["faculty keyword in URL"],
        )
        self.assertTrue(result.department_scope)
        payload = result.to_dict()
        self.assertTrue(payload["department_scope"])
        self.assertIn("faculty keyword in URL", payload["matched_rules"])

    def test_log_format_includes_required_fields(self) -> None:
        result = DepartmentScopeResult(
            is_department_page=True,
            confidence=0.96,
            matched_rules=["faculty keyword in URL", "870 parsed entries", "124 faculty roles"],
            page_url="https://www.cs.purdue.edu/people/faculty/index.html",
            parsed_entry_count=870,
            faculty_role_count=124,
        )
        text = format_department_scope_log("Pedro Fonseca 0001", result)
        self.assertIn("Department Scope Detector", text)
        self.assertIn("department_scope=True", text)
        self.assertIn("confidence=0.96", text)
        self.assertIn("faculty keyword", text)

    def test_detector_does_not_mutate_parsed_page(self) -> None:
        entry = MemberPageEntry(
            name="Alice Chen",
            raw_text="Alice Chen – PhD Student",
            profile_url="https://example.edu/~alice/",
            member_status=MemberStatus.CURRENT,
            section_role=MemberRole.PHD_STUDENT,
            in_member_section=True,
        )
        parsed = ParsedMemberPage(page_title="Lab", entries=[entry])
        original_len = len(parsed.entries)
        DepartmentScopeDetector().detect(parsed, "https://lab.example.edu/team/")
        self.assertEqual(len(parsed.entries), original_len)


if __name__ == "__main__":
    unittest.main()
