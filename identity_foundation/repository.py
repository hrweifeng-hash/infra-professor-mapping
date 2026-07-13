"""Identity candidate repository — independent from MemberMerger."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from identity_foundation.models import (
    IDENTITY_PIPELINE_VERSION,
    IDENTITY_SCHEMA_VERSION,
    IdentityCandidate,
    ValidationState,
)


def _normalize_name(name: str) -> str:
    return " ".join(name.lower().split())


class IdentityRepository:
    """
    Collect, merge, deduplicate, and export identity candidates.

    Independent from MemberMerger — operates on the identity layer only.
    """

    def __init__(self) -> None:
        self._candidates: list[IdentityCandidate] = []
        self._exported_by_professor: dict[str, set[str]] = {}

    @property
    def size(self) -> int:
        return len(self._candidates)

    @property
    def candidates(self) -> list[IdentityCandidate]:
        return list(self._candidates)

    def collect(self, candidate: IdentityCandidate) -> None:
        """Add a single candidate to the repository."""
        self._candidates.append(candidate)

    def collect_many(self, candidates: list[IdentityCandidate]) -> None:
        """Add multiple candidates."""
        self._candidates.extend(candidates)

    def register_exported_members(
        self,
        professor_name: str,
        member_names: list[str],
    ) -> None:
        """Record which members were exported in the member graph."""
        key = professor_name.lower()
        if key not in self._exported_by_professor:
            self._exported_by_professor[key] = set()
        self._exported_by_professor[key].update(
            _normalize_name(n) for n in member_names
        )

    def mark_verified(self) -> None:
        """Upgrade candidates that appear in the final member graph export."""
        for candidate in self._candidates:
            exported = self._exported_by_professor.get(
                candidate.source_professor.lower(), set()
            )
            if _normalize_name(candidate.name) in exported:
                candidate.validation_state = ValidationState.VERIFIED
                candidate.confidence = max(candidate.confidence, 1.0)
                candidate.rejection_reason = None

    def merge(self) -> list[IdentityCandidate]:
        """
        Merge duplicate candidates (same professor + normalized name).

        Keeps the best evidence and highest validation state.
        """
        return self.deduplicate()

    def deduplicate(self) -> list[IdentityCandidate]:
        """Deduplicate by (source_professor, normalized_name), merging evidence."""
        merged: dict[tuple[str, str], IdentityCandidate] = {}
        for candidate in self._candidates:
            key = (candidate.source_professor.lower(), _normalize_name(candidate.name))
            if key in merged:
                merged[key] = merged[key].merge_with(candidate)
            else:
                merged[key] = candidate

        self._candidates = list(merged.values())
        return self._candidates

    def count_by_state(self) -> dict[str, int]:
        """Count candidates by validation state."""
        counts = {state.value: 0 for state in ValidationState}
        for candidate in self._candidates:
            counts[candidate.validation_state.value] += 1
        return counts

    def export(
        self,
        output_dir: str | Path = "data/output",
        filename: str = "identity_candidates.json",
    ) -> Path:
        """Write identity_candidates.json."""
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / filename

        deduped = self.deduplicate()
        self.mark_verified()

        payload = {
            "schema_version": IDENTITY_SCHEMA_VERSION,
            "pipeline_version": IDENTITY_PIPELINE_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_candidates": len(deduped),
            "validation_state_counts": self.count_by_state(),
            "candidates": [c.to_dict() for c in deduped],
        }

        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)

        print(f"[PR31] Wrote identity candidates to {path}", flush=True)
        return path

    def clear(self) -> None:
        """Reset repository state."""
        self._candidates.clear()
        self._exported_by_professor.clear()
