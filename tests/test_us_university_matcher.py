import json
import tempfile
import unittest
from pathlib import Path

from identity.us_university_matcher import USUniversityMatcher


class TestUSUniversityMatcher(unittest.TestCase):
    def setUp(self):
        fixture = [
            {
                "canonical": "Massachusetts Institute of Technology",
                "aliases": ["MIT"],
                "country": "United States",
            },
            {
                "canonical": "University of Washington",
                "aliases": ["UW"],
                "country": "United States",
            },
            {
                "canonical": "San Diego State University",
                "aliases": ["SDSU"],
                "country": "United States",
            },
            {
                "canonical": "University of California, San Diego",
                "aliases": ["UC San Diego", "UCSD"],
                "country": "United States",
            },
        ]

        self._tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        )
        json.dump(fixture, self._tmp)
        self._tmp.close()

        self.matcher = USUniversityMatcher(universities_path=self._tmp.name)

    def tearDown(self):
        Path(self._tmp.name).unlink(missing_ok=True)

    def test_exact_canonical_match(self):
        result = self.matcher.match("Massachusetts Institute of Technology")

        self.assertEqual(result.canonical, "Massachusetts Institute of Technology")
        self.assertEqual(result.country, "United States")
        self.assertEqual(result.confidence, 1.0)

    def test_alias_match(self):
        result = self.matcher.match("MIT")

        self.assertEqual(result.canonical, "Massachusetts Institute of Technology")
        self.assertEqual(result.confidence, 0.85)

    def test_substring_containment_match(self):
        result = self.matcher.match(
            "University of Washington Paul G. Allen School of Computer Science"
        )

        self.assertEqual(result.canonical, "University of Washington")
        self.assertEqual(result.confidence, 0.6)

    def test_no_match(self):
        result = self.matcher.match("Tsinghua University, Beijing, China")

        self.assertIsNone(result.canonical)
        self.assertIsNone(result.country)
        self.assertEqual(result.confidence, 0.0)

    def test_comma_containing_university_name_not_confused_with_prefix_match(self):
        # Regression test: "University of California, San Diego" contains a
        # comma in its own name. Naive comma-split fragment matching
        # ("San Diego" fragment vs. "San Diego State University" canonical)
        # previously produced a confident but wrong match. Matching the
        # canonical against the FULL affiliation string instead fixes this.
        result = self.matcher.match(
            "University of California, San Diego, La Jolla, CA, USA"
        )

        self.assertEqual(result.canonical, "University of California, San Diego")
        self.assertEqual(result.confidence, 0.6)

    def test_state_abbreviation_does_not_false_match(self):
        # Regression test: a bare two-letter state code segment (e.g. "WA")
        # must not substring-match into an unrelated long canonical name
        # like "george WAshington university" or "CAlifornia institute of
        # technology". Found via a real pipeline run: "Microsoft Research,
        # Redmond, WA, USA" was incorrectly resolving to University of
        # Washington's namesake before the length guard was added.
        result = self.matcher.match("Microsoft Research, Redmond, WA, USA")

        self.assertIsNone(result.canonical)
        self.assertEqual(result.confidence, 0.0)

    def test_empty_affiliation(self):
        result = self.matcher.match(None)

        self.assertIsNone(result.canonical)
        self.assertEqual(result.confidence, 0.0)


if __name__ == "__main__":
    unittest.main()
