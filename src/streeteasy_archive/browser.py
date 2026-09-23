#!/usr/bin/env python3
"""Stock Firefox transport capturing decoded HTTP entities through Selenium BiDi."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from pathlib import Path
from scrapy.http import HtmlResponse
from scrapy.core.downloader.handlers.http11 import HTTP11DownloadHandler
from selenium.common.exceptions import WebDriverException
import base64
import json
import queue
import threading
from collections import Counter
from dataclasses import asdict, is_dataclass
from urllib.parse import urlsplit

from selenium import webdriver
from selenium.webdriver.common.bidi.network import DataType
from selenium.webdriver.firefox.options import Options


def _plain(value):
    if is_dataclass(value):
        return {k: _plain(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def _request_id(event):
    raw = _plain(event)
    return (raw.get("request") or {}).get("request") or raw.get("request")


def _response(event):
    raw = _plain(event)
    return raw.get("response") or {}


def _body_bytes(result):
    """Decode Selenium's getData result without treating text as entity bytes."""
    raw = _plain(result)
    value = raw.get("bytes") if isinstance(raw, dict) else raw
    if isinstance(value, dict):
        if value.get("type") == "base64":
            return base64.b64decode(value["value"])
        if value.get("type") == "string":
            # String data is browser-decoded text, not a wire-byte guarantee.
            return value["value"].encode("utf-8")
    raise TypeError(f"unrecognized getData result: {type(result)!r}")


def _header_value(value):
    if isinstance(value, dict) and value.get("type") == "string":
        return value.get("value", "")
    return value


class RequestPolicy:
    """Resolve only our blocked events; preserve failures outside callback threads."""

    def __init__(self, network, main_url, conditional_headers=None):
        self.network = network
        self.main_url = main_url
        self.headers = conditional_headers or {}
        self.intercept = None
        self.closed = threading.Event()
        self.errors = queue.Queue()
        self.warnings = Counter()
        self.lock = threading.Lock()

    def __call__(self, event):
        if self.closed.is_set() or not event.get("isBlocked"):
            return
        if self.intercept not in event.get("intercepts", []):
            return
        request = event.get("request", {})
        url = request.get("url", "")
        if url.startswith("data:"):
            return
        request_id = request.get("request")
        resource = (
            request.get("destination") or request.get("initiatorType") or ""
        ).lower()
        document = resource in ("document", "iframe")
        main = url == self.main_url and document
        try:
            if (
                request.get("method") != "GET"
                or (document and not main)
                or resource in ("image", "media", "font")
            ):
                self.network.fail_request(request=request_id)
            else:
                headers = None
                if main and self.headers:
                    names = {k.lower() for k in self.headers}
                    headers = [
                        h
                        for h in request.get("headers", [])
                        if h["name"].lower() not in names
                    ]
                    headers += [
                        {"name": k, "value": {"type": "string", "value": v}}
                        for k, v in self.headers.items()
                    ]
                self.network.continue_request(request=request_id, headers=headers)
        except Exception as exc:
            if self.closed.is_set():
                return  # Firefox shutdown cancelled outstanding subresources.
            text = str(exc).lower()
            stale = isinstance(exc, WebDriverException) and "no such request" in text
            if stale and not main:
                # Firefox already cancelled it. No retry or further command is useful.
                with self.lock:
                    self.warnings["cancelled_subresource"] += 1
            else:
                # Timeouts and unexpected failures must be visible and pause the
                # crawler after saving any available main-document response.
                self.errors.put(
                    f"{resource or 'unknown'} interception: {type(exc).__name__}: {exc}"
                )

    def diagnostics(self):
        errors = []
        while not self.errors.empty():
            errors.append(self.errors.get_nowait())
        with self.lock:
            return {"warnings": dict(self.warnings), "errors": errors}


