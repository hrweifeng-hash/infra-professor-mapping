"""
Infrastructure Affinity Score (PR11).

Measures how strongly a professor's publication portfolio aligns with core
infrastructure / systems venues. This is an interpretable ranking feature,
not a hard filter — ML venue papers still count toward total output.
"""

from dataclasses import dataclass


# Canonical infra venues and DBLP display-name aliases observed in venue_distribution.
INFRA_VENUE_ALIASES: dict[str, tuple[str, ...]] = {
    "OSDI": ("osdi",),
    "SOSP": ("sosp",),
    "NSDI": ("nsdi",),
    "FAST": ("fast",),
    "ATC": ("usenix atc", "usenix annual technical conference", "atc"),
    "EuroSys": ("eurosys",),
    "ASPLOS": ("asplos",),
    "SIGCOMM": ("sigcomm",),
    "SoCC": ("socc", "symposium on cloud computing"),
    "Middleware": ("middleware",),
}


@dataclass(frozen=True)
class InfrastructureAffinityResult:
    """Interpretable breakdown of infrastructure venue alignment."""

    affinity: float
    infra_paper_count: int
    total_paper_count: int
    infra_venue_counts: dict[str, int]
    primary_infra_venues: tuple[str, ...]


def _normalize_venue(venue: str) -> str:
    return " ".join(venue.lower().split())


def match_infrastructure_venue(venue: str) -> str | None:
    """
    Return the canonical infra venue name if *venue* matches, else None.
    """
    normalized = _normalize_venue(venue)

    for canonical, aliases in INFRA_VENUE_ALIASES.items():
        canonical_lower = canonical.lower()

        if normalized == canonical_lower:
            return canonical

        for alias in aliases:
            if len(alias) <= 4:
                if normalized == alias:
                    return canonical
            elif alias in normalized or normalized in alias:
                return canonical

    return None


def compute_infrastructure_affinity(
    venue_distribution: dict[str, int],
) -> InfrastructureAffinityResult:
    """
    Compute infrastructure affinity as the fraction of papers published in
    core infrastructure venues (0.0 – 1.0).
    """
    total = sum(venue_distribution.values())

    if total == 0:
        return InfrastructureAffinityResult(
            affinity=0.0,
            infra_paper_count=0,
            total_paper_count=0,
            infra_venue_counts={},
            primary_infra_venues=(),
        )

    infra_venue_counts: dict[str, int] = {}
    infra_paper_count = 0

    for venue, count in venue_distribution.items():
        canonical = match_infrastructure_venue(venue)
        if canonical is None:
            continue

        infra_paper_count += count
        infra_venue_counts[canonical] = (
            infra_venue_counts.get(canonical, 0) + count
        )

    primary = tuple(
        venue
        for venue, _ in sorted(
            infra_venue_counts.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:3]
    )

    return InfrastructureAffinityResult(
        affinity=infra_paper_count / total,
        infra_paper_count=infra_paper_count,
        total_paper_count=total,
        infra_venue_counts=infra_venue_counts,
        primary_infra_venues=primary,
    )
