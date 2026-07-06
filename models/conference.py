from dataclasses import dataclass


@dataclass
class Conference:
    """
    Conference configuration.
    """

    name: str

    dblp_name: str

    category: str

    start_year: int