import json
import tempfile
import unittest
from pathlib import Path

from lxml import etree

from parser.www_record_parser import WWWRecordParser


class TestWWWRecordParser(unittest.TestCase):
    def setUp(self):
        denylist = ["orcid.org", "scholar.google.com", "dl.acm.org"]

        self._tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        )
        json.dump(denylist, self._tmp)
        self._tmp.close()

        self.parser = WWWRecordParser(denylist_path=self._tmp.name)

    def tearDown(self):
        Path(self._tmp.name).unlink(missing_ok=True)

    def _parse(self, xml: str):
        element = etree.fromstring(xml)
        return self.parser.parse(element)

    def test_picks_first_non_denylisted_url_as_homepage(self):
        xml = b"""
        <www mdate="2024-01-01" key="homepages/1/1">
            <author>Jane Doe</author>
            <title>Home Page</title>
            <note type="affiliation">MIT, Cambridge, MA, USA</note>
            <url>https://orcid.org/0000-0000-0000-0000</url>
            <url>https://www.cs.mit.edu/~jane</url>
        </www>
        """
        record = self._parse(xml)

        self.assertEqual(record.name, "Jane Doe")
        self.assertEqual(record.homepage, "https://www.cs.mit.edu/~jane")
        self.assertEqual(record.orcid, "https://orcid.org/0000-0000-0000-0000")
        self.assertEqual(record.affiliation_notes, ["MIT, Cambridge, MA, USA"])

    def test_all_urls_are_aggregators_homepage_is_none(self):
        xml = b"""
        <www mdate="2024-01-01" key="homepages/1/2">
            <author>John Smith</author>
            <url>https://orcid.org/0000-0000-0000-0001</url>
            <url>https://scholar.google.com/citations?user=abc</url>
            <url>https://dl.acm.org/profile/12345</url>
        </www>
        """
        record = self._parse(xml)

        self.assertIsNone(record.homepage)
        self.assertEqual(record.orcid, "https://orcid.org/0000-0000-0000-0001")

    def test_no_urls_at_all(self):
        xml = b"""
        <www mdate="2024-01-01" key="homepages/1/3">
            <author>No URLs Person</author>
        </www>
        """
        record = self._parse(xml)

        self.assertIsNone(record.homepage)
        self.assertIsNone(record.orcid)
        self.assertEqual(record.affiliation_notes, [])


if __name__ == "__main__":
    unittest.main()
