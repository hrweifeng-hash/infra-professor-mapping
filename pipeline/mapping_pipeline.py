from pipeline.conference_pipeline import ConferencePipeline
from pipeline.dataset_pipeline import DatasetPipeline
from registry.professor_registry import ProfessorRegistry

from identity.identity_pipeline import IdentityPipeline
from intelligence.pipeline import IntelligencePipeline
from intelligence.analyzers.publication_analyzer import PublicationAnalyzer
from intelligence.analyzers.statistics_analyzer import StatisticsAnalyzer
from intelligence.analyzers.venue_analyzer import VenueAnalyzer
from intelligence.analyzers.productivity_analyzer import ProductivityAnalyzer
from intelligence.analyzers.research_area_analyzer import ResearchAreaAnalyzer
from intelligence.ranking_engine import RankingEngine
from utils.observability import stage_start, stage_end
import time


class MappingPipeline:
    """
    Run the whole professor mapping workflow.
    """

    def __init__(
        self,
        dataset_path: str | None = None,
        identity_top_n: int = 300,
        enrich_identity: bool = True,
    ):
        self.conference_pipeline = ConferencePipeline()
        # dataset_pipeline can be overridden by caller via constructor arg
        from pipeline.dataset_pipeline import DatasetPipeline
        self.dataset_pipeline = DatasetPipeline(dataset_path) if dataset_path else None

        # How many top-ranked professors get real-world identity enrichment.
        # This bounds network calls to dblp.org — it must stay well below
        # the full professor universe. See ProfessorEnrichmentBuilder.
        self.identity_top_n = identity_top_n

        # Enrichment makes real network calls (one per professor). Callers
        # that just want to smoke-test the dataset pipeline (e.g. a single
        # conference/year) can disable it to skip network access entirely.
        self.enrich_identity = enrich_identity

        self.intelligence_pipeline = IntelligencePipeline(
            analyzers=[
                PublicationAnalyzer(),
                StatisticsAnalyzer(),
                ResearchAreaAnalyzer(),
                VenueAnalyzer(),
                ProductivityAnalyzer(),
            ]
        )
        self.ranking_engine = RankingEngine()

    def run(self, conferences, years):

        # lazily create dataset pipeline with default path if not provided
        if self.dataset_pipeline is None:
            self.dataset_pipeline = DatasetPipeline()

        # ✅ IMPORTANT: reset every run (避免污染)
        self.registry = ProfessorRegistry()

        # Stage: Dataset Loading (includes DBLP Parsing inside scanner)
        ds_start = stage_start("Dataset Loading")
        for proceedings in self.dataset_pipeline:
            if not any(
                proceedings.conference == conference.name
                and proceedings.year == year
                for conference in conferences
                for year in years
            ):
                continue

            print()
            print("=" * 100)
            print(f"{proceedings.conference} {proceedings.year}")
            print("=" * 100)

            professors = self.conference_pipeline.run(proceedings)

            # guard: skip invalid output
            if not professors:
                continue

            for professor in professors:
                self.registry.add(professor)

        # dataset loading finished
        stage_end("Dataset Loading", ds_start)

        # --------------------------------------------------
        # Build final dataset and rerun intelligence after deduplication
        # --------------------------------------------------
        reg_start = stage_start("ProfessorRegistry")
        professors = self.registry.build()
        stage_end("ProfessorRegistry", reg_start)

        # --------------------------------------------------
        # PR10: DBLP <www> person-record enrichment (local file only, no
        # network calls) — populates homepage/affiliation from the bulk
        # dataset before ranking. Runs over the full professor universe,
        # unlike ProfessorEnrichmentBuilder below (which is network-bound
        # and stays scoped to top-N).
        # --------------------------------------------------
        from builders.dblp_www_enrichment_builder import DBLPWWWEnrichmentBuilder

        www_start = stage_start("DBLPWWWEnrichment")
        www_enrichment_builder = DBLPWWWEnrichmentBuilder()
        www_enrichment_builder.enrich_many(list(professors.values()))
        stage_end("DBLPWWWEnrichment", www_start)

        # Stage: IntelligencePipeline
        intel_start = stage_start("IntelligencePipeline")
        professors = self.intelligence_pipeline.run(professors)
        stage_end("IntelligencePipeline", intel_start)

        # Stage: RankingEngine
        rank_start = stage_start("RankingEngine")
        ranked_professors = self.ranking_engine.rank(professors)
        stage_end("RankingEngine", rank_start)

        # --------------------------------------------------
        # Enrichment (PR8): fetch homepage / affiliation from DBLP's
        # per-author XML. Real network calls — bounded to the top N
        # ranked professors, never the full universe.
        # --------------------------------------------------
        top_n = min(self.identity_top_n, len(ranked_professors))

        if self.enrich_identity and top_n > 0:
            from builders.professor_enrichment_builder import ProfessorEnrichmentBuilder

            enrich_start = stage_start("ProfessorEnrichment")
            enrichment_builder = ProfessorEnrichmentBuilder()
            enrichment_builder.enrich_many(ranked_professors[:top_n])
            stage_end("ProfessorEnrichment", enrich_start)

        # Stage: IdentityPipeline
        from identity.dblp_resolver import DBLPResolver

        identity_start = stage_start("IdentityPipeline")
        identity_pipeline = IdentityPipeline(
            resolver=DBLPResolver(),
            top_n=self.identity_top_n,
        )
        self.identity_records = identity_pipeline.run(ranked_professors)
        stage_end("IdentityPipeline", identity_start)

        # --------------------------------------------------
        # Export (PR4)
        # --------------------------------------------------
        from pipeline.export_pipeline import ProfessorExporter

        exporter = ProfessorExporter()
        exp_start = stage_start("Export")
        exporter.export(ranked_professors)
        stage_end("Export", exp_start)

        # --------------------------------------------------
        # PR10: US professor filtering + Top100 export.
        # Filtering happens AFTER ranking metadata exists, and does not
        # change ranking behavior — RankingEngine/intelligence are never
        # touched by AffiliationResolver.
        # --------------------------------------------------
        from identity.affiliation_resolver import AffiliationResolver
        from identity.homepage_resolver import HomepageResolver
        from pipeline.us_top100_export_pipeline import USTop100Exporter

        us_start = stage_start("USTop100")

        affiliation_resolver = AffiliationResolver()
        affiliation_resolver.resolve_many(ranked_professors)
        affiliation_resolver.write_unmatched_report()

        # ranked_professors is already sorted by overall_score; filtering
        # preserves that order.
        us_professors = [p for p in ranked_professors if p.is_us]
        us_top100 = us_professors[:100]

        homepage_resolver = HomepageResolver()
        for professor in us_top100:
            professor.homepage = homepage_resolver.resolve(professor)

        # --------------------------------------------------
        # PR11: Research summaries (Top100 only, pluggable LLM)
        # --------------------------------------------------
        from summaries.pipeline import ResearchSummaryPipeline
        from summaries.providers.stub import StubLLMProvider

        summary_start = stage_start("ResearchSummaries")
        summary_pipeline = ResearchSummaryPipeline(provider=StubLLMProvider())
        summary_pipeline.generate_many(us_top100)
        stage_end("ResearchSummaries", summary_start)

        # --------------------------------------------------
        # PR12: Homepage Intelligence (Top100 only, single-page analysis)
        # --------------------------------------------------
        from homepage_agent.pipeline import HomepagePipeline
        from homepage_agent.providers.stub import StubNavigatorProvider
        from homepage_agent.report import HomepageAgentReport

        homepage_start = stage_start("HomepageIntelligence")
        homepage_pipeline = HomepagePipeline(provider=StubNavigatorProvider())
        homepage_graphs = homepage_pipeline.analyze_many(us_top100)

        from homepage_agent.homepage_resolver import CanonicalHomepageResolver

        canonical_resolver = CanonicalHomepageResolver(homepage_pipeline=homepage_pipeline)
        homepage_graphs = canonical_resolver.resolve_many(homepage_graphs)
        for professor, graph in zip(us_top100, homepage_graphs):
            professor.homepage_graph = graph

        HomepageAgentReport.write(homepage_graphs)
        stage_end("HomepageIntelligence", homepage_start)

        # --------------------------------------------------
        # PR13: Research Group Intelligence (Top 10, one extra fetch)
        # --------------------------------------------------
        from research_group_agent.pipeline import ResearchGroupPipeline
        from research_group_agent.providers.stub import StubResearchGroupProvider
        from research_group_agent.report import ResearchGroupReport

        rg_start = stage_start("ResearchGroupIntelligence")
        rg_pipeline = ResearchGroupPipeline(provider=StubResearchGroupProvider())
        research_group_graphs = rg_pipeline.analyze_many(us_top100)
        ResearchGroupReport.write(research_group_graphs, metrics=rg_pipeline.last_metrics)
        rg_pipeline.identity_repository.export()
        stage_end("ResearchGroupIntelligence", rg_start)

        self.us_top100 = USTop100Exporter().export(us_top100)

        # --------------------------------------------------
        # PR11: Validation report (ranking comparison + role estimates)
        # --------------------------------------------------
        from validation.pr11_validation_report import PR11ValidationReport

        report_start = stage_start("PR11Validation")
        report = PR11ValidationReport.generate(
            ranked_professors=ranked_professors,
            us_top100=us_top100,
        )
        PR11ValidationReport.write(report)
        stage_end("PR11Validation", report_start)

        print(
            f"[USTop100] {len(us_professors)} US professors identified, "
            f"exporting top {len(us_top100)}",
            flush=True,
        )
        stage_end("USTop100", us_start)

        return ranked_professors
