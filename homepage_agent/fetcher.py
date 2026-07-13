"""HTTP fetcher for professor homepages — no AI, reusable by future PRs."""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import requests
from requests.exceptions import ConnectTimeout, ReadTimeout, Timeout, TooManyRedirects

from homepage_agent.models import FetchStatus, HomepageDocument

logger = logging.getLogger(__name__)

SLOW_FETCH_THRESHOLD_SECONDS = 5.0


@dataclass
class FetchStats:
    """Aggregated HTTP fetch metrics for validation and observability."""

    total_requests: int = 0
    successful: int = 0
    timeouts: int = 0
    network_errors: int = 0
    redirect_limit_exceeded: int = 0
    latencies: list[float] = field(default_factory=list)
    slow_requests: int = 0

    def record(
        self,
        latency: float,
        status: FetchStatus,
        *,
        redirect_limit: bool = False,
        slow_threshold: float = SLOW_FETCH_THRESHOLD_SECONDS,
    ) -> None:
        self.total_requests += 1
        self.latencies.append(latency)
        if latency >= slow_threshold:
            self.slow_requests += 1
        if redirect_limit:
            self.redirect_limit_exceeded += 1
        elif status == FetchStatus.SUCCESS:
            self.successful += 1
        elif status == FetchStatus.TIMEOUT:
            self.timeouts += 1
        else:
            self.network_errors += 1

    def reset(self) -> None:
        self.total_requests = 0
        self.successful = 0
        self.timeouts = 0
        self.network_errors = 0
        self.redirect_limit_exceeded = 0
        self.latencies.clear()
        self.slow_requests = 0

    @staticmethod
    def _percentile(values: list[float], percent: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        rank = (len(ordered) - 1) * (percent / 100.0)
        lower = int(rank)
        upper = min(lower + 1, len(ordered) - 1)
        weight = rank - lower
        return ordered[lower] + (ordered[upper] - ordered[lower]) * weight

    def average_latency(self) -> float:
        if not self.latencies:
            return 0.0
        return sum(self.latencies) / len(self.latencies)

    def percentile_latency(self, percent: float) -> float:
        return self._percentile(self.latencies, percent)

    def to_dict(self) -> dict[str, float | int]:
        return {
            "total_requests": self.total_requests,
            "successful": self.successful,
            "timeouts": self.timeouts,
            "network_errors": self.network_errors,
            "redirect_limit_exceeded": self.redirect_limit_exceeded,
            "average_latency": round(self.average_latency(), 2),
            "p95_latency": round(self.percentile_latency(95), 2),
            "slow_requests": self.slow_requests,
        }

    def format_summary(self) -> str:
        return "\n".join(
            [
                "========== Fetch Summary ==========",
                f"Total requests: {self.total_requests}",
                f"Successful: {self.successful}",
                f"Timeouts: {self.timeouts}",
                f"Network errors: {self.network_errors}",
                f"Redirect limit exceeded: {self.redirect_limit_exceeded}",
                f"Average latency: {self.average_latency():.2f}s",
                f"95th percentile latency: {self.percentile_latency(95):.2f}s",
                f"Slow requests (>5s): {self.slow_requests}",
                "===================================",
            ]
        )


class HomepageFetcher:
    """
    Fetch a homepage URL with timeout, retry, redirect handling, and optional cache.

    Designed as a standalone stage so future PRs can reuse the same fetch layer.
    """

    DEFAULT_CONNECT_TIMEOUT = 5
    DEFAULT_READ_TIMEOUT = 10
    DEFAULT_TIMEOUT = (DEFAULT_CONNECT_TIMEOUT, DEFAULT_READ_TIMEOUT)
    DEFAULT_RETRIES = 2
    DEFAULT_BACKOFF = 1.0
    DEFAULT_MAX_REDIRECTS = 5
    SLOW_FETCH_THRESHOLD_SECONDS = SLOW_FETCH_THRESHOLD_SECONDS

    USER_AGENT = (
        "InfraProfessorMapping/1.0 (+https://github.com/infra-professor-mapping; "
        "homepage-intelligence-agent)"
    )

    def __init__(
        self,
        timeout: float | tuple[float, float] = DEFAULT_TIMEOUT,
        retries: int = DEFAULT_RETRIES,
        backoff: float = DEFAULT_BACKOFF,
        max_redirects: int = DEFAULT_MAX_REDIRECTS,
        cache_dir: str | Path | None = "data/cache/homepages",
        use_cache: bool = True,
        stats: FetchStats | None = None,
    ):
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self.max_redirects = max_redirects
        self.use_cache = use_cache
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self._stats = stats if stats is not None else FetchStats()
        if self.cache_dir and self.use_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

        self._session = requests.Session()
        self._session.max_redirects = max_redirects
        self._session.headers.update({"User-Agent": self.USER_AGENT})

    @property
    def stats(self) -> FetchStats:
        return self._stats

    def fetch(self, url: str) -> HomepageDocument:
        normalized = self._normalize_url(url)
        if not normalized:
            return HomepageDocument(
                url=url,
                html="",
                title="",
                fetch_status=FetchStatus.INVALID_URL,
                error_message=f"Invalid homepage URL: {url}",
            )

        if self.use_cache and self.cache_dir:
            cached = self._read_cache(normalized)
            if cached is not None:
                return cached

        document = self._fetch_with_retries(normalized)

        if (
            self.use_cache
            and self.cache_dir
            and document.fetch_status == FetchStatus.SUCCESS
        ):
            self._write_cache(normalized, document)

        return document

    def _normalize_url(self, url: str) -> str | None:
        url = (url or "").strip()
        if not url:
            return None
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        parsed = urlparse(url)
        if not parsed.netloc:
            return None
        return url

    def _fetch_with_retries(self, url: str) -> HomepageDocument:
        last_error: str | None = None

        for attempt in range(self.retries + 1):
            started_at = time.monotonic()
            try:
                response = self._session.get(
                    url,
                    timeout=self.timeout,
                    allow_redirects=True,
                )
                self._log_slow_fetch(url, started_at)

                final_url = response.url
                status_code = response.status_code

                if status_code >= 400:
                    self._record_request(started_at, FetchStatus.HTTP_ERROR)
                    return HomepageDocument(
                        url=url,
                        html="",
                        title="",
                        fetch_status=FetchStatus.HTTP_ERROR,
                        final_url=final_url,
                        status_code=status_code,
                        error_message=f"HTTP {status_code}",
                    )

                html = response.text or ""
                if not html.strip():
                    self._record_request(started_at, FetchStatus.EMPTY_RESPONSE)
                    return HomepageDocument(
                        url=url,
                        html="",
                        title="",
                        fetch_status=FetchStatus.EMPTY_RESPONSE,
                        final_url=final_url,
                        status_code=status_code,
                        error_message="Empty response body",
                    )

                title = self._extract_title(html)
                self._record_request(started_at, FetchStatus.SUCCESS)
                return HomepageDocument(
                    url=url,
                    html=html,
                    title=title,
                    fetch_status=FetchStatus.SUCCESS,
                    final_url=final_url,
                    status_code=status_code,
                )

            except ReadTimeout as exc:
                self._log_slow_fetch(url, started_at)
                self._record_request(started_at, FetchStatus.TIMEOUT)
                logger.warning("Read timeout fetching %s: %s", url, exc)
                return HomepageDocument(
                    url=url,
                    html="",
                    title="",
                    fetch_status=FetchStatus.TIMEOUT,
                    error_message=str(exc),
                )

            except ConnectTimeout as exc:
                self._log_slow_fetch(url, started_at)
                self._record_request(started_at, FetchStatus.TIMEOUT)
                logger.warning("Connect timeout fetching %s: %s", url, exc)
                return HomepageDocument(
                    url=url,
                    html="",
                    title="",
                    fetch_status=FetchStatus.TIMEOUT,
                    error_message=str(exc),
                )

            except Timeout as exc:
                self._log_slow_fetch(url, started_at)
                self._record_request(started_at, FetchStatus.TIMEOUT)
                logger.warning("Timeout fetching %s: %s", url, exc)
                return HomepageDocument(
                    url=url,
                    html="",
                    title="",
                    fetch_status=FetchStatus.TIMEOUT,
                    error_message=str(exc),
                )

            except TooManyRedirects as exc:
                self._log_slow_fetch(url, started_at)
                self._record_request(
                    started_at,
                    FetchStatus.NETWORK_ERROR,
                    redirect_limit=True,
                )
                logger.warning(
                    "Redirect limit exceeded (%d) for %s: %s",
                    self.max_redirects,
                    url,
                    exc,
                )
                return HomepageDocument(
                    url=url,
                    html="",
                    title="",
                    fetch_status=FetchStatus.NETWORK_ERROR,
                    error_message=(
                        f"Exceeded redirect limit ({self.max_redirects}): {exc}"
                    ),
                )

            except requests.RequestException as exc:
                self._log_slow_fetch(url, started_at)
                self._record_request(started_at, FetchStatus.NETWORK_ERROR)
                last_error = str(exc)
                if attempt < self.retries:
                    time.sleep(self.backoff * (attempt + 1))
                    continue
                return HomepageDocument(
                    url=url,
                    html="",
                    title="",
                    fetch_status=FetchStatus.NETWORK_ERROR,
                    error_message=last_error,
                )

        self._record_request(started_at, FetchStatus.NETWORK_ERROR)
        return HomepageDocument(
            url=url,
            html="",
            title="",
            fetch_status=FetchStatus.NETWORK_ERROR,
            error_message=last_error or "Unknown fetch error",
        )

    def _log_slow_fetch(self, url: str, started_at: float) -> None:
        elapsed = time.monotonic() - started_at
        if elapsed >= self.SLOW_FETCH_THRESHOLD_SECONDS:
            logger.warning("Slow fetch (%.1fs) %s", elapsed, url)

    def _record_request(
        self,
        started_at: float,
        status: FetchStatus,
        *,
        redirect_limit: bool = False,
    ) -> None:
        elapsed = time.monotonic() - started_at
        self._stats.record(elapsed, status, redirect_limit=redirect_limit)

    @staticmethod
    def _extract_title(html: str) -> str:
        lower = html.lower()
        start = lower.find("<title")
        if start == -1:
            return ""
        start = lower.find(">", start)
        if start == -1:
            return ""
        end = lower.find("</title>", start)
        if end == -1:
            return ""
        return html[start + 1 : end].strip()

    def _cache_key(self, url: str) -> str:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        return digest

    def _cache_path(self, url: str) -> Path:
        assert self.cache_dir is not None
        return self.cache_dir / f"{self._cache_key(url)}.html"

    def _read_cache(self, url: str) -> HomepageDocument | None:
        assert self.cache_dir is not None
        path = self._cache_path(url)
        if not path.exists():
            return None
        html = path.read_text(encoding="utf-8", errors="replace")
        meta_path = path.with_suffix(".meta")
        final_url = url
        status_code = 200
        if meta_path.exists():
            for line in meta_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("final_url="):
                    final_url = line.split("=", 1)[1]
                elif line.startswith("status_code="):
                    status_code = int(line.split("=", 1)[1])

        return HomepageDocument(
            url=url,
            html=html,
            title=self._extract_title(html),
            fetch_status=FetchStatus.SUCCESS,
            final_url=final_url,
            status_code=status_code,
        )

    def _write_cache(self, url: str, document: HomepageDocument) -> None:
        assert self.cache_dir is not None
        path = self._cache_path(url)
        path.write_text(document.html, encoding="utf-8")
        meta_path = path.with_suffix(".meta")
        meta_path.write_text(
            f"final_url={document.final_url or url}\n"
            f"status_code={document.status_code or 200}\n",
            encoding="utf-8",
        )
