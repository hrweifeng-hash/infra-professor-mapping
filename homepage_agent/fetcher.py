"""HTTP fetcher for professor homepages — no AI, reusable by future PRs."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

from homepage_agent.models import FetchStatus, HomepageDocument


class HomepageFetcher:
    """
    Fetch a homepage URL with timeout, retry, redirect handling, and optional cache.

    Designed as a standalone stage so future PRs can reuse the same fetch layer.
    """

    DEFAULT_TIMEOUT = 15
    DEFAULT_RETRIES = 2
    DEFAULT_BACKOFF = 1.0

    USER_AGENT = (
        "InfraProfessorMapping/1.0 (+https://github.com/infra-professor-mapping; "
        "homepage-intelligence-agent)"
    )

    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        retries: int = DEFAULT_RETRIES,
        backoff: float = DEFAULT_BACKOFF,
        cache_dir: str | Path | None = "data/cache/homepages",
        use_cache: bool = True,
    ):
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self.use_cache = use_cache
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir and self.use_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

        self._session = requests.Session()
        self._session.headers.update({"User-Agent": self.USER_AGENT})

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
            try:
                response = self._session.get(
                    url,
                    timeout=self.timeout,
                    allow_redirects=True,
                )
                final_url = response.url
                status_code = response.status_code

                if status_code >= 400:
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
                return HomepageDocument(
                    url=url,
                    html=html,
                    title=title,
                    fetch_status=FetchStatus.SUCCESS,
                    final_url=final_url,
                    status_code=status_code,
                )

            except requests.Timeout as exc:
                last_error = str(exc)
                if attempt < self.retries:
                    time.sleep(self.backoff * (attempt + 1))
                    continue
                return HomepageDocument(
                    url=url,
                    html="",
                    title="",
                    fetch_status=FetchStatus.TIMEOUT,
                    error_message=last_error,
                )

            except requests.RequestException as exc:
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

        return HomepageDocument(
            url=url,
            html="",
            title="",
            fetch_status=FetchStatus.NETWORK_ERROR,
            error_message=last_error or "Unknown fetch error",
        )

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
