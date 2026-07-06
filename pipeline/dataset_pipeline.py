from crawler.dblp_dataset_scanner import DBLPDatasetScanner
from config.conference_alias import CONFERENCE_ALIAS
from parser.dataset_proceedings_parser import DatasetProceedingsParser


class DatasetPipeline:
    """
    Stream the DBLP dataset once and yield normalized Proceedings objects.

    The pipeline uses DBLPDatasetScanner to consume the XML in a single pass.
    It normalizes venue names to internal conference names and rebuilds the
    Proceedings object using DatasetProceedingsParser.
    """

    def __init__(self, dataset_path: str = "data/raw/dblp.xml.gz"):
        self.scanner = DBLPDatasetScanner(dataset_path)
        self.parser = DatasetProceedingsParser()

    def __iter__(self):
        for candidate in self.scanner:
            for paper in candidate.papers:
                paper.venue = CONFERENCE_ALIAS.get(paper.venue, paper.venue)

            proceedings = self.parser.parse(candidate.papers)

            if proceedings is None:
                continue

            yield proceedings
