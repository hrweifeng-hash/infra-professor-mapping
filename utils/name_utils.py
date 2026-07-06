import re


def normalize_author_name(name: str) -> str:
    """
    Remove DBLP disambiguation suffix.

    Example:
        Haibo Chen 0001 -> Haibo Chen
    """

    return re.sub(r"\s+\d{4}$", "", name)