from lxml import etree

from models.author import Author
from models.paper import Paper


class PaperParser:
    """
    Parse one DBLP <inproceedings> element into a Paper object.
    """

    @staticmethod
    def _text(element, tag: str) -> str | None:
        node = element.find(tag)

        if node is None:
            return None

        if node.text is None:
            return None

        return node.text.strip()

    def parse(self, element: etree._Element) -> Paper:

        authors = []

        for author_node in element.findall("author"):

            authors.append(
                Author(
                    pid=author_node.get("pid"),
                    name=(author_node.text or "").strip(),
                )
            )

        title = self._text(element, "title") or ""

        venue = self._text(element, "booktitle") or ""

        year_text = self._text(element, "year") or "0"

        pages = self._text(element, "pages")

        ee_url = self._text(element, "ee")

        dblp_url = self._text(element, "url")

        paper = Paper(
            title=title,
            authors=authors,
            venue=venue,
            year=int(year_text),
            pages=pages,
            dblp_key=element.get("key"),
            ee_url=ee_url,
            dblp_url=dblp_url,
        )

        return paper