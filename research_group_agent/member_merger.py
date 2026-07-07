"""MemberMerger — merge and deduplicate TalentProfiles from multiple pages.

PR17: multi-page member discovery merges results from several candidate
pages into a single deduplicated list while preserving evidence about
which pages each member was found on.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from research_group_agent.models import TalentProfile


# ─────────────────────────────────────────────────────────────────────────────
# Output model
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class MergedMember:
    """A deduplicated member assembled from one or more parsed pages."""

    person: TalentProfile
    confidence: float
    source_pages: list[str] = field(default_factory=list)
    source_count: int = 1
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.person.to_dict(),
            "merge_confidence": round(self.confidence, 3),
            "source_pages": self.source_pages,
            "source_count": self.source_count,
            "merge_evidence": self.evidence,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Name normalisation helpers
# ─────────────────────────────────────────────────────────────────────────────

_SUFFIX_RE = re.compile(
    r"\b(?:Jr\.?|Sr\.?|II|III|IV|PhD|Ph\.D\.?|M\.S\.?|B\.S\.?)\b",
    re.IGNORECASE,
)
_WHITESPACE_RE = re.compile(r"\s+")


def _normalise_name(name: str) -> str:
    """Lowercase, strip suffixes and extra whitespace for fuzzy matching."""
    name = _SUFFIX_RE.sub("", name)
    name = _WHITESPACE_RE.sub(" ", name).strip().lower()
    return name


def _names_match(a: str, b: str) -> bool:
    """True when two normalised names refer to the same person.

    Matches:
      - Exact normalised equality.
      - One name is a suffix of the other (handles "Alice Smith" vs
        "Alice J. Smith").
      - All tokens of the shorter name appear in the longer name.
    """
    na, nb = _normalise_name(a), _normalise_name(b)
    if na == nb:
        return True
    # token-set containment
    tokens_a = set(na.split())
    tokens_b = set(nb.split())
    shorter, longer = (
        (tokens_a, tokens_b) if len(tokens_a) <= len(tokens_b) else (tokens_b, tokens_a)
    )
    if len(shorter) >= 2 and shorter.issubset(longer):
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# MemberMerger
# ─────────────────────────────────────────────────────────────────────────────


class MemberMerger:
    """
    Merge TalentProfile lists from multiple parsed pages.

    Usage::

        merger = MemberMerger()
        merged = merger.merge(
            pages=[
                (page_url_1, current_members_1, former_members_1),
                (page_url_2, current_members_2, former_members_2),
            ]
        )
        current  = merged["current"]   # list[MergedMember]
        former   = merged["former"]    # list[MergedMember]
        stats    = merged["stats"]     # dict

    Responsibilities:
      - Merge parsed members from multiple pages.
      - Deduplicate by name similarity.
      - Preserve evidence (which pages each member was found on).
      - Prefer the higher-confidence TalentProfile when duplicates exist.
      - Track source_pages and source_count per merged member.
    """

    def merge(
        self,
        pages: list[tuple[str, list[TalentProfile], list[TalentProfile]]],
    ) -> dict[str, Any]:
        """
        Merge members from *pages*.

        *pages* is a list of ``(page_url, current_members, former_members)``
        tuples, one per successfully parsed page.

        Returns a dict with keys:
          ``current``  — list[MergedMember] (deduplicated current members)
          ``former``   — list[MergedMember] (deduplicated former/alumni)
          ``stats``    — deduplication statistics dict
        """
        current_merged = self._merge_list(pages, slot=1)
        former_merged = self._merge_list(pages, slot=2)

        total_current_raw = sum(len(p[1]) for p in pages)
        total_former_raw = sum(len(p[2]) for p in pages)

        dedup_current = total_current_raw - len(current_merged)
        dedup_former = total_former_raw - len(former_merged)
        total_raw = total_current_raw + total_former_raw
        total_merged = len(current_merged) + len(former_merged)
        dedup_total = total_raw - total_merged

        dedup_rate = round(dedup_total / total_raw, 3) if total_raw > 0 else 0.0

        return {
            "current": current_merged,
            "former": former_merged,
            "stats": {
                "pages_merged": len(pages),
                "raw_current": total_current_raw,
                "raw_former": total_former_raw,
                "raw_total": total_raw,
                "merged_current": len(current_merged),
                "merged_former": len(former_merged),
                "merged_total": total_merged,
                "duplicates_removed": dedup_total,
                "duplicates_removed_current": dedup_current,
                "duplicates_removed_former": dedup_former,
                "deduplication_rate": dedup_rate,
            },
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _merge_list(
        self,
        pages: list[tuple[str, list[TalentProfile], list[TalentProfile]]],
        slot: int,
    ) -> list[MergedMember]:
        """Merge one category (current=1 / former=2) across all pages."""
        merged: list[MergedMember] = []

        for page_url, *member_lists in pages:
            members: list[TalentProfile] = member_lists[slot - 1]
            for profile in members:
                existing = self._find_duplicate(merged, profile.name)
                if existing is not None:
                    self._absorb(existing, profile, page_url)
                else:
                    merged.append(
                        MergedMember(
                            person=profile,
                            confidence=round(profile.confidence, 3),
                            source_pages=[page_url],
                            source_count=1,
                            evidence=[f"found_on:{page_url}"],
                        )
                    )

        # Sort by descending confidence for consistent output
        merged.sort(key=lambda m: m.confidence, reverse=True)
        return merged

    @staticmethod
    def _find_duplicate(
        merged: list[MergedMember],
        name: str,
    ) -> MergedMember | None:
        for existing in merged:
            if _names_match(existing.person.name, name):
                return existing
        return None

    @staticmethod
    def _absorb(
        existing: MergedMember,
        incoming: TalentProfile,
        page_url: str,
    ) -> None:
        """Absorb *incoming* into *existing*, preferring the higher confidence."""
        if page_url not in existing.source_pages:
            existing.source_pages.append(page_url)
            existing.source_count = len(existing.source_pages)
            existing.evidence.append(f"also_found_on:{page_url}")

        # Replace profile with the higher-confidence version
        if incoming.confidence > existing.person.confidence:
            existing.person = incoming
            existing.confidence = round(incoming.confidence, 3)
            existing.evidence.append(
                f"upgraded_confidence:{round(incoming.confidence, 3)}"
            )
        # Merge digital footprint fields that are missing in existing
        _merge_footprint(existing.person.digital_footprint, incoming.digital_footprint)


def _merge_footprint(base, incoming) -> None:
    """Copy non-None fields from *incoming* into *base* when base slot is None."""
    for attr in (
        "homepage",
        "github",
        "linkedin",
        "google_scholar",
        "dblp",
        "openreview",
        "semantic_scholar",
        "orcid",
        "blog",
    ):
        if getattr(base, attr) is None and getattr(incoming, attr) is not None:
            setattr(base, attr, getattr(incoming, attr))
