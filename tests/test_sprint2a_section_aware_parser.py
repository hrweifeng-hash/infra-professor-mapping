"""Sprint 2A — SectionAwareParser plain-text section heading tests."""

from __future__ import annotations

import unittest

from research_group_agent.models import MemberStatus
from research_group_agent.parser import MemberPageParser


PLAIN_TEXT_BEFORE_UL = """
<html><body>
Current Students:
<ul>
  <li><a href="https://example.edu/~alice">Alice Wang</a> – PhD Student</li>
  <li><a href="https://example.edu/~bob">Bob Chen</a> – Postdoc</li>
  <li><a href="https://example.edu/~carol">Carol Davis</a> – Research Staff</li>
</ul>
</body></html>
"""

STRONG_BEFORE_UL = """
<html><body>
<strong>Current Students:</strong>
<ul>
  <li><a href="https://example.edu/~alice">Alice Wang</a> – PhD Student</li>
  <li><a href="https://example.edu/~bob">Bob Chen</a> – Postdoc</li>
  <li><a href="https://example.edu/~carol">Carol Davis</a> – Research Staff</li>
</ul>
</body></html>
"""

P_STRONG_BEFORE_UL = """
<html><body>
<p><strong>Graduate Students:</strong></p>
<ul>
  <li><a href="https://example.edu/~dan">Dan Kim</a> – PhD Student</li>
  <li><a href="https://example.edu/~eva">Eva Martinez</a> – PhD Student</li>
  <li><a href="https://example.edu/~frank">Frank Liu</a> – PhD Student</li>
</ul>
</body></html>
"""

DIV_PLAIN_BEFORE_UL = """
<html><body>
<div>PhD Students:</div>
<ul>
  <li><a href="https://example.edu/~gina">Gina Park</a> – PhD Student</li>
  <li><a href="https://example.edu/~henry">Henry Lee</a> – PhD Student</li>
  <li><a href="https://example.edu/~iris">Iris Chen</a> – PhD Student</li>
</ul>
</body></html>
"""

MULTI_PLAIN_SECTIONS = """
<html><body>
Current Students:
<ul>
  <li><a href="https://example.edu/~a1">Alice One</a> – PhD Student</li>
  <li><a href="https://example.edu/~a2">Alice Two</a> – PhD Student</li>
</ul>
Postdocs:
<ul>
  <li><a href="https://example.edu/~p1">Post One</a> – Postdoc</li>
  <li><a href="https://example.edu/~p2">Post Two</a> – Postdoc</li>
</ul>
Former Members:
<ul>
  <li><a href="https://example.edu/~f1">Former One</a> – Former PhD</li>
  <li><a href="https://example.edu/~f2">Former Two</a> – Former PhD</li>
</ul>
</body></html>
"""


class TestSprint2ASectionAwareParser(unittest.TestCase):
    def _parse(self, html: str):
        return MemberPageParser().parse(html, base_url="https://example.edu/")

    def test_plain_text_before_ul(self):
        parsed = self._parse(PLAIN_TEXT_BEFORE_UL)
        self.assertGreaterEqual(len(parsed.entries), 3)
        self.assertTrue(any(s.detection_method == "plain_text" for s in parsed.sections))

    def test_strong_before_ul(self):
        parsed = self._parse(STRONG_BEFORE_UL)
        names = {e.name for e in parsed.entries}
        self.assertIn("Alice Wang", names)
        self.assertIn("Bob Chen", names)
        current = [e for e in parsed.entries if e.member_status == MemberStatus.CURRENT]
        self.assertGreaterEqual(len(current), 3)

    def test_p_strong_before_ul(self):
        parsed = self._parse(P_STRONG_BEFORE_UL)
        names = {e.name for e in parsed.entries}
        self.assertIn("Dan Kim", names)
        self.assertIn("Eva Martinez", names)
        member_sections = [s for s in parsed.sections if s.is_member_section]
        self.assertTrue(member_sections)

    def test_div_plain_before_ul(self):
        parsed = self._parse(DIV_PLAIN_BEFORE_UL)
        self.assertGreaterEqual(len(parsed.entries), 3)

    def test_multiple_plain_sections(self):
        parsed = self._parse(MULTI_PLAIN_SECTIONS)
        names = {e.name for e in parsed.entries}
        self.assertIn("Alice One", names)
        self.assertIn("Post One", names)
        self.assertIn("Former One", names)
        alumni = [e for e in parsed.entries if e.member_status == MemberStatus.ALUMNI]
        self.assertGreaterEqual(len(alumni), 2)


if __name__ == "__main__":
    unittest.main()
