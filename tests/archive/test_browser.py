"""Scope regression plus optional real Firefox loopback validation."""

import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from streeteasy_archive.store import ArchiveStore


def test_claim_building_boundary_and_resume(tmp_path):
    store = ArchiveStore(tmp_path)
    generation = store.new_generation()
    base = "https://streeteasy.com/building/example"
    store.enqueue(
        generation,
        [
            {"url": base + "-other/1", "kind": "listing"},
            {"url": base + "/1", "kind": "listing"},
            {"url": base, "kind": "building"},
        ],
    )
    first = store.claim(generation, url_prefix=base)
    assert first["url"] == base + "/1"
    store.record(generation, first["url"], 200, {}, b"detail")
    assert store.claim(generation, url_prefix=base)["url"] == base
    store.close()
    store = ArchiveStore(tmp_path)
    store.recover_inflight(generation)
    assert store.claim(generation, url_prefix=base)["url"] == base
    assert store.claim(generation, url_prefix=base) is None
    assert store.claim(generation)["url"] == base + "-other/1"
    store.close()


@pytest.mark.skipif(
    os.environ.get("ARCHIVE_TEST_FIREFOX") != "1",
    reason="opt-in installed Firefox loopback test",
)
def test_firefox_entity_conditional_and_redirect():
    from streeteasy_archive.browser import capture_main_document

    class Handler(BaseHTTPRequestHandler):
        seen = []
        body = '<html><body>entity\x00é€<img src="/image"></body></html>'.encode(
            "utf-8"
        )

        def do_GET(self):
            self.seen.append((self.path, self.headers.get("If-None-Match")))
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "/forbidden")
            elif self.headers.get("If-None-Match") == '"v1"':
                self.send_response(304)
            else:
                self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("ETag", '"v1"')
            self.end_headers()
            if self.path == "/page" and not self.headers.get("If-None-Match"):
                self.wfile.write(self.body)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        first = capture_main_document(base + "/page")
        assert first["status"] == 200
        assert first["body"] == Handler.body
        assert first["rendered_html"]
        second = capture_main_document(base + "/page", {"If-None-Match": '"v1"'})
        assert second["status"] == 304 and second["body"] == b""
        redirect = capture_main_document(base + "/redirect")
        assert redirect["status"] == 302
        assert all(path not in ("/forbidden", "/image") for path, _ in Handler.seen)
    finally:
        server.shutdown()
        server.server_close()


def test_interception_races_are_not_uncaught_and_real_failures_remain_visible():
    pytest.importorskip("selenium")
    from selenium.common.exceptions import WebDriverException
    from streeteasy_archive.browser import RequestPolicy

    class Network:
        def __init__(self):
            self.calls = []
            self.failure = None

        def fail_request(self, **kwargs):
            self.calls.append(("fail", kwargs))
            if self.failure:
                raise self.failure

        def continue_request(self, **kwargs):
            self.calls.append(("continue", kwargs))
            if self.failure:
                raise self.failure

    network = Network()
    policy = RequestPolicy(
        network, "https://streeteasy.com/building/test/1a", {"If-None-Match": '"v1"'}
    )
    policy.intercept = "ours"

    def event(url, resource="image", blocked=True, intercept="ours"):
        return {
            "isBlocked": blocked,
            "intercepts": [intercept],
            "request": {
                "request": "r1",
                "url": url,
                "destination": resource,
                "method": "GET",
                "headers": [
                    {
                        "name": "if-none-match",
                        "value": {"type": "string", "value": "old"},
                    }
                ],
            },
        }

    policy(event("https://example.com/photo", blocked=False))
    policy(event("https://example.com/photo", intercept="someone-else"))
    assert network.calls == []
    network.failure = WebDriverException("no such request: cancelled by browser")
    policy(event("https://example.com/photo"))
    assert policy.diagnostics() == {
        "warnings": {"cancelled_subresource": 1},
        "errors": [],
    }
    network.failure = WebDriverException("Timed out waiting for response")
    policy(event("https://example.com/photo"))
    assert len(policy.diagnostics()["errors"]) == 1
    network.failure = None
    policy(event(policy.main_url, "document"))
    assert network.calls[-1][1]["headers"] == [
        {"name": "If-None-Match", "value": {"type": "string", "value": '"v1"'}}
    ]
    network.failure = WebDriverException("no such request: main navigation disappeared")
    policy(event(policy.main_url, "document"))
    assert len(policy.diagnostics()["errors"]) == 1
    before = len(network.calls)
    policy.closed.set()
    policy(event("https://example.com/photo"))
    assert len(network.calls) == before


def test_interception_failure_saves_document_before_pausing(tmp_path):
    from scrapy import Request
    from scrapy.http import HtmlResponse
    from streeteasy_archive.crawler import ArchiveSpider

    store = ArchiveStore(tmp_path)
    gen = store.new_generation()
    url = "https://streeteasy.com/building/example/1a"
    store.enqueue(gen, [{"url": url, "kind": "listing"}])
    store.close()
    spider = ArchiveSpider(data_dir=tmp_path, generation=gen)
    request = Request(
        url,
        meta={
            "archive_url": url,
            "archive_browser": {
                "interception": {"errors": ["script interception timeout"]}
            },
        },
    )
    response = HtmlResponse(
        url, status=200, body=b"<title>Preserved</title>", request=request
    )
    assert list(spider.parse(response)) == []
    assert spider.store.latest_response(url)["status"] == 200
    assert spider.store.status(gen)["status"] == "paused"
    assert spider.stopped
    spider.store.close()
