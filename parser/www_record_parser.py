import json
from pathlib import Path
from urllib.parse import urlparse

from lxml import etree

from models.person_record import PersonRecord

DEFAULT_DENYLIST_PATH = (
    Path(__file__).resolve().parent.parent / "resources" / "dblp_url_denylist.json"
)


class WWWRecordParser:
    """
    Parse one DBLP <www key="homepages/..."> element into a PersonRecord.

    <url> children on these records are a mix of personal homepages and
    aggregator/profile links (ORCID, Google Scholar, ACM DL, IEEE Xplore,
    Wikidata, ...). The denylist (resources/dblp_url_denylist.json, built
    from what was actually observed in the real dataset — see PR10 plan)
    is loaded once per parser instance and used to pick the first <url>
    that looks like a real personal/faculty homepage.
    """

    def __init__(self, denylist_path: Path | str = DEFAULT_DENYLIST_PATH):
        with open(denylist_path, "r", encoding="utf-8") as f:
            self._denylist = set(json.load(f))

    @staticmethod
    def _text(element, tag: str) -> str | None:
        node = element.find(tag)

        if node is None or node.text is None:
            return None

        return node.text.strip()

    def _classify_homepage(self, urls: list[str]) -> str | None:
        for url in urls:
            host = urlparse(url).netloc.lower()

            if host and host not in self._denylist:
                return url

        return None

    def _classify_orcid(self, urls: list[str]) -> str | None:
        for url in urls:
            if "orcid.org" in url:
                return url

        return None

    def parse(self, element: etree._Element) -> PersonRecord:
        name = self._text(element, "author") or ""

        urls = [
            node.text.strip()
            for node in element.findall("url")
            if node.text
        ]

        affiliation_notes = [
            node.text.strip()
            for node in element.findall("note")
            if node.get("type") == "affiliation" and node.text
        ]

        return PersonRecord(
            name=name,
            urls=urls,
            affiliation_notes=affiliation_notes,
            homepage=self._classify_homepage(urls),
            orcid=self._classify_orcid(urls),
        )
