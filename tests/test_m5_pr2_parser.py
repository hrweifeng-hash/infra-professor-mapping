"""M5-PR2 — Deep member page parser tests."""

from __future__ import annotations

import unittest

from research_group_agent.deep_member_extractor import DeepMemberExtractor
from research_group_agent.parser import MemberPageParser
from tests.test_research_group_agent import (
    BOOTSTRAP_CARD_HTML,
    H34_IN_MEMBER_SECTION_HTML,
    MEMBER_PAGE_HTML,
    SIMPLE_PARAGRAPH_MEMBERS_HTML,
)

DEFINITION_LIST_HTML = """
<html><body>
  <h2>Graduate Students</h2>
  <dl>
    <dt><a href="https://example.edu/~alice">Alice Wang</a></dt>
    <dd>PhD Student | Advisor: Prof Smith | alice@example.edu</dd>
    <dt><a href="https://example.edu/~bob">Bob Chen</a></dt>
    <dd>Postdoc Researcher</dd>
    <dt><a href="https://example.edu/~carol">Carol Davis</a></dt>
    <dd>Research Staff</dd>
  </dl>
</body></html>
"""

TABLE_DIRECTORY_HTML = """
<html><body>
  <h2>Researchers</h2>
  <table>
    <tr><td><a href="https://example.edu/~dan">Dan Kim</a></td><td>PhD Student</td></tr>
    <tr><td><a href="https://example.edu/~eva">Eva Martinez</a></td><td>Postdoc</td></tr>
    <tr><td><a href="https://example.edu/~frank">Frank Liu</a></td><td>Research Staff</td></tr>
  </table>
</body></html>
"""

BOOTSTRAP_GRID_HTML = """
<html><body>
  <h2>Lab Members</h2>
  <div class="row">
    <div class="card profile-tile">
      <div class="media-body">
        <h4><a href="https://example.edu/~gina">Gina Park</a></h4>
        <p>Graduate Student</p>
      </div>
    </div>
    <div class="card profile-tile">
      <h4><a href="https://example.edu/~henry">Henry Lee</a></h4>
      <p>Postdoc</p>
    </div>
    <div class="card profile-tile">
      <h4><a href="https://example.edu/~iris">Iris Chen</a></h4>
      <p>Research Staff</p>
    </div>
  </div>
</body></html>
"""

ACCORDION_HTML = """
<html><body>
  <h2>Current Members</h2>
  <div class="accordion">
    <div class="panel">
      <p><a href="https://example.edu/~jack">Jack Miller</a> — PhD Student</p>
    </div>
    <div class="panel">
      <p><a href="https://example.edu/~kate">Kate Wilson</a> — Postdoc</p>
    </div>
    <div class="panel">
      <p><a href="https://example.edu/~leo">Leo Brown</a> — Research Staff</p>
    </div>
  </div>
</body></html>
"""

TAB_PANEL_HTML = """
<html><body>
  <h2>Research Team</h2>
  <div class="tab-pane">
    <p><a href="https://example.edu/~mia">Mia Johnson</a>, PhD Student</p>
    <p><a href="https://example.edu/~noah">Noah Davis</a>, Postdoc</p>
    <p><a href="https://example.edu/~olivia">Olivia White</a>, Research Staff</p>
  </div>
</body></html>
"""

PROFILE_CARD_GRID_HTML = """
<html><body>
  <h2>People Directory</h2>
  <a href="/people#alice-wang"><img alt="Alice Wang" src="/img/a.jpg"></a>
  <a href="/people#bob-chen"><img alt="Bob Chen" src="/img/b.jpg"></a>
  <a href="/people#carol-davis"><img alt="Carol Davis" src="/img/c.jpg"></a>
  <a href="/people#dan-kim"><img alt="Dan Kim" src="/img/d.jpg"></a>
</body></html>
"""

SIDEBAR_NOISE_HTML = """
<html><body>
  <aside class="sidebar widget">
    <a href="https://example.edu/~noise">Sidebar Person</a>
  </aside>
  <h2>Students</h2>
  <ul>
    <li><a href="https://example.edu/~real1">Real One</a> — PhD Student</li>
    <li><a href="https://example.edu/~real2">Real Two</a> — PhD Student</li>
  </ul>
</body></html>
"""

