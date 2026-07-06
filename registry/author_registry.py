from models.author import Author
from models.author_profile import AuthorProfile


class AuthorRegistry:
    """
    Registry for deduplicating AuthorProfile objects.

    Priority:
        1. DBLP pid (preferred)
        2. normalized_name (fallback)
    """

    def __init__(self):
        self._profiles: dict[str, AuthorProfile] = {}

    def get_or_create(self, author: Author) -> AuthorProfile:
        """
        Return an existing AuthorProfile if it already exists,
        otherwise create a new one.
        """

        key = self._build_key(author)

        if key not in self._profiles:
            self._profiles[key] = AuthorProfile(author=author)

        return self._profiles[key]

    def get(self, author: Author) -> AuthorProfile | None:
        """
        Return AuthorProfile if it exists.
        """

        return self._profiles.get(self._build_key(author))

    def add(self, profile: AuthorProfile):
        """
        Manually register an AuthorProfile.
        """

        key = self._build_key(profile.author)
        self._profiles[key] = profile

    def values(self) -> list[AuthorProfile]:
        """
        Return all AuthorProfiles.
        """

        return list(self._profiles.values())

    def __len__(self):
        return len(self._profiles)

    @staticmethod
    def _build_key(author: Author) -> str:
        """
        Build a unique key for an author.

        Priority:
            pid > normalized_name > name
        """

        if author.pid:
            return f"pid:{author.pid}"

        if author.normalized_name:
            return f"name:{author.normalized_name}"

        return f"name:{author.name.lower()}"