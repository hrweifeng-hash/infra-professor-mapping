from typing import Dict

from models.author_profile import AuthorProfile
from models.proceedings import Proceedings


class AuthorProfileBuilder:
    """
    Build AuthorProfile objects from Proceedings.
    """

    def build(
        self,
        proceedings: Proceedings,
    ) -> Dict[str, AuthorProfile]:

        profiles = {}

        for paper in proceedings.papers:

            for author in paper.authors:

                pid = author.pid or author.name

                if pid not in profiles:

                    profiles[pid] = AuthorProfile(
                        author=author
                    )

                profile = profiles[pid]

                profile.papers.append(paper)

                profile.conferences.add(
                    paper.venue
                )

                profile.active_years.add(
                    paper.year
                )

        return profiles