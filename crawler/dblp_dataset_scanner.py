import gzip
from pathlib import Path
from typing import Iterator

from lxml import etree
from utils.observability import stage_start, stage_end, progress
import time

from models.proceedings import Proceedings
from parser.paper_parser import PaperParser
from crawler.normalized_dataset import resolve_normalized_path


class DBLPDatasetScanner:
    """
    Stream DBLP dataset XML with minimal memory usage.

    This scanner reads `data/raw/dblp.xml.gz`, iterates over
    <inproceedings> elements, and delegates XML-to-Paper parsing
    to PaperParser. It groups papers by conference and year and
    yields one Proceedings object each time that grouping changes.

    DBLP's official dump periodically contains stray unescaped
    entities that make lxml's strict parser abort mid-stream. Before
    parsing, the scanner normalizes the raw file once (see
    crawler.ingestion.normalize_dataset) and caches the cleaned copy
    next to the original, so subsequent runs skip re-normalizing.
    """

    def __init__(self, dataset_path: str = "data/raw/dblp.xml.gz"):
        self.dataset_path = Path(dataset_path)
        self.parser = PaperParser()

    def __iter__(self) -> Iterator[Proceedings]:
        if not self.dataset_path.exists():
            raise FileNotFoundError(
                f"Dataset not found: {self.dataset_path}"
            )

        parse_path = resolve_normalized_path(self.dataset_path)

        current_proceedings: Proceedings | None = None
        current_key: tuple[str, int] | None = None

        start = stage_start("DBLP Parsing")
        count = 0
        with gzip.open(parse_path, "rb") as raw:
            context = etree.iterparse(
                raw,
                events=("end",),
                tag="inproceedings",
            )

            for _, element in context:
                paper = self.parser.parse(element)
                paper_key = (paper.venue, paper.year)
                count += 1
                progress("DBLP Parsing", count, interval=100000)

                if current_key != paper_key:
                    if current_proceedings is not None:
                        yield current_proceedings

                    current_key = paper_key
                    current_proceedings = Proceedings(
                        conference=paper.venue,
                        year=paper.year,
                        title=f"{paper.venue} {paper.year}",
                        papers=[paper],
                    )
                else:
                    current_proceedings.papers.append(paper)

                element.clear()

                while element.getprevious() is not None:
                    del element.getparent()[0]

        if current_proceedings is not None:
            yield current_proceedings
        stage_end("DBLP Parsing", start)
