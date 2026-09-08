"""Scrapy download handler backed by the Oxylabs Realtime Web Scraper API."""
from __future__ import annotations

import os
import asyncio
import time
import email.utils
from pathlib import Path

import requests
from dotenv import load_dotenv
from scrapy.http import HtmlResponse

from .extract import canonical_url, is_unavailable_url

API_URL = "https://realtime.oxylabs.io/v1/queries"
_PRIVATE_KEYS = {"authorization", "proxy-authorization", "cookie", "cookies", "set-cookie", "www-authenticate", "x-api-key", "_request", "session_info"}
MAX_BODY = 32 * 1024 * 1024


class RetryableOxylabsError(RuntimeError):
    """A provider-side job failure that is safe to retry for the same URL."""


def _result_item(envelope):
    results = envelope.get("results") if isinstance(envelope, dict) else None
    if not isinstance(results, list) or len(results) != 1 or not isinstance(results[0], dict):
        raise RetryableOxylabsError("Oxylabs response did not contain one result")
    item = results[0]
    status = item.get("status_code", item.get("status"))
    content = item.get("content")
    if (isinstance(status, bool) or not isinstance(status, int)
            or not 100 <= status <= 599 or not isinstance(content, (str, bytes))):
        raise RetryableOxylabsError("Oxylabs result is missing status or content")
    return results, item, status, content


def _credentials() -> tuple[str, str]:
    # Loading is deliberately limited to the project .env and the process
    # environment. Values are never included in errors or response metadata.
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False, interpolate=False)
    username = os.getenv("OXYLABS_USERNAME") or os.getenv("OXYLABS_USER")
    password = os.getenv("OXYLABS_PASSWORD")
    if not username or not password:
        raise RuntimeError("Oxylabs credentials are not configured")
    return username, password


def _target_url(url: str) -> str:
    canonical = canonical_url(url)
    if not canonical or canonical != url:
        raise ValueError("Oxylabs transport requires a canonical StreetEasy URL")
    return canonical


def _safe_envelope(value):
    """Keep provider evidence while excluding request credentials/session data."""
    if isinstance(value, dict):
        return {key: _safe_envelope(item) for key, item in value.items()
                if str(key).lower() not in _PRIVATE_KEYS}
    if isinstance(value, list):
        return [_safe_envelope(item) for item in value]
    return value


class OxylabsDownloadHandler:
    """Fetch one canonical StreetEasy document through Oxylabs."""

    lazy = True

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings)

    def __init__(self, settings=None):
        self.settings = settings
        self._submission_interval = 1 / (settings.getfloat("ARCHIVE_API_RPS", 2) if settings else 2)
        self._submission_lock = asyncio.Lock()
        self._next_submission = 0.0

    async def _submission_slot(self):
        # Rate and concurrency are separate: five jobs can render simultaneously,
        # but the trial accepts only three rendered job submissions per second.
        async with self._submission_lock:
            await asyncio.sleep(max(0, self._next_submission - time.monotonic()))
            self._next_submission = time.monotonic() + self._submission_interval

    def _defer_submissions(self, value, attempt):
        delay = 2 ** (attempt + 1)
        try:
            delay = max(delay, float(value))
        except (TypeError, ValueError):
            try:
                delay = max(delay, email.utils.parsedate_to_datetime(value).timestamp() - time.time())
            except (TypeError, ValueError, OverflowError):
                pass
        # Longer waits belong in the durable crawl cooldown, not an API call.
        if delay > 60:
            return False
        self._next_submission = max(self._next_submission, time.monotonic() + delay)
        return True

    async def download_request(self, request, spider=None):
        url = _target_url(request.url)
        username, password = _credentials()
        payload = {"source": "universal", "url": url}
        if is_unavailable_url(url):
            category = 'For rent' if 'unavailable-rentals' in url else 'For sale'
            payload.update(url=url.split('?')[0], render='html', browser_instructions=[
                {'type': 'click', 'selector': {'type': 'xpath', 'value': '//button[contains(., "View unavailable units")]'}},
                {'type': 'wait', 'wait_time_s': 8},
                {'type': 'click', 'selector': {'type': 'xpath', 'value': f'//*[@role="dialog"]//button[normalize-space(.)="{category}"]'}},
                {'type': 'wait', 'wait_time_s': 2},
            ])
        elif self.settings and self.settings.getbool("ARCHIVE_OXYLABS_RENDER", False):
            payload["render"] = "html"
        result = None
        for attempt in range(3):
            result = None
            try:
                await self._submission_slot()
                result = await asyncio.to_thread(requests.post, API_URL, json=payload,
                                                  auth=(username, password), timeout=180,
                                                  allow_redirects=False)
                if result.status_code == 401 or result.status_code == 403:
                    result.raise_for_status()
                if result.status_code == 429 or result.status_code >= 500:
                    result.raise_for_status()
                envelope = result.json()
                results, item, status, content = _result_item(envelope)
                break
            except requests.RequestException as exc:
                api_status = exc.response.status_code if exc.response is not None else None
                if api_status in (401, 403):
                    raise RuntimeError(f"Oxylabs request failed (HTTP {api_status})") from None
                detail = f"HTTP {api_status}" if api_status is not None else type(exc).__name__
                failure = f"Oxylabs request failed ({detail})"
            except (ValueError, TypeError):
                failure = "Oxylabs returned invalid JSON"
            except RetryableOxylabsError as exc:
                failure = str(exc)
            retry_headers = getattr(result, "headers", {}) if result is not None else {}
            if attempt == 2 or not self._defer_submissions(
                    retry_headers.get("Retry-After"), attempt):
                raise RetryableOxylabsError(failure) from None
        else:  # pragma: no cover - loop always breaks or raises
            raise RetryableOxylabsError("Oxylabs job failed")

        body = content.encode("utf-8") if isinstance(content, str) else content
        if len(body) > MAX_BODY:
            raise RuntimeError("Oxylabs response exceeds 32 MiB")
        provider_response = item.get("_response")
        headers = item.get("headers") if isinstance(item.get("headers"), dict) else {}
        if not headers and isinstance(provider_response, dict) and isinstance(provider_response.get("headers"), dict):
            headers = provider_response["headers"]
        response_headers = {key: value for key, value in headers.items()
                            if str(key).lower() not in {"content-encoding", "content-length"}}
        response = HtmlResponse(url=url, status=status, headers=response_headers, body=body, request=request, encoding="utf-8")
        response.meta["archive_provider"] = {
            "target_url": payload['url'],
            "browser_instructions": payload.get('browser_instructions', []),
            "results": _safe_envelope(results),
            "api_headers": {k: v for k, v in getattr(result, 'headers', {}).items()
                            if k.lower().startswith('x-ratelimit-') or k.lower() == 'x-oxylabs-job-id'},
            "submission_attempts": attempt + 1,
        }
        response.meta["archive_response_headers"] = _safe_envelope(headers)
        return response

    async def close(self):
        return None
