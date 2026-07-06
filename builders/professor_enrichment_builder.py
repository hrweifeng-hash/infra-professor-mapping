import time

from crawler.dblp_author_client import DBLPAuthorClient
from parser.author_parser import AuthorParser


class ProfessorEnrichmentBuilder:
    """
    Enrich a ProfessorProfile with fields only available from DBLP's
    per-author XML (homepage, affiliation) — NOT present in the bulk
    dblp.xml.gz dataset.

    This builder makes real network calls (one per professor), so it is
    deliberately NOT run for the full professor universe. Callers should
    only pass it a bounded slice (e.g. the top-N ranked professors) — see
    MappingPipeline.

    Design notes (per docs/HANDOFF.md coding principles):
    - Cached: a pid is only ever fetched once per builder instance.
    - Rate limited: a fixed delay is inserted between network calls to
      avoid hammering dblp.org.
    - Never raises: a failed lookup (404 / timeout / malformed XML) is
      logged and skipped, it must not abort the pipeline.
    """

    def __init__(
        self,
        client: DBLPAuthorClient | None = None,
        parser: AuthorParser | None = None,
        delay_seconds: float = 1.0,
    ):
        self.client = client or DBLPAuthorClient()
        self.parser = parser or AuthorParser()
        self.delay_seconds = delay_seconds

        self._cache: dict[str, object | None] = {}

        self.attempted = 0
        self.succeeded = 0
        self.failed = 0
        self.skipped_no_pid = 0

    def enrich(self, professor):
        pid = professor.author_profile.author.pid

        if not pid:
            self.skipped_no_pid += 1
            return professor

        detail = self._fetch(pid)

        if detail is not None:
            professor.homepage = detail.homepage
            professor.affiliation = detail.affiliation

        return professor

    def enrich_many(self, professors: list):
        """Enrich a bounded list of professors, in place, with progress logging."""

        total = len(professors)

        for index, professor in enumerate(professors, start=1):
            self.enrich(professor)

            if index % 10 == 0 or index == total:
                print(f"[Enrichment] {index}/{total}")

        self.report()

        return professors

    def report(self):
        print()
        print("=" * 40)
        print("DBLP Author Enrichment Summary")
        print("=" * 40)
        print(f"Attempted        : {self.attempted}")
        print(f"Succeeded        : {self.succeeded}")
        print(f"Failed           : {self.failed}")
        print(f"Skipped (no pid) : {self.skipped_no_pid}")
        print()

    def _fetch(self, pid: str):
        if pid in self._cache:
            return self._cache[pid]

        self.attempted += 1

        try:
            xml = self.client.get_author_xml(pid)
            detail = self.parser.parse(xml)
            self.succeeded += 1

        except Exception as exc:
            print(f"[Enrichment] FAILED pid={pid}: {exc}")
            detail = None
            self.failed += 1

        finally:
            # rate limit regardless of success/failure so a run of
            # consecutive failures can't hot-loop against dblp.org
            time.sleep(self.delay_seconds)

        self._cache[pid] = detail

        return detail