ALUMNI_SECTION_HTML = """
<html><body>
  <h2>Alumni</h2>
  <dl>
    <dt><a href="https://example.edu/~past1">Past One</a></dt>
    <dd>Former PhD Student</dd>
    <dt><a href="https://example.edu/~past2">Past Two</a></dt>
    <dd>Former Postdoc</dd>
    <dt><a href="https://example.edu/~past3">Past Three</a></dt>
    <dd>Alumni Researcher</dd>
  </dl>
</body></html>
"""

VISITOR_SECTION_HTML = """
<html><body>
  <h2>Visitors</h2>
  <p><a href="https://example.edu/~vis1">Visitor One</a> — Visiting Researcher</p>
  <p><a href="https://example.edu/~vis2">Visitor Two</a> — Visiting Scholar</p>
  <p><a href="https://example.edu/~vis3">Visitor Three</a> — Visiting Student</p>
</body></html>
"""

GITHUB_LINKS_HTML = """
<html><body>
  <h2>Affiliated Students</h2>
  <div class="card member">
    <a href="https://github.com/alicecodes">Alice Wang</a> — PhD Student
  </div>
  <div class="card member">
    <a href="https://github.com/bobcodes">Bob Chen</a> — Graduate Student
  </div>
  <div class="card member">
    <a href="https://github.com/carolcodes">Carol Davis</a> — Research Staff
  </div>
</body></html>
"""


class TestDeepMemberExtractor(unittest.TestCase):
    def _extract(self, html: str, base_url: str = "https://example.edu/people") -> list:
        seen: set[str] = set()
        return DeepMemberExtractor().extract(html, base_url, seen)

    def test_definition_list_extracts_three_members(self):
        entries = self._extract(DEFINITION_LIST_HTML)
        names = {entry.name for entry in entries}
        self.assertIn("Alice Wang", names)
        self.assertGreaterEqual(len(entries), 3)

    def test_definition_list_captures_advisor_and_email(self):
        entries = self._extract(DEFINITION_LIST_HTML)
        alice = next(entry for entry in entries if entry.name == "Alice Wang")
        self.assertIn("advisor", (alice.raw_text or "").lower())
        self.assertIn("@example.edu", alice.raw_text or "")

    def test_table_directory_extracts_rows(self):
        entries = self._extract(TABLE_DIRECTORY_HTML)
        self.assertGreaterEqual(len(entries), 3)

    def test_bootstrap_grid_extracts_cards(self):
        entries = self._extract(BOOTSTRAP_GRID_HTML)
        self.assertGreaterEqual(len(entries), 3)

    def test_accordion_panel_extracts_members(self):
        entries = self._extract(ACCORDION_HTML)
        self.assertGreaterEqual(len(entries), 3)

    def test_tab_panel_extracts_members(self):
        entries = self._extract(TAB_PANEL_HTML)
        self.assertGreaterEqual(len(entries), 3)

    def test_profile_card_grid_threshold(self):
        entries = self._extract(PROFILE_CARD_GRID_HTML)
        self.assertGreaterEqual(len(entries), 3)

    def test_deduplicates_names(self):
        html = DEFINITION_LIST_HTML + "<p>Alice Wang — duplicate</p>"
        entries = self._extract(html)
        self.assertEqual(sum(1 for entry in entries if entry.name == "Alice Wang"), 1)

    def test_alumni_section_supported(self):
        entries = self._extract(ALUMNI_SECTION_HTML)
        self.assertGreaterEqual(len(entries), 3)

    def test_visitor_section_supported(self):
        entries = self._extract(VISITOR_SECTION_HTML)
        self.assertGreaterEqual(len(entries), 3)

    def test_github_links_supported(self):
        entries = self._extract(GITHUB_LINKS_HTML)
        self.assertGreaterEqual(len(entries), 3)


