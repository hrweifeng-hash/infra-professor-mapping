import json
import tempfile
import unittest
from pathlib import Path

from identity.affiliation_resolver import AffiliationResolver
from identity.us_university_matcher import USUniversityMatcher
from models.author import Author
from models.author_profile import AuthorProfile
from models.professor_profile import ProfessorProfile


class TestAffiliationResolver(unittest.TestCase):
    def setUp(self):
        fixture = [
            {
                "canonical": "Carnegie Mellon University",
                "aliases": ["CMU"],
                "country": "United States",
            },
        ]

        self._tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        )
        json.dump(fixture, self._tmp)
        self._tmp.close()

        matcher = USUniversityMatcher(universities_path=self._tmp.name)
        self.resolver = AffiliationResolver(matcher=matcher)

    def tearDown(self):
        Path(self._tmp.name).unlink(missing_ok=True)

    def _professor(self, affiliation: str | None) -> ProfessorProfile:
        author = Author(pid=None, name="Test Person")
        author_profile = AuthorProfile(author=author)

        return ProfessorProfile(
            author_profile=author_profile,
            affiliation=affiliation,
        )

    def test_known_us_affiliation_resolves_is_us_true(self):
        professor = self._professor("School of Computer Science, Carnegie Mellon University, Pittsburgh, PA")

        self.resolver.resolve(professor)

        self.assertTrue(professor.is_us)
        self.assertEqual(professor.university, "Carnegie Mellon University")
        self.assertEqual(professor.country, "United States")
        self.assertGreater(professor.affiliation_confidence, 0.0)

    def test_unknown_affiliation_resolves_is_us_false(self):
        professor = self._professor("ETH Zurich, Switzerland")

        self.resolver.resolve(professor)

        self.assertFalse(professor.is_us)
        self.assertIsNone(professor.university)
        self.assertIsNone(professor.country)
        self.assertEqual(professor.affiliation_confidence, 0.0)

    def test_missing_affiliation_resolves_is_us_false(self):
        professor = self._professor(None)

        self.resolver.resolve(professor)

        self.assertFalse(professor.is_us)


if __name__ == "__main__":
    unittest.main()
