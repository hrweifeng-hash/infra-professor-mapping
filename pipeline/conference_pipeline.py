from builders.author_profile_builder import AuthorProfileBuilder
from builders.professor_profile_builder import ProfessorProfileBuilder
from utils.observability import stage_start, stage_end


class ConferencePipeline:

    def __init__(self):
        self.author_builder = AuthorProfileBuilder()
        self.professor_builder = ProfessorProfileBuilder()

    def run(self, proceedings):

        print("=" * 80)
        print(f"Running pipeline: {proceedings.conference} {proceedings.year}")
        print("=" * 80)

        if not proceedings or not proceedings.papers:
            print(f"[SKIP] missing proceedings data: {proceedings.conference} {proceedings.year}")
            return []

        print()
        print("Conference :", proceedings.conference)
        print("Year       :", proceedings.year)
        print("Papers     :", len(proceedings.papers))
        print()

        # --------------------------------------------------
        # Step 1: Author Profiles (AuthorProfileBuilder)
        # --------------------------------------------------
        ab_start = stage_start("AuthorProfileBuilder")
        author_profiles = self.author_builder.build(proceedings)
        stage_end("AuthorProfileBuilder", ab_start)

        if not author_profiles:
            return []

        print(f"Author Profiles : {len(author_profiles)}")

        # --------------------------------------------------
        # Step 5: Professor Profiles (ProfessorProfileBuilder)
        # --------------------------------------------------
        pb_start = stage_start("ProfessorProfileBuilder")
        professor_profiles = self.professor_builder.build(author_profiles)
        stage_end("ProfessorProfileBuilder", pb_start)

        print(f"Professor Profiles : {len(professor_profiles)}")

        return list(professor_profiles.values())
