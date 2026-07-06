from crawler.dblp_www_scanner import DBLPWWWScanner


class DBLPWWWEnrichmentBuilder:
    """
    Enrich ProfessorProfile.homepage / .affiliation from DBLP's bulk
    <www> person records.

    Unlike ProfessorEnrichmentBuilder (PR8), this makes NO network calls —
    it is a second local pass over the already-downloaded dblp.xml.gz, so
    it is safe to run over the full professor universe rather than a
    bounded top-N slice.

    Join key is the case-folded author name (DBLP's bulk dump never puts a
    `pid` attribute on <author> elements inside publication records — see
    PR10 plan for the empirical check), not pid.
    """

    def __init__(self, dataset_path: str = "data/raw/dblp.xml.gz"):
        self.dataset_path = dataset_path

        self.total = 0
        self.homepage_found = 0
        self.affiliation_found = 0
        self.no_www_record = 0
        self.unmatched_sample: list[str] = []

    def enrich_many(self, professors: list) -> list:
        self.total = len(professors)

        by_name: dict[str, list] = {}

        for professor in professors:
            name = professor.author_profile.author.name
            by_name.setdefault(name.strip().casefold(), []).append(professor)

        target_names = set(by_name.keys())

        scanner = DBLPWWWScanner(
            target_names=target_names,
            dataset_path=self.dataset_path,
        )

        matched_keys: set[str] = set()

        for matched_name, record in scanner:
            key = matched_name.strip().casefold()
            group = by_name.get(key)

            if not group:
                continue

            matched_keys.add(key)

            for professor in group:
                if not professor.homepage and record.homepage:
                    professor.homepage = record.homepage
                    self.homepage_found += 1

                if not professor.affiliation and record.affiliation_notes:
                    professor.affiliation = record.affiliation_notes[0]
                    self.affiliation_found += 1

        unmatched = sorted(target_names - matched_keys)
        self.no_www_record = len(unmatched)
        self.unmatched_sample = unmatched[:25]

        self.report()

        return professors

    def report(self) -> None:
        print()
        print("=" * 60)
        print("DBLP Homepage Coverage Report")
        print("=" * 60)
        print()
        print(f"Total Professors      : {self.total}")
        print(f"Homepage Available    : {self.homepage_found}")
        print(f"Homepage Missing      : {self.total - self.homepage_found}")

        if self.total:
            coverage = self.homepage_found / self.total * 100
            print(f"Coverage               : {coverage:.1f}%")

        print()
        print(f"Affiliation Available  : {self.affiliation_found}")
        print(f"No <www> record at all : {self.no_www_record}")

        if self.unmatched_sample:
            print()
            print("Sample of names with no matching <www> record:")

            for name in self.unmatched_sample:
                print(f"  - {name}")

        print()
