import gzip
from pathlib import Path
from typing import Iterator

from lxml import etree as ET

from models.author import Author
from models.paper import Paper


class DBLPDatasetLoader:
    """
    Stream papers from the official DBLP dataset.

    The loader is responsible for:

    - opening dblp.xml.gz
    - streaming XML
    - converting <inproceedings> into Paper

    It does NOT filter conferences or years.
    """

    def __init__(self, dataset_path: str):

        self.dataset_path = Path(dataset_path)

    def __iter__(self) -> Iterator[Paper]:

        if not self.dataset_path.exists():
            raise FileNotFoundError(
                f"Dataset not found: {self.dataset_path}"
            )

        with gzip.open(self.dataset_path, "rb") as f:

            context = ET.iterparse(
                f,
                events=("end",),
                tag="inproceedings",
                recover=True,
                huge_tree=True,
            )

            for _, elem in context:

                paper = self._parse_paper(elem)

                # release memory
                elem.clear()

                while elem.getprevious() is not None:
                    del elem.getparent()[0]

                if paper is not None:
                    yield paper

    def _parse_paper(
        self,
        elem,
    ) -> Paper | None:

        title = ""
        venue = ""
        year = None
        pages = None
        dblp_key = elem.get("key")
        ee_url = None

        authors = []

        for child in elem:

            tag = child.tag

            text = (
                child.text.strip()
                if child.text
                else ""
            )

            if tag == "author":

                authors.append(
                    Author(
                        pid=child.get("pid"),
                        name=text,
                    )
                )

            elif tag == "title":
                title = text

            elif tag == "booktitle":
                venue = text

            elif tag == "year":

                try:
                    year = int(text)
                except Exception:
                    return None

            elif tag == "pages":
                pages = text

            elif tag == "ee":
                ee_url = text

        if not venue:
            return None

        if year is None:
            return None

        return Paper(
            title=title,
            authors=authors,
            venue=venue,
            year=year,
            pages=pages,
            dblp_key=dblp_key,
            ee_url=ee_url,
        )