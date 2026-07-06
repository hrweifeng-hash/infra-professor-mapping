import argparse

from pipeline.mapping_pipeline import MappingPipeline
from config.conferences import CONFERENCES


YEARS = [
    2021,
    2022,
    2023,
    2024,
    2025,
]

TOP_K = 100


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run the Infra Professor Mapping pipeline."
    )

    parser.add_argument(
        "--conferences",
        nargs="+",
        default=None,
        help=(
            "Subset of conference keys from config/conferences.py "
            "(e.g. --conferences OSDI SOSP). Default: all configured "
            "conferences."
        ),
    )

    parser.add_argument(
        "--years",
        nargs="+",
        type=int,
        default=None,
        help=f"Subset of years to run. Default: {YEARS}.",
    )

    parser.add_argument(
        "--no-enrich",
        action="store_true",
        help=(
            "Skip DBLP author-page enrichment (no network calls). "
            "Useful for a fast smoke test of the dataset pipeline."
        ),
    )

    parser.add_argument(
        "--top-n",
        type=int,
        default=300,
        help="How many top-ranked professors get identity enrichment.",
    )

    return parser.parse_args()


def main():

    args = parse_args()

    conferences = (
        [CONFERENCES[key] for key in args.conferences]
        if args.conferences
        else list(CONFERENCES.values())
    )

    years = args.years if args.years else YEARS

    pipeline = MappingPipeline(
        identity_top_n=args.top_n,
        enrich_identity=not args.no_enrich,
    )

    professors = pipeline.run(
        conferences=conferences,
        years=years,
    )

    print()
    print("=" * 100)
    print("Professor Universe")
    print("=" * 100)
    print(f"Total Professors: {len(professors)}")
    print()

    print("=" * 100)
    print(f"Top {TOP_K} Professors")
    print("=" * 100)

    ranked = sorted(
        professors,
        key=lambda p: getattr(
            getattr(p, "intelligence", None),
            "overall_score",
            0,
        ),
        reverse=True,
    )

    for i, professor in enumerate(ranked[:TOP_K], start=1):

        intelligence = getattr(professor, "intelligence", None)
        author_profile = getattr(professor, "author_profile", None)
        author = getattr(author_profile, "author", None) if author_profile else None

        if not intelligence or not author:
            continue

        venues = ", ".join(
            list(
                getattr(
                    intelligence,
                    "venue_distribution",
                    {},
                ).keys()
            )[:3]
        )

        areas = ", ".join(
            getattr(
                intelligence,
                "research_areas",
                [],
            )[:3]
        )

        print(f"{i:3d}. {author.name}")

        print(
            f"     Score      : {getattr(intelligence, 'overall_score', 0):.1f} ({getattr(intelligence, 'priority', 'N/A')})"
        )

        print(
            f"     Papers     : {getattr(intelligence, 'publication_count', 0)}"
        )

        print(
            f"     Research   : {areas if areas else 'N/A'}"
        )

        print(
            f"     Venues     : {venues if venues else 'N/A'}"
        )

        print()

    us_top100 = getattr(pipeline, "us_top100", [])

    print("=" * 100)
    print(f"Top {len(us_top100)} US Infrastructure Professors")
    print("=" * 100)
    print("See data/output/top100_us_professors.csv / .json / TOP100_US.md")
    print()

    for row in us_top100[:10]:
        print(
            f"{row['Rank']:3d}. {row['Name']} — {row['University'] or 'N/A'} "
            f"({row['Score']}, {row['Source Confidence']})"
        )

    print()


if __name__ == "__main__":
    main()