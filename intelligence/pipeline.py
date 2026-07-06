from models.professor_profile import ProfessorProfile

from intelligence.analyzers.base_analyzers import BaseAnalyzer
from utils.observability import stage_start, stage_end


class IntelligencePipeline:

    def __init__(

        self,

        analyzers: list[BaseAnalyzer],

    ):

        self.analyzers = analyzers

    def run(

        self,

        professors: dict[str, ProfessorProfile],

    ) -> dict[str, ProfessorProfile]:
        import time

        print()
        print("=" * 80)
        print("Running Intelligence Pipeline")
        print("=" * 80)

        start = stage_start("IntelligencePipeline:analyzers")
        for professor in professors.values():
            for analyzer in self.analyzers:
                analyzer.analyze(professor)
        stage_end("IntelligencePipeline:analyzers", start)

        return professors
    
    