@dataclass
class Enrichment:

    source: str

    success: bool

    message: str | None = None