from models.professor_profile import ProfessorProfile


def print_top_professors(
    professors: dict[str, ProfessorProfile],
    top_k: int = 20,
):

    print()
    print("=" * 80)
    print("Top Professors")
    print("=" * 80)

    professors = sorted(
        professors.values(),
        key=lambda p: len(p.author_profile.papers),
        reverse=True,
    )

    for professor in professors[:top_k]:

        print()

        print(professor.author_profile.author.name)

        print(
            f"Papers : {len(professor.author_profile.papers)}"
        )

        print(
            "Areas  :",
            ", ".join(
                professor.intelligence.research_areas
            ),
        )
        print(

            "HM Match:",

            professor.intelligence.hm_matches,

        )
        if professor.intelligence.research_dna:

            print(
                "DNA    :",
                professor.intelligence.research_dna.top(5),
            )