def capture_main_document(
    url: str, conditional_headers: dict[str, str] | None = None, binary=None
) -> dict:
    """Capture one public main-document response, retaining its rendered DOM separately."""
    parsed = urlsplit(url)
    if parsed.hostname not in {
        "127.0.0.1",
        "localhost",
        "::1",
        "streeteasy.com",
        "www.streeteasy.com",
    }:
        raise ValueError("browser target outside archive scope")

    options = Options()
    if binary:
        options.binary_location = binary
    elif Path("/Applications/Firefox.app/Contents/MacOS/firefox").exists():
        options.binary_location = "/Applications/Firefox.app/Contents/MacOS/firefox"
    options.enable_bidi = True
    options.add_argument("--headless")
    options.accept_insecure_certs = False

    driver = webdriver.Firefox(options=options)
    driver.set_page_load_timeout(45)
    collector = None
    response_events: queue.Queue = queue.Queue()
    request_handler = None
    policy = None
    response_handler = None
    try:
        network = driver.network
        network._conn.response_wait_timeout = 15
        # Selenium 4.48's generated legacy network binding drops the request
        # member when deserializing responseCompleted.  Keep the raw event so
        # getData can receive the request id.  Newer bindings can omit this.
        response_event_wrapper = network._event_manager._event_wrappers.get(
            "network.responseCompleted"
        )
        if response_event_wrapper is not None:
            response_event_wrapper._python_class = dict
        collector_result = network.add_data_collector(
            data_types=[DataType.RESPONSE],
            max_encoded_data_size=64 * 1024 * 1024,
        )
        collector = _plain(collector_result).get("collector", collector_result)

        main_url = url
        policy = RequestPolicy(network, main_url, conditional_headers)

        def response_complete(event):
            response = _response(event)
            if response.get("url") == main_url:
                response_events.put((event, response))

        request_handler = network.add_event_handler("before_request", policy)
        policy.intercept = network.add_intercept(phases=["beforeRequestSent"])[
            "intercept"
        ]
        response_handler = network.add_event_handler(
            "response_completed", response_complete
        )
        navigation_error = None
        try:
            driver.get(url)
        except WebDriverException as exc:
            navigation_error = exc
        if navigation_error and response_events.empty():
            raise navigation_error

        event, response = response_events.get(timeout=10)
        request_id = _request_id(event)
        if not request_id:
            raise RuntimeError(
                "response event had no request id: "
                + json.dumps(_plain(event), default=str)[:2000]
            )
        # Firefox does not complete getData for a redirect whose next hop is
        # blocked. Archive its status/headers and let Scrapy enqueue the hop.
        redirect = (
            300 <= response.get("status", 0) < 400 and response.get("status") != 304
        )
        result = None
        if redirect:
            body = b""
        else:
            result = network.get_data(
                data_type=DataType.RESPONSE,
                collector=collector,
                request=request_id,
                disown=True,
            )
            body = _body_bytes(result)
        if len(body) > 32 * 1024 * 1024:
            raise ValueError("browser response exceeds 32 MiB")
        return {
            "interception": policy.diagnostics(),
            "response_data": result,
            "body_captured": not redirect,
            "rendered_html": driver.page_source
            if response.get("status") == 200 and not navigation_error
            else None,
            "browser_version": driver.capabilities.get("browserVersion"),
            "url": response.get("url"),
            "status": response.get("status"),
            "headers": {
                h.get("name"): _header_value(h.get("value"))
                for h in response.get("headers", [])
            },
            "body": body,
            "body_sha256": __import__("hashlib").sha256(body).hexdigest(),
        }
    finally:
        if policy is not None:
            policy.closed.set()
        with suppress(Exception):
            if request_handler is not None:
                network.remove_event_handler("before_request", request_handler)
        with suppress(Exception):
            driver.quit()


class FirefoxDownloadHandler(HTTP11DownloadHandler):
    def __init__(self, crawler):
        super().__init__(crawler)
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.binary = crawler.settings.get("ARCHIVE_FIREFOX_BINARY")

    async def download_request(self, request):
        if request.meta.get("archive_kind") == "sitemap":
            return await super().download_request(request)
        headers = {
            k.decode(): v[0].decode()
            for k, v in request.headers.items()
            if k.lower() in (b"if-none-match", b"if-modified-since")
        }
        capture = await asyncio.get_running_loop().run_in_executor(
            self.executor, capture_main_document, request.url, headers, self.binary
        )
        request.meta["archive_browser"] = {
            "transport": "selenium-firefox",
            "browser_version": capture["browser_version"],
            "rendered_html": capture["rendered_html"],
            "body_representation": "BiDi base64 bytes or browser-decoded text encoded as UTF-8",
            "response_data": capture["response_data"],
            "interception": capture["interception"],
        }
        request.meta["archive_response_headers"] = capture["headers"]
        request.meta["archive_body_captured"] = capture["body_captured"]
        headers = {
            k: v
            for k, v in capture["headers"].items()
            if k.lower() not in ("content-encoding", "content-length")
        }
        return HtmlResponse(
            request.url,
            status=capture["status"],
            headers=headers,
            body=capture["body"],
            request=request,
        )

    async def close(self):
        await super().close()
        self.executor.shutdown(wait=True)
