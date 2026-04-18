"""URL validation utility with retry logic."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from dataset_extractor.logging_utils import get_logger, log_event

logger = get_logger(__name__, log_file="url_validation.jsonl")


class URLStatus(str, Enum):
    VALID = "valid"
    INVALID = "invalid"
    TIMEOUT = "timeout"
    NOT_FOUND = "not_found"
    UNSUPPORTED = "unsupported"


@dataclass
class URLCheckResult:
    url: str
    status: URLStatus
    http_code: Optional[int] = None
    error: Optional[str] = None
    content_type: Optional[str] = None


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=10))
async def _check_url_once(url: str, timeout: float = 15.0) -> URLCheckResult:
    """Attempt a HEAD request (falling back to GET) to verify the URL."""
    async with httpx.AsyncClient(
        follow_redirects=True, timeout=timeout, verify=False  # noqa: S501
    ) as client:
        try:
            resp = await client.head(url)
        except httpx.HTTPError:
            resp = await client.get(url)  # some servers reject HEAD

        content_type = resp.headers.get("content-type", "")
        if resp.status_code < 400:
            return URLCheckResult(
                url=url,
                status=URLStatus.VALID,
                http_code=resp.status_code,
                content_type=content_type,
            )
        if resp.status_code == 404:
            return URLCheckResult(
                url=url,
                status=URLStatus.NOT_FOUND,
                http_code=resp.status_code,
            )
        return URLCheckResult(
            url=url,
            status=URLStatus.INVALID,
            http_code=resp.status_code,
        )


async def check_url(url: str) -> URLCheckResult:
    """Validate a URL, returning a structured result."""
    try:
        result = await _check_url_once(url)
    except httpx.TimeoutException:
        result = URLCheckResult(url=url, status=URLStatus.TIMEOUT, error="Request timed out")
    except Exception as exc:  # noqa: BLE001
        result = URLCheckResult(url=url, status=URLStatus.INVALID, error=str(exc))

    log_event(logger, "url_check", url=url, status=result.status.value, http_code=result.http_code)
    return result


async def check_urls(urls: list[str]) -> list[URLCheckResult]:
    """Validate multiple URLs concurrently."""
    return await asyncio.gather(*(check_url(u) for u in urls))


def check_url_sync(url: str) -> URLCheckResult:
    """Synchronous convenience wrapper."""
    return asyncio.run(check_url(url))
