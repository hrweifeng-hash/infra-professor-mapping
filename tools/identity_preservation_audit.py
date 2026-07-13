#!/usr/bin/env python3
"""
Sprint X — Identity Preservation Audit (read-only)

Measures how many parsed research-group members are discarded due to missing
homepage/profile identity evidence, and estimates value of preserving them for
future OpenAlex / DBLP / Google Scholar resolution.

Replays cached HTML with production components (MemberPageParser, MemberExtractor,
PersonValidator, MemberMerger) without modifying pipeline behavior.

Reads:
    data/output/research_group_graph.json
    data/cache/research_groups/ + data/cache/homepages/

Writes:
    data/output/IDENTITY_PRESERVATION.json
    data/output/IDENTITY_PRESERVATION_AUDIT.md

Usage:
    python3.11 tools/identity_preservation_audit.py [--graph PATH] [--limit N]
    python3.11 tools/identity_preservation_audit.py --professor "Ryan Huang"
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from research_group_agent.department_scope_detector import DepartmentScopeDetector
from research_group_agent.member_extractor import MemberExtractor
from research_group_agent.member_merger import MemberMerger
from research_group_agent.models import GroupPageSelection, MemberRole, MemberStatus
from research_group_agent.parser import MemberPageParser
from research_group_agent.person_validator import PersonValidator
from research_group_agent.precision_constants import (
    ALUMNI_SECTION_KEYWORDS,
    CURRENT_SECTION_KEYWORDS,
    PERSON_NEGATIVE_KEYWORDS,
    PERSON_NEGATIVE_NAME_PATTERNS,
    PERSON_NEGATIVE_URL_PATTERNS,
)
from research_group_agent.providers.stub import StubResearchGroupProvider
from tools.failure_pattern_analysis import _to_talent_profile, resolve_graph_path
from tools.layout_classification import _read_cached
from tools.validator_funnel_audit import _classify_validator_rule, _extract_signals

OUTPUT_DIR = Path("data/output")
OUT_JSON = OUTPUT_DIR / "IDENTITY_PRESERVATION.json"
OUT_MD = OUTPUT_DIR / "IDENTITY_PRESERVATION_AUDIT.md"

_EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")
_NAME_PATTERN = re.compile(r"^[A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z]+)+$")

BUCKETS = ("VERIFIED", "RESOLVABLE", "PARTIAL", "INVALID")

STUDENT_ROLES = frozenset({
    MemberRole.PHD_STUDENT,
    MemberRole.MASTER_STUDENT,
    MemberRole.POSTDOC,
    MemberRole.RESEARCH_STAFF,
    MemberRole.VISITOR,
})

CURRENT_STUDENT_SECTION_HINTS = frozenset(
    kw
    for kw in CURRENT_SECTION_KEYWORDS
    if "student" in kw or kw in {"phd students", "doctoral students", "graduate students"}
)

_ADMIN_ROLE_HINTS = frozenset({
    "administrator",
    "administrative",
    "coordinator",
    "secretary",
    "manager",
    "receptionist",
    "webmaster",
})


# ─────────────────────────────────────────────────────────────────────────────
# Data models
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class CandidateSignals:
    homepage: str | None = None
    profile_url: str | None = None
    email: str | None = None
    github: str | None = None
    scholar: str | None = None
    linkedin: str | None = None
    affiliation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ParsedCandidateRecord:
    professor: str
    source_url: str
    name: str
    role: str
    section: str | None
    homepage: str | None
    email: str | None
    github: str | None
    scholar: str | None
    linkedin: str | None
    validation_status: str  # accepted | rejected
    reason_rejected: str | None
    rejection_stage: str | None
    validator_rules: list[str] = field(default_factory=list)
    is_exported: bool = False
    bucket: str = "PARTIAL"
    bucket_reason: str = ""
    preservation_confidence: float = 0.0
    member_status: str = "CURRENT"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class UnresolvedCandidate:
    professor: str
    name: str
    role: str
    section: str | None
    homepage: str | None
    email: str | None
    github: str | None
    scholar: str | None
    linkedin: str | None
    source: str
    reason: str
    confidence: float
    bucket: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProfessorPreservationGain:
    professor: str
    currently_exported: int
    additional_preservable: int
    resolvable: int
    partial: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class IdentityPreservationReport:
    generated_at: str
    source_graph: str
    professor_filter: str | None
    limit: int | None
    pages_analyzed: int
    professors_analyzed: int
    bucket_counts: dict[str, int]
    bucket_unique_counts: dict[str, int]
    rejection_reason_breakdown: list[dict[str, Any]]
    recovery_estimate: dict[str, Any]
    unresolved_candidates: list[UnresolvedCandidate]
    top_preservation_gains: list[ProfessorPreservationGain]
    all_candidates: list[ParsedCandidateRecord]
    executive_answers: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "source_graph": self.source_graph,
            "professor_filter": self.professor_filter,
            "limit": self.limit,
            "pages_analyzed": self.pages_analyzed,
            "professors_analyzed": self.professors_analyzed,
            "bucket_counts": self.bucket_counts,
            "bucket_unique_counts": self.bucket_unique_counts,
            "rejection_reason_breakdown": self.rejection_reason_breakdown,
            "recovery_estimate": self.recovery_estimate,
            "unresolved_candidates": [u.to_dict() for u in self.unresolved_candidates],
            "top_preservation_gains": [p.to_dict() for p in self.top_preservation_gains],
            "all_candidates": [c.to_dict() for c in self.all_candidates],
            "executive_answers": self.executive_answers,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Signal extraction & classification (audit-only)
# ─────────────────────────────────────────────────────────────────────────────


def _extract_signals_extended(entry: Any) -> CandidateSignals:
    """Extend validator-funnel signal extraction with LinkedIn."""
    base = _extract_signals(entry)
    linkedin = None
    all_urls: list[str] = []
    if base.profile_url:
        all_urls.append(base.profile_url)
    for link in getattr(entry, "links", []) or []:
        url = getattr(link, "absolute_url", None) or getattr(link, "href", None)
        if url:
            all_urls.append(url)
    for url in all_urls:
        if "linkedin.com" in urlparse(url).netloc.lower():
            linkedin = url
            break
    return CandidateSignals(
        homepage=base.homepage,
        profile_url=base.profile_url,
        email=base.email,
        github=base.github,
        scholar=base.scholar,
        linkedin=linkedin,
        affiliation=base.affiliation,
    )


def _has_homepage_or_profile(signals: CandidateSignals) -> bool:
    if signals.homepage:
        return True
    if signals.profile_url and PersonValidator._is_personal_profile_url(signals.profile_url):
        return True
    return False


def _section_suggests_alumni(section_name: str | None) -> bool:
    if not section_name:
        return False
    normalized = section_name.lower().strip()
    return any(hint in normalized for hint in ALUMNI_SECTION_KEYWORDS) or any(
        token in normalized for token in ("past ", "former ", "alumni", "graduated")
    )


def _section_suggests_current_student(section_name: str | None) -> bool:
    if not section_name:
        return False
    normalized = section_name.lower().strip()
    return any(hint in normalized for hint in CURRENT_STUDENT_SECTION_HINTS)


def _is_obvious_non_person(entry: Any) -> bool:
    name = (entry.name or "").lower()
    haystack = f"{name} {entry.raw_text or ''} {entry.role_hint or ''}".lower()
    for pattern in PERSON_NEGATIVE_NAME_PATTERNS:
        if pattern in name:
            return True
    for keyword in PERSON_NEGATIVE_KEYWORDS:
        if keyword in haystack:
            return True
    return False


def _is_administrative(role: MemberRole, entry: Any) -> bool:
    haystack = f"{entry.role_hint or ''} {entry.section_name or ''} {entry.raw_text or ''}".lower()
    if role == MemberRole.RESEARCH_STAFF and any(h in haystack for h in _ADMIN_ROLE_HINTS):
        return True
    return any(h in haystack for h in _ADMIN_ROLE_HINTS)


def _has_strong_affiliation(entry: Any, role: MemberRole, signals: CandidateSignals) -> bool:
    if not entry.in_member_section:
        return False
    if role in STUDENT_ROLES and role != MemberRole.UNKNOWN:
        return True
    if _section_suggests_current_student(entry.section_name):
        return True
    haystack = f"{entry.raw_text or ''} {entry.role_hint or ''} {signals.affiliation or ''}".lower()
    university_hints = (
        "university",
        "institute of technology",
        "department of",
        "school of",
        "college of",
        "laboratory",
        "research group",
        "lab ",
    )
    return any(hint in haystack for hint in university_hints)


def _has_external_identity(signals: CandidateSignals) -> bool:
    return bool(signals.email or signals.github or signals.scholar or signals.linkedin)


def _classify_bucket(
    entry: Any,
    role: MemberRole,
    signals: CandidateSignals,
    *,
    is_exported: bool,
    validation_accepted: bool,
) -> tuple[str, str]:
    """Classify a parsed candidate into VERIFIED / RESOLVABLE / PARTIAL / INVALID."""
    if _is_obvious_non_person(entry):
        return "INVALID", "Parser noise / non-person pattern"

    if not PersonValidator._looks_like_person_name(entry.name):
        return "INVALID", "Does not resemble a person name"

    if not entry.in_member_section:
        return "INVALID", "Navigation / outside member section"

    if role == MemberRole.PROFESSOR:
        return "INVALID", "Faculty / PI entry"

    if _is_administrative(role, entry):
        return "INVALID", "Administrative staff"

    if entry.member_status == MemberStatus.ALUMNI or _section_suggests_alumni(entry.section_name):
        return "INVALID", "Alumni / former member section"

    if signals.profile_url:
        url_lower = signals.profile_url.lower()
        for pattern in PERSON_NEGATIVE_URL_PATTERNS:
            if pattern in url_lower:
                return "INVALID", f"Negative profile URL ({pattern})"

    has_homepage = _has_homepage_or_profile(signals)
    if has_homepage and is_exported:
        return "VERIFIED", "Has homepage/profile URL and accepted in current export"

    if has_homepage and validation_accepted:
        return "VERIFIED", "Has homepage/profile URL and passed validation"

    if _has_external_identity(signals) or _has_strong_affiliation(entry, role, signals):
        return "RESOLVABLE", "No homepage but has resolvable identity or affiliation signals"

    if entry.name and (entry.section_name or entry.role_hint or role != MemberRole.UNKNOWN):
        return "PARTIAL", "Name + role/section only; no external identity evidence"

    return "INVALID", "Insufficient member signals"


def _preservation_confidence(
    bucket: str,
    entry: Any,
    role: MemberRole,
    signals: CandidateSignals,
    validation_confidence: float | None,
) -> float:
    if bucket == "INVALID":
        return 0.0
    if bucket == "VERIFIED":
        return 1.0

    score = 0.35
    if _NAME_PATTERN.match(entry.name):
        score += 0.10
    if entry.in_member_section:
        score += 0.10
    if role in {MemberRole.PHD_STUDENT, MemberRole.MASTER_STUDENT}:
        score += 0.15
    elif role in STUDENT_ROLES:
        score += 0.08
    if _section_suggests_current_student(entry.section_name):
        score += 0.10
    if signals.email:
        score += 0.12
    if signals.github or signals.scholar:
        score += 0.08
    if signals.linkedin:
        score += 0.05
    if _has_strong_affiliation(entry, role, signals):
        score += 0.07
    if validation_confidence is not None and validation_confidence > 0:
        score = max(score, min(0.95, validation_confidence + 0.15))

    if bucket == "RESOLVABLE":
        score = max(score, 0.65)
    elif bucket == "PARTIAL":
        score = min(score, 0.82)

    return round(min(0.95, max(0.40, score)), 2)


def _unresolved_reason(
    bucket: str,
    validation_reason: str | None,
    rejection_stage: str | None,
    validator_rules: list[str],
) -> str:
    if bucket == "RESOLVABLE":
        if validation_reason and "missing personal profile" in validation_reason.lower():
            return "Missing identity only"
        if rejection_stage == "adaptive_cap":
            return "Adaptive cap (has resolvable signals)"
        return "Missing homepage; resolvable via external profiles"
    if bucket == "PARTIAL":
        if validation_reason and "missing personal profile" in validation_reason.lower():
            return "Missing identity only"
        if validation_reason and "low confidence" in validation_reason.lower():
            return "Missing identity only"
        if validator_rules:
            return f"Missing identity only ({validator_rules[0]})"
        return "Missing identity only"
    return validation_reason or "Not exported"


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline replay
# ─────────────────────────────────────────────────────────────────────────────


def _build_exported_keys(
    graphs: list[dict[str, Any]],
    *,
    parser: MemberPageParser,
    extractor: MemberExtractor,
    department_detector: DepartmentScopeDetector,
) -> dict[str, set[str]]:
    exported: dict[str, set[str]] = defaultdict(set)
    for graph in graphs:
        professor = graph.get("professor_name", "")
        urls = list(dict.fromkeys(graph.get("parsed_pages") or []))
        group_page = graph.get("group_page")
        if group_page and group_page.get("url"):
            urls = list(dict.fromkeys(urls + [group_page["url"]]))

        page_results: list[tuple[str, list, list]] = []
        for url in urls:
            html, final_url = _read_cached(url)
            if not html:
                continue
            parsed = parser.parse(html, final_url or url)
            department_scope = department_detector.detect(
                parsed=parsed,
                page_url=final_url or url,
                page_title=parsed.page_title,
            )
            group_page_sel = GroupPageSelection(
                url=final_url or url,
                source_node_type="identity_preservation_audit",
                confidence=1.0,
                reason="offline_replay",
            )
            with contextlib.redirect_stdout(io.StringIO()):
                extraction = extractor.extract(
                    professor_name=professor,
                    group_page=group_page_sel,
                    parsed=parsed,
                    page_url=final_url or url,
                    department_scope=department_scope,
                )
            current_profiles = [_to_talent_profile(m) for m in extraction.members]
            former_profiles = [_to_talent_profile(m) for m in extraction.former_members]
            if current_profiles or former_profiles:
                page_results.append((final_url or url, current_profiles, former_profiles))

        if page_results:
            merged = MemberMerger().merge(page_results)
            for member in merged["current"]:
                exported[professor].add(member.person.name.lower())
    return exported


def _trace_candidates_for_page(
    *,
    professor: str,
    page_url: str,
    html: str,
    final_url: str,
    parser: MemberPageParser,
    validator: PersonValidator,
    stub: StubResearchGroupProvider,
    exported_keys: set[str],
) -> list[ParsedCandidateRecord]:
    parsed = parser.parse(html, final_url or page_url)
    professor_lower = professor.lower()
    records: list[ParsedCandidateRecord] = []

    for entry in parsed.entries:
        if entry.name.lower() == professor_lower:
            continue

        role = stub._classify_role(entry.section_role, entry.role_hint, entry.raw_text)
        signals = _extract_signals_extended(entry)
        validation = validator.validate(
            name=entry.name,
            profile_url=entry.profile_url,
            section_name=entry.section_name,
            section_role=entry.section_role,
            role_hint=entry.role_hint,
            raw_text=entry.raw_text,
            in_member_section=entry.in_member_section,
        )

        is_exported = entry.name.lower() in exported_keys
        bucket, bucket_reason = _classify_bucket(
            entry,
            role,
            signals,
            is_exported=is_exported,
            validation_accepted=validation.is_valid,
        )

        rejection_stage: str | None = None
        validator_rules: list[str] = []
        reason_rejected: str | None = None

        if not validation.is_valid:
            rejection_stage = "validator"
            reason_rejected = validation.reason
            validator_rules = [
                _classify_validator_rule(validation.reason, role=role, stage="validator")
            ]
        elif not is_exported:
            confidence = stub._extraction_confidence(entry, role, validation.confidence)
            if confidence < stub.MIN_EXTRACTION_CONFIDENCE:
                rejection_stage = "extraction_confidence"
                reason_rejected = f"low extraction confidence ({confidence:.2f})"
                validator_rules = ["Low extraction confidence"]
            else:
                rejection_stage = "not_exported"
                reason_rejected = "Passed validation but not in merged export"

        conf = _preservation_confidence(
            bucket,
            entry,
            role,
            signals,
            validation.confidence if validation.is_valid else validation.confidence,
        )

        records.append(
            ParsedCandidateRecord(
                professor=professor,
                source_url=final_url or page_url,
                name=entry.name,
                role=role.value,
                section=entry.section_name,
                homepage=signals.homepage,
                email=signals.email,
                github=signals.github,
                scholar=signals.scholar,
                linkedin=signals.linkedin,
                validation_status="accepted" if validation.is_valid else "rejected",
                reason_rejected=reason_rejected,
                rejection_stage=rejection_stage,
                validator_rules=validator_rules,
                is_exported=is_exported,
                bucket=bucket,
                bucket_reason=bucket_reason,
                preservation_confidence=conf,
                member_status=entry.member_status.value,
            )
        )

    return records


def run_audit(
    *,
    graph_path: Path | None = None,
    limit: int | None = None,
    professor_filter: str | None = None,
) -> IdentityPreservationReport:
    source = resolve_graph_path(graph_path)
    graphs: list[dict[str, Any]] = json.loads(source.read_text(encoding="utf-8"))
    if professor_filter:
        pf = professor_filter.lower()
        graphs = [g for g in graphs if g.get("professor_name", "").lower() == pf]
    if limit:
        graphs = graphs[:limit]

    parser = MemberPageParser()
    validator = PersonValidator()
    stub = StubResearchGroupProvider(validator=validator)
    extractor = MemberExtractor(provider=stub)
    department_detector = DepartmentScopeDetector()

    exported_by_professor = _build_exported_keys(
        graphs,
        parser=parser,
        extractor=extractor,
        department_detector=department_detector,
    )

    all_candidates: list[ParsedCandidateRecord] = []
    pages_analyzed = 0

    for graph in graphs:
        professor = graph.get("professor_name", "")
        exported_keys = exported_by_professor.get(professor, set())
        urls = list(dict.fromkeys(graph.get("parsed_pages") or []))
        group_page = graph.get("group_page")
        if group_page and group_page.get("url"):
            urls = list(dict.fromkeys(urls + [group_page["url"]]))

        for url in urls:
            html, final_url = _read_cached(url)
            if not html:
                continue
            pages_analyzed += 1
            records = _trace_candidates_for_page(
                professor=professor,
                page_url=url,
                html=html,
                final_url=final_url or url,
                parser=parser,
                validator=validator,
                stub=stub,
                exported_keys=exported_keys,
            )
            all_candidates.extend(records)

    bucket_counts = Counter(c.bucket for c in all_candidates)
    unique_by_bucket: dict[str, set[tuple[str, str]]] = {b: set() for b in BUCKETS}
    for c in all_candidates:
        unique_by_bucket[c.bucket].add((c.professor, c.name.lower()))

    currently_exported = sum(len(keys) for keys in exported_by_professor.values())
    preservable = [c for c in all_candidates if c.bucket in {"RESOLVABLE", "PARTIAL"}]

    # Best record per (professor, name) for bucket assignment and export status.
    best_by_key: dict[tuple[str, str], ParsedCandidateRecord] = {}
    for c in preservable:
        key = (c.professor, c.name.lower())
        prev = best_by_key.get(key)
        if prev is None or (c.is_exported and not prev.is_exported):
            best_by_key[key] = c
        elif not c.is_exported and not prev.is_exported:
            if c.preservation_confidence > prev.preservation_confidence:
                best_by_key[key] = c

    preservable_unique: set[tuple[str, str]] = set(best_by_key.keys())
    unresolved_unique: set[tuple[str, str]] = {
        key for key, rec in best_by_key.items() if not rec.is_exported
    }
    unresolved_resolvable_unique: set[tuple[str, str]] = {
        key for key, rec in best_by_key.items()
        if rec.bucket == "RESOLVABLE" and not rec.is_exported
    }
    unresolved_partial_unique: set[tuple[str, str]] = {
        key for key, rec in best_by_key.items()
        if rec.bucket == "PARTIAL" and not rec.is_exported
    }

    rejection_counter: Counter[str] = Counter()
    for key in unresolved_unique:
        rec = best_by_key[key]
        if rec.validator_rules:
            rule = rec.validator_rules[0]
        elif rec.reason_rejected and "missing personal profile" in rec.reason_rejected.lower():
            rule = "Missing profile URL"
        elif rec.bucket == "PARTIAL":
            rule = "Missing identity only (name + role/section)"
        else:
            rule = rec.reason_rejected or "Missing identity only"
        rejection_counter[rule] += 1

    per_professor_gain: dict[str, ProfessorPreservationGain] = {}
    for graph in graphs:
        professor = graph.get("professor_name", "")
        exported = len(exported_by_professor.get(professor, set()))
        prof_keys = [k for k in best_by_key if k[0] == professor]
        prof_unresolved = {
            k[1] for k in prof_keys if not best_by_key[k].is_exported
        }
        per_professor_gain[professor] = ProfessorPreservationGain(
            professor=professor,
            currently_exported=exported,
            additional_preservable=len(prof_unresolved),
            resolvable=len({k[1] for k in prof_keys if best_by_key[k].bucket == "RESOLVABLE" and not best_by_key[k].is_exported}),
            partial=len({k[1] for k in prof_keys if best_by_key[k].bucket == "PARTIAL" and not best_by_key[k].is_exported}),
        )

    top_gains = sorted(
        per_professor_gain.values(),
        key=lambda p: (-p.additional_preservable, -p.resolvable, p.professor),
    )[:20]

    unresolved: list[UnresolvedCandidate] = []
    for key in sorted(
        unresolved_unique,
        key=lambda k: (
            -best_by_key[k].preservation_confidence,
            best_by_key[k].professor,
            best_by_key[k].name,
        ),
    ):
        c = best_by_key[key]
        unresolved.append(
            UnresolvedCandidate(
                professor=c.professor,
                name=c.name,
                role=c.role,
                section=c.section,
                homepage=c.homepage,
                email=c.email,
                github=c.github,
                scholar=c.scholar,
                linkedin=c.linkedin,
                source=c.source_url,
                reason=_unresolved_reason(
                    c.bucket,
                    c.reason_rejected,
                    c.rejection_stage,
                    c.validator_rules,
                ),
                confidence=c.preservation_confidence,
                bucket=c.bucket,
            )
        )

    missing_identity_only = sum(
        1
        for u in unresolved
        if "missing identity" in u.reason.lower()
    )

    thrown_away = len(unresolved_unique)
    executive = {
        "names_currently_thrown_away": thrown_away,
        "preservable_bucket_total": len(preservable_unique),
        "already_exported_without_homepage": len(preservable_unique) - thrown_away,
        "throw_away_breakdown": {
            "unresolved_resolvable": len(unresolved_resolvable_unique),
            "unresolved_partial": len(unresolved_partial_unique),
            "invalid_parser_noise": len(unique_by_bucket["INVALID"]),
        },
        "resolvable_for_future_identity_resolution": len(unresolved_resolvable_unique),
        "name_only_partial": len(unresolved_partial_unique),
        "talent_graph_growth_if_preserved": {
            "currently_exported": currently_exported,
            "additional_unresolved": thrown_away,
            "projected_total": currently_exported + thrown_away,
            "growth_pct": round(
                100.0 * thrown_away / max(1, currently_exported),
                1,
            ),
        },
        "identity_preservation_vs_validator_work": {
            "preservation_gain_unique": thrown_away,
            "missing_identity_only_count": missing_identity_only,
            "recommendation": (
                "Identity preservation is higher ROI"
                if thrown_away > 200
                else "Further validator/parser work may be competitive"
            ),
        },
    }

    recovery_estimate = {
        "currently_exported": currently_exported,
        "total_parsed_candidates": len(all_candidates),
        "preservable_bucket_unique": len(preservable_unique),
        "additional_names_preserved": thrown_away,
        "of_those_resolvable": len(unresolved_resolvable_unique),
        "of_those_partial": len(unresolved_partial_unique),
        "average_preserved_names_per_professor": round(
            thrown_away / max(1, len(graphs)),
            2,
        ),
        "projected_talent_graph_size": currently_exported + thrown_away,
        "growth_factor": round(
            (currently_exported + thrown_away) / max(1, currently_exported),
            2,
        ),
    }

    return IdentityPreservationReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        source_graph=str(source),
        professor_filter=professor_filter,
        limit=limit,
        pages_analyzed=pages_analyzed,
        professors_analyzed=len(graphs),
        bucket_counts={b: bucket_counts.get(b, 0) for b in BUCKETS},
        bucket_unique_counts={b: len(unique_by_bucket[b]) for b in BUCKETS},
        rejection_reason_breakdown=[
            {"reason": reason, "count": count}
            for reason, count in rejection_counter.most_common()
        ],
        recovery_estimate=recovery_estimate,
        unresolved_candidates=unresolved,
        top_preservation_gains=top_gains,
        all_candidates=all_candidates,
        executive_answers=executive,
    )


def render_markdown(report: IdentityPreservationReport) -> str:
    bc = report.bucket_counts
    bu = report.bucket_unique_counts
    rec = report.recovery_estimate
    exec_a = report.executive_answers
    growth = exec_a["talent_graph_growth_if_preserved"]

    lines = [
        "# Sprint X — Identity Preservation Audit",
        "",
        f"Generated: {report.generated_at}",
        f"Source: `{report.source_graph}`",
        f"Pages analyzed: {report.pages_analyzed} | Professors: {report.professors_analyzed}",
        "",
        "## Executive Summary",
        "",
        f"- **Total parsed candidates:** {rec['total_parsed_candidates']}",
        f"- **Currently exported (VERIFIED):** {rec['currently_exported']} unique members",
        f"- **Preservable bucket (RESOLVABLE + PARTIAL):** {rec['preservable_bucket_unique']} unique",
        f"- **Unresolved / thrown away (not exported):** {rec['additional_names_preserved']} unique "
        f"(RESOLVABLE: {rec['of_those_resolvable']}, PARTIAL: {rec['of_those_partial']})",
        f"- **Projected talent graph if preserved:** {rec['projected_talent_graph_size']} "
        f"(+{growth['growth_pct']}% vs current export)",
        "",
        "### Success Criteria Answers",
        "",
        f"1. **How many names are we currently throwing away?** "
        f"**{exec_a['names_currently_thrown_away']}** unique members not in current export "
        f"({exec_a['preservable_bucket_total']} in preservable buckets; "
        f"{exec_a['already_exported_without_homepage']} already exported without homepage).",
        f"2. **Why are they being discarded?** Primarily missing homepage/profile URL "
        f"and PersonValidator identity-anchor rules. See rejection breakdown below.",
        f"3. **How many have enough information to resolve later?** "
        f"**{exec_a['resolvable_for_future_identity_resolution']}** (email, GitHub, Scholar, "
        f"LinkedIn, or strong affiliation).",
        f"4. **How many only have a name?** **{exec_a['name_only_partial']}** PARTIAL "
        f"(name + role/section, no external identity).",
        f"5. **Talent graph growth if we preserve instead of drop?** "
        f"{growth['currently_exported']} → {growth['projected_total']} "
        f"(+{growth['additional_unresolved']} members, +{growth['growth_pct']}%).",
        f"6. **Identity Preservation vs validator/parser ROI?** "
        f"{exec_a['identity_preservation_vs_validator_work']['recommendation']} — "
        f"preservation unlocks **{exec_a['identity_preservation_vs_validator_work']['preservation_gain_unique']}** "
        f"names vs incremental validator tuning.",
        "",
        "## Bucket Classification",
        "",
        "| Bucket | Parsed (raw) | Unique (professor, name) | Definition |",
        "|---|---:|---:|---|",
        f"| VERIFIED | {bc['VERIFIED']} | {bu['VERIFIED']} | Has homepage/profile URL; accepted in export |",
        f"| RESOLVABLE | {bc['RESOLVABLE']} | {bu['RESOLVABLE']} | No homepage; email/GitHub/Scholar/LinkedIn or strong affiliation |",
        f"| PARTIAL | {bc['PARTIAL']} | {bu['PARTIAL']} | Name + role/section only |",
        f"| INVALID | {bc['INVALID']} | {bu['INVALID']} | Parser noise, navigation, faculty, admin |",
        "",
        "## Rejection Reasons (RESOLVABLE + PARTIAL, not exported)",
        "",
        "| Reason | Count |",
        "|---|---:|",
    ]
    for row in report.rejection_reason_breakdown[:20]:
        lines.append(f"| {row['reason']} | {row['count']} |")
    if not report.rejection_reason_breakdown:
        lines.append("| _none_ | 0 |")

    lines.extend([
        "",
        "## Future Recovery Estimate",
        "",
        f"- Currently exported: **{rec['currently_exported']}**",
        f"- Additional names preserved (unresolved): **{rec['additional_names_preserved']}**",
        f"  - Resolvable: **{rec['of_those_resolvable']}**",
        f"  - Partial: **{rec['of_those_partial']}**",
        f"- Average preserved names per professor: **{rec['average_preserved_names_per_professor']}**",
        f"- Growth factor: **{rec['growth_factor']}×**",
        "",
        "## Top 20 Professors — Largest Preservation Gain",
        "",
        "| Professor | Exported | Additional Preservable | Resolvable | Partial |",
        "|---|---:|---:|---:|---:|",
    ])
    for row in report.top_preservation_gains:
        lines.append(
            f"| {row.professor} | {row.currently_exported} | "
            f"{row.additional_preservable} | {row.resolvable} | {row.partial} |"
        )

    lines.extend([
        "",
        "## Unresolved Candidates (feed to OpenAlex / DBLP / Scholar)",
        "",
        f"Total unique unresolved: **{len(report.unresolved_candidates)}**",
        "",
    ])

    for idx, u in enumerate(report.unresolved_candidates[:100], 1):
        lines.extend([
            f"### {idx}. {u.name}",
            "",
            f"**Professor:** {u.professor}",
            "",
            "**Candidate:**",
            f"- **Name:** {u.name}",
            f"- **Role:** {u.role}",
            f"- **Section:** {u.section or 'None'}",
            f"- **Homepage:** {u.homepage or 'None'}",
            f"- **Email:** {u.email or 'None'}",
            f"- **Github:** {u.github or 'None'}",
            f"- **Scholar:** {u.scholar or 'None'}",
            f"- **LinkedIn:** {u.linkedin or 'None'}",
            f"- **Source:** {u.source}",
            f"- **Reason:** {u.reason}",
            f"- **Confidence:** {u.confidence:.2f}",
            f"- **Bucket:** {u.bucket}",
            "",
        ])

    if len(report.unresolved_candidates) > 100:
        lines.append(
            f"_Showing first 100 of {len(report.unresolved_candidates)} unresolved candidates. "
            f"Full list in `IDENTITY_PRESERVATION.json`._"
        )
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sprint X identity preservation audit (read-only)"
    )
    parser.add_argument("--graph", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--professor", type=str, default=None)
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report = run_audit(
        graph_path=args.graph,
        limit=args.limit,
        professor_filter=args.professor,
    )

    OUT_JSON.write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    OUT_MD.write_text(render_markdown(report), encoding="utf-8")

    rec = report.recovery_estimate
    print(f"Wrote {OUT_MD}")
    print(f"Wrote {OUT_JSON}")
    print(
        f"[Identity Preservation] parsed={rec['total_parsed_candidates']} "
        f"exported={rec['currently_exported']} "
        f"unresolved={rec['additional_names_preserved']} "
        f"(resolvable={rec['of_those_resolvable']}, partial={rec['of_those_partial']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
