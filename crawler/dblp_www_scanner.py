import gzip
from pathlib import Path
from typing import Iterator

from lxml import etree

from crawler.normalized_dataset import resolve_normalized_path
from models.person_record import PersonRecord
from parser.www_record_parser import WWWRecordParser
from utils.observability import stage_start, stage_end, progress


class DBLPWWWScanner:
    """
    Stream DBLP's <www key="homepages/..."> person records with minimal
    memory usage, yielding only PersonRecords for authors we already know
    about from the publication-parsing pass (target_names).

    This is a second, additive pass over the same normalized dblp.xml.gz
    used by DBLPDatasetScanner (see crawler.normalized_dataset — the cached
    normalized copy is reused, never rebuilt). It does NOT build an
    in-memory index of DBLP's ~4.1M person records: every element is
    inspected, matched against target_names, and cleared immediately,
    regardless of match.

    DBLP bulk XML never carries a `pid` attribute on <author> elements
    inside publication records (verified empirically — see PR10 plan), so
    the join key here is the disambiguated author name string itself,
    case-folded. A single <www> record can list multiple <author> aliases
    (e.g. a former name); any alias matching target_names counts as a
    match, and the matched alias (not necessarily record.name) is yielded
    alongside the record so callers can join back correctly.
    """

    def __init__(
        self,
        target_names: set[str],
        dataset_path: str = "data/raw/dblp.xml.gz",
    ):
        # normalize once so lookups during scanning are cheap set membership
        self.target_names = {n.strip().casefold() for n in target_names}
        self.dataset_path = Path(dataset_path)
        self.parser = WWWRecordParser()

    def __iter__(self) -> Iterator[tuple[str, PersonRecord]]:
        if not self.dataset_path.exists():
            raise FileNotFoundError(f"Dataset not found: {self.dataset_path}")

        parse_path = resolve_normalized_path(self.dataset_path)

        start = stage_start("DBLP WWW Parsing")
        count = 0
        matched = 0

        with gzip.open(parse_path, "rb") as raw:
            context = etree.iterparse(raw, events=("end",), tag="www")

            for _, element in context:
                count += 1
                progress("DBLP WWW Parsing", count, interval=500000)

                key = element.get("key") or ""

                if key.startswith("homepages/"):
                    matched_name = None

                    for author_node in element.findall("author"):
                        text = author_node.text

                        if text and text.strip().casefold() in self.target_names:
                            matched_name = text.strip()
                            break

                    if matched_name is not None:
                        record = self.parser.parse(element)
                        matched += 1
                        yield matched_name, record

                element.clear()

                while element.getprevious() is not None:
                    del element.getparent()[0]

        print(
            f"[WWW Scan] scanned={count} matched={matched}",
            flush=True,
        )
        stage_end("DBLP WWW Parsing", start)
