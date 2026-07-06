import json
import re
from dataclasses import dataclass
from pathlib import Path

DEFAULT_UNIVERSITIES_PATH = (
    Path(__file__).resolve().parent.parent / "resources" / "us_universities.json"
)


@dataclass
class MatchResult:
    canonical: str | None
    country: str | None
    confidence: float


class USUniversityMatcher:
    """
    Match a raw DBLP affiliation string against a curated list of US
    universities (resources/us_universities.json).

    No Geo API, no network calls. All matching heuristics live here, not
    in the JSON resource — the resource stays plain data (canonical name +
    aliases + country) so it's easy to review/extend as a diff.

    Confidence tiers:
      1.0  exact match of a segment against the canonical name
      0.85 exact match of a segment against a known alias
      0.6  canonical/alias found as a substring of the full affiliation
      0.0  no match
    """

    def __init__(self, universities_path: Path | str = DEFAULT_UNIVERSITIES_PATH):
        with open(universities_path, "r", encoding="utf-8") as f:
            self._entries = json.load(f)

        self._exact: dict[str, dict] = {}
        self._alias: dict[str, dict] = {}

        for entry in self._entries:
            self._exact[self._normalize(entry["canonical"])] = entry

            for alias in entry.get("aliases", []):
                self._alias[self._normalize(alias)] = entry

    @staticmethod
    def _normalize(text: str) -> str:
        text = text.lower().strip()
        text = re.sub(r"[.,]", "", text)
        text = re.sub(r"\s+", " ", text)
        return text

    def _segments(self, raw_affiliation: str) -> list[str]:
        segments = [self._normalize(s) for s in raw_affiliation.split(",")]
        segments.append(self._normalize(raw_affiliation))
        return [s for s in segments if s]

    def match(self, raw_affiliation: str | None) -> MatchResult:
        if not raw_affiliation:
            return MatchResult(None, None, 0.0)

        segments = self._segments(raw_affiliation)

        for segment in segments:
            entry = self._exact.get(segment)
            if entry:
                return MatchResult(entry["canonical"], entry["country"], 1.0)

        for segment in segments:
            entry = self._alias.get(segment)
            if entry:
                return MatchResult(entry["canonical"], entry["country"], 0.85)

        # Substring containment: canonical/alias found inside the FULL
        # normalized affiliation string — one direction only.
        #
        # This is deliberately not checked fragment-vs-fragment on
        # comma-split segments, and not checked in the reverse direction
        # (segment-is-substring-of-canonical). Two real false positives
        # were found empirically doing it that way:
        #   - a bare two-letter segment from a US state code ("WA", "CA")
        #     is a substring of an unrelated long canonical name (e.g. "WA"
        #     inside "george WAshington university", "CA" inside
        #     "CAlifornia institute of technology") — a state code should
        #     never resolve a university by itself.
        #   - some university names are themselves comma-containing (e.g.
        #     "University of California, San Diego"), so naive comma
        #     splitting produces a fragment ("San Diego") that happens to
        #     prefix-match a *different*, unrelated university ("San Diego
        #     State University"). Matching canonical-in-full-string instead
        #     of fragment-in-canonical avoids this: "san diego state
        #     university" is not a substring of "university of california
        #     san diego ca usa", but "university of california san diego"
        #     correctly is.
        MIN_SUBSTRING_LEN = 5
        normalized_full = self._normalize(raw_affiliation)

        for norm_key, entry in {**self._exact, **self._alias}.items():
            if len(norm_key) < MIN_SUBSTRING_LEN:
                continue

            if norm_key in normalized_full:
                return MatchResult(entry["canonical"], entry["country"], 0.6)

        return MatchResult(None, None, 0.0)
