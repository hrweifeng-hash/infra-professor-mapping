"""AdaptiveMemberLimiter — page-quality-aware member export caps (PR29).

Replaces the fixed MAX_MEMBERS_PER_GROUP with limits derived from
DepartmentScopeDetector output and parsed roster size.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from research_group_agent.department_scope_detector import DepartmentScopeResult
from research_group_agent.parser import ParsedMemberPage

LEGACY_MEMBER_CAP = 20
LARGE_CLEAN_GROUP_CAP = 60
MEDIUM_DEPT_CAP = 30
NO_CAP_LIMIT = 10_000


@dataclass
class AdaptiveMemberLimitResult:
    """Adaptive export limit for a parsed member page."""

    member_limit: int
    confidence: str
    reason: str
    rules_applied: list[str] = field(default_factory=list)
    unlimited: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "member_limit": self.member_limit,
            "confidence": self.confidence,
            "reason": self.reason,
            "rules_applied": list(self.rules_applied),
            "unlimited": self.unlimited,
        }


class AdaptiveMemberLimiter:
    """
    Determine member export limit from page quality signals.

    Rules (department scope takes precedence over clean-group rules):
      1. Clean research group, parsed <= 60  → no cap
      2. Large clean group, parsed > 60      → cap 60
      3. Department page, confidence >= 0.7  → legacy cap 20
      4. Medium-confidence department        → cap 30
      5. Very small group, parsed <= 20      → no cap (non-department only)
    """

    LEGACY_CAP = LEGACY_MEMBER_CAP
    LARGE_CLEAN_CAP = LARGE_CLEAN_GROUP_CAP
    MEDIUM_DEPT_CAP = MEDIUM_DEPT_CAP

    def compute(
        self,
        parsed: ParsedMemberPage,
        department_scope: DepartmentScopeResult,
        *,
        validated_member_count: int | None = None,
    ) -> AdaptiveMemberLimitResult:
        parsed_count = len(parsed.entries)
        export_count = (
            validated_member_count
            if validated_member_count is not None
            else parsed_count
        )

        if department_scope.is_department_page:
            return self._department_limit(department_scope, export_count)

        if parsed_count <= 20:
            return AdaptiveMemberLimitResult(
                member_limit=max(export_count, NO_CAP_LIMIT),
                confidence="High",
                reason=(
                    f"Very small group ({parsed_count} parsed entries); "
                    "no member cap applied"
                ),
                rules_applied=["very_small_group"],
                unlimited=True,
            )

        if parsed_count <= 60:
            return AdaptiveMemberLimitResult(
                member_limit=max(export_count, NO_CAP_LIMIT),
                confidence="High",
                reason=(
                    f"Clean research group ({parsed_count} parsed entries); "
                    "all validated members exported"
                ),
                rules_applied=["clean_research_group"],
                unlimited=True,
            )

        return AdaptiveMemberLimitResult(
            member_limit=self.LARGE_CLEAN_CAP,
            confidence="High",
            reason=(
                f"Large clean research group ({parsed_count} parsed entries); "
                f"cap at {self.LARGE_CLEAN_CAP}"
            ),
            rules_applied=["large_clean_group"],
        )

    def _department_limit(
        self,
        department_scope: DepartmentScopeResult,
        export_count: int,
    ) -> AdaptiveMemberLimitResult:
        confidence = department_scope.confidence

        if confidence >= 0.7:
            return AdaptiveMemberLimitResult(
                member_limit=self.LEGACY_CAP,
                confidence="High",
                reason=(
                    f"Department page (confidence={confidence:.2f}); "
                    f"legacy cap {self.LEGACY_CAP} retained"
                ),
                rules_applied=["department_high_confidence"],
            )

        if confidence >= 0.4:
            return AdaptiveMemberLimitResult(
                member_limit=self.MEDIUM_DEPT_CAP,
                confidence="Medium",
                reason=(
                    f"Medium-confidence department page (confidence={confidence:.2f}); "
                    f"cap at {self.MEDIUM_DEPT_CAP}"
                ),
                rules_applied=["medium_confidence_department"],
            )

        return AdaptiveMemberLimitResult(
            member_limit=self.LEGACY_CAP,
            confidence="Low",
            reason=(
                f"Low-confidence department page (confidence={confidence:.2f}); "
                f"default legacy cap {self.LEGACY_CAP}"
            ),
            rules_applied=["department_low_confidence"],
        )


def format_adaptive_member_limit_log(
    *,
    professor_name: str,
    parsed_members: int,
    exported_members: int,
    limit_result: AdaptiveMemberLimitResult,
) -> str:
    """Format PR29 console log block when a page is member-capped."""
    lines = [
        "Adaptive Member Limiter",
        f"  professor={professor_name}",
        f"  parsed_members={parsed_members}",
        f"  exported_members={exported_members}",
        f"  applied_limit={limit_result.member_limit if not limit_result.unlimited else 'none'}",
        f"  reason={limit_result.reason}",
        f"  confidence={limit_result.confidence}",
        "  rules:",
    ]
    for rule in limit_result.rules_applied:
        lines.append(f"    - {rule}")
    return "\n".join(lines)