class TestMemberPageParserDeepPass(unittest.TestCase):
    def _parse(self, html: str, base_url: str = "https://example.edu/people") -> object:
        return MemberPageParser().parse(html, base_url)

    def test_deep_member_count_on_definition_list(self):
        parsed = self._parse(DEFINITION_LIST_HTML)
        self.assertGreater(parsed.deep_member_count, 0)
        self.assertGreaterEqual(len(parsed.entries), 3)

    def test_profile_cards_merged_via_deep_pass(self):
        parsed = self._parse(PROFILE_CARD_GRID_HTML)
        self.assertGreater(parsed.deep_member_count, 0)
        self.assertEqual(parsed.repeated_profiles, [])

    def test_sidebar_person_ignored(self):
        parsed = self._parse(SIDEBAR_NOISE_HTML)
        names = {entry.name for entry in parsed.entries}
        self.assertNotIn("Sidebar Person", names)

    def test_regression_member_page_html_unchanged(self):
        parsed = self._parse(MEMBER_PAGE_HTML, "https://example.edu/lab")
        names = {entry.name for entry in parsed.entries}
        self.assertIn("Jian Wang", names)
        self.assertIn("Alice Chen", names)

    def test_regression_bootstrap_cards_still_work(self):
        parsed = self._parse(BOOTSTRAP_CARD_HTML, "https://rise.cs.berkeley.edu/people/")
        names = {entry.name for entry in parsed.entries}
        self.assertIn("Alice Wang", names)
        self.assertIn("Bob Chen", names)

    def test_regression_heading_cards_still_work(self):
        parsed = self._parse(H34_IN_MEMBER_SECTION_HTML, "https://example.edu/lab")
        names = {entry.name for entry in parsed.entries}
        self.assertIn("Dan Kim", names)
        self.assertGreaterEqual(parsed.heading_card_count, 3)

    def test_regression_paragraph_members_still_work(self):
        parsed = self._parse(
            SIMPLE_PARAGRAPH_MEMBERS_HTML,
            "https://example.edu/~tianyin/",
        )
        self.assertGreaterEqual(parsed.paragraph_member_count, 3)

    def test_section_label_deep_member(self):
        parsed = self._parse(DEFINITION_LIST_HTML)
        deep_entries = [entry for entry in parsed.entries if entry.section_name]
        self.assertTrue(deep_entries)


class TestDeepLayoutCombinations(unittest.TestCase):
    def test_mixed_heading_and_definition_list(self):
        html = """
        <html><body>
          <h2>Current Members</h2>
          <ul><li><a href="https://example.edu/~one">List One</a></li></ul>
          <h2>Postdocs</h2>
          <dl>
            <dt><a href="https://example.edu/~two">Post Two</a></dt><dd>Postdoc</dd>
            <dt><a href="https://example.edu/~three">Post Three</a></dt><dd>Postdoc</dd>
            <dt><a href="https://example.edu/~four">Post Four</a></dt><dd>Postdoc</dd>
          </dl>
        </body></html>
        """
        parsed = MemberPageParser().parse(html, "https://example.edu/lab")
        names = {entry.name for entry in parsed.entries}
        self.assertIn("List One", names)
        self.assertIn("Post Two", names)

    def test_research_staff_section(self):
        html = """
        <html><body>
          <h2>Research Staff</h2>
          <p><a href="https://example.edu/~staff1">Staff One</a></p>
          <p><a href="https://example.edu/~staff2">Staff Two</a></p>
          <p><a href="https://example.edu/~staff3">Staff Three</a></p>
        </body></html>
        """
        parsed = MemberPageParser().parse(html, "https://example.edu/lab")
        self.assertGreaterEqual(len(parsed.entries), 3)

    def test_student_directory_heading(self):
        html = """
        <html><body>
          <h2>Student Directory</h2>
          <p><a href="https://example.edu/~s1">Student One</a>, PhD Student</p>
          <p><a href="https://example.edu/~s2">Student Two</a>, PhD Student</p>
          <p><a href="https://example.edu/~s3">Student Three</a>, PhD Student</p>
        </body></html>
        """
        parsed = MemberPageParser().parse(html, "https://example.edu/lab")
        self.assertGreaterEqual(len(parsed.entries), 3)


if __name__ == "__main__":
    unittest.main()
