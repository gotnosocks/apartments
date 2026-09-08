"""Scrapy download handler backed by the Oxylabs Realtime Web Scraper API."""
from __future__ import annotations

import os
import asyncio
from pathlib import Path

import requests
from dotenv import load_dotenv
from scrapy.http import HtmlResponse

from .extract import canonical_url

API_URL = "https://realtime.oxylabs.io/v1/queries"
_PRIVATE_KEYS = {"authorization", "proxy-authorization", "cookie", "cookies", "set-cookie", "www-authenticate", "x-api-key", "_request", "session_info"}
MAX_BODY = 32 * 1024 * 1024


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

    async def download_request(self, request, spider=None):
        url = _target_url(request.url)
        username, password = _credentials()
        payload = {"source": "universal", "url": url, "render": "html"}
        try:
            result = await asyncio.to_thread(requests.post, API_URL, json=payload,
                                              auth=(username, password), timeout=180,
                                              allow_redirects=False)
            result.raise_for_status()
            envelope = result.json()
        except requests.RequestException as exc:
            raise RuntimeError("Oxylabs request failed") from None
        except (ValueError, TypeError) as exc:
            raise RuntimeError("Oxylabs returned invalid JSON") from None

        results = envelope.get("results") if isinstance(envelope, dict) else None
        if not isinstance(results, list) or len(results) != 1 or not isinstance(results[0], dict):
            raise RuntimeError("Oxylabs response did not contain one result")
        item = results[0]
        status = item.get("status_code", item.get("status"))
        content = item.get("content")
        if isinstance(status, bool) or not isinstance(status, int) or not 100 <= status <= 599 or not isinstance(content, (str, bytes)):
            raise RuntimeError("Oxylabs result is missing status or content")
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
        response.meta["archive_provider"] = {"results": _safe_envelope(results)}
        response.meta["archive_response_headers"] = _safe_envelope(headers)
        return response

    async def close(self):
        return None
