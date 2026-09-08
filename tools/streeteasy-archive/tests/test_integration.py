"""Offline end-to-end tests for the Scrapy adapter and durable frontier."""

from __future__ import annotations

import fcntl
from pathlib import Path

import pytest
from scrapy.crawler import CrawlerProcess
from scrapy.http import Response
from streeteasy_archive.crawler import ArchiveSpider
from streeteasy_archive.store import ArchiveStore


class FixtureDownloadHandler:
    """A Scrapy download handler backed entirely by an in-memory fixture."""

    lazy = True
    responses: dict[str, tuple[int, dict[str, str], bytes]] = {}
    requests: list[tuple[str, dict[str, str]]] = []

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings)

    def __init__(self, settings):
        self.settings = settings

    async def download_request(self, request, spider=None):
        url = request.url
        headers = {key.lower(): value for key, value in request.headers.to_unicode_dict().items()}
        type(self).requests.append((url, headers))
        status, response_headers, body = type(self).responses[url]
        return Response(url=url, status=status, headers=response_headers, body=body, request=request)

    async def close(self):
        return None


class FixtureArchiveSpider(ArchiveSpider):
    custom_settings = {
        **ArchiveSpider.custom_settings,
        "DOWNLOAD_DELAY": 0,
        "RANDOMIZE_DOWNLOAD_DELAY": False,
        "AUTOTHROTTLE_ENABLED": False,
    }


def _run_spiders(*specs: tuple[Path, int]):
    handler = f"{__name__}.FixtureDownloadHandler"
    process = CrawlerProcess(
        settings={
            "LOG_ENABLED": False,
            "DOWNLOAD_HANDLERS": {"https": handler},
            "CONCURRENT_REQUESTS": 1,
            "DOWNLOAD_DELAY": 0,
            "AUTOTHROTTLE_ENABLED": False,
            "RETRY_ENABLED": False,
            "REDIRECT_ENABLED": False,
            "TELNETCONSOLE_ENABLED": False,
        }
    )
    crawlers = []
    for data_dir, generation in specs:
        crawler = process.create_crawler(FixtureArchiveSpider)
        process.crawl(crawler, data_dir=str(data_dir), generation=generation)
        crawlers.append(crawler)
    process.start()
    return crawlers


@pytest.fixture
def fixture_handler():
    FixtureDownloadHandler.responses = {}
    FixtureDownloadHandler.requests = []
    yield FixtureDownloadHandler
    FixtureDownloadHandler.responses = {}
    FixtureDownloadHandler.requests = []


def test_scrapy_lifecycle_queue_304_block_and_external_redirect(tmp_path, fixture_handler):
    """A complete offline crawl advances the queue and preserves durable gaps."""
    store = ArchiveStore(tmp_path)
    generation = store.new_generation("integration")
    root = "https://streeteasy.com/buildings/fixture"
    cached = "https://streeteasy.com/building/cached"
    blocked = "https://streeteasy.com/building/blocked"
    redirected = "https://streeteasy.com/building/redirected"
    discovered = "https://streeteasy.com/building/discovered"
    external = "https://example.test/should-not-follow"

    store.enqueue(
        generation,
        [
            {"url": root, "kind": "directory"},
            {"url": cached, "kind": "building"},
            {"url": blocked, "kind": "building"},
        ],
    )
    store.enqueue(generation, [{"url": cached, "kind": "building"}])
    store.record(generation, cached, 200, {"ETag": "old"}, b"<html><title>cached body</title></html>", "text/html")
    # Put the cached URL back in the pending frontier with validators, as an
    # update run would do after loading known URLs from a prior generation.
    store.db.execute(
        "UPDATE frontier SET state='pending', etag='old' WHERE generation=? AND url=?",
        (generation, cached),
    )
    store.db.commit()

    fixture_handler.responses.update(
        {
            root: (200, {"Content-Type": "text/html"}, f'<a href="{discovered}">new</a>'.encode()),
            cached: (304, {"ETag": "old"}, b""),
            blocked: (403, {"Retry-After": "600"}, b"access denied"),
            redirected: (302, {"Location": external}, b""),
            discovered: (200, {"Content-Type": "text/html"}, b"<title>new</title>"),
        }
    )

    redirect_dir = tmp_path / "redirect"
    redirect_store = ArchiveStore(redirect_dir)
    redirect_generation = redirect_store.new_generation("redirect")
    redirect_store.enqueue(redirect_generation, [{"url": redirected, "kind": "building"}])
    redirect_store.close()
    fixture_handler.responses[redirected] = (302, {"Location": external}, b"")

    restart_dir = tmp_path / "restart"
    restart_store = ArchiveStore(restart_dir)
    restart_generation = restart_store.new_generation("restart")
    restart_url = "https://streeteasy.com/building/restart"
    restart_store.enqueue(restart_generation, [{"url": restart_url, "kind": "building"}])
    assert restart_store.claim(restart_generation)["url"] == restart_url
    restart_store.close()
    restart_store = ArchiveStore(restart_dir)
    restart_store.recover_inflight(restart_generation)
    fixture_handler.responses[restart_url] = (200, {"Content-Type": "text/html"}, b"<title>restart</title>")

    crawlers = _run_spiders(
        (tmp_path, generation),
        (redirect_dir, redirect_generation),
        (restart_dir, restart_generation),
        (restart_dir, restart_generation),
    )

    urls = [url for url, _ in fixture_handler.requests]
    assert urls.count(cached) == 1
    assert external not in urls
    assert urls.count(blocked) == 1, "403 must close the crawl instead of retrying immediately"
    assert urls.count(restart_url) == 1
    assert crawlers[1].stats.get_value("spider_exceptions/count", 0) == 0
    assert store.get_body(store.latest_body(None, cached)) == b"<html><title>cached body</title></html>"
    assert store.status(generation)["pending"] >= 1
    assert store.status(generation)["cooldown"] is not None
    redirect_rows = [row for row in ArchiveStore(redirect_dir).observations(redirect_generation) if row["url"] == redirected]
    assert len(redirect_rows) == 1 and "coverage gap" in redirect_rows[0]["error"]


def test_incremental_enqueue_deduplicates_known_completed_url(tmp_path):
    store = ArchiveStore(tmp_path)
    generation = store.new_generation("incremental")
    url = "https://streeteasy.com/building/known"
    store.enqueue(generation, [{"url": url, "kind": "building"}])
    store.claim(generation)
    store.record(generation, url, 200, {}, b"known", "text/plain")
    store.enqueue(generation, [{"url": url, "kind": "building", "lastmod": "2026-09-07"}])

    row = store.db.execute("SELECT state, attempts, lastmod FROM frontier WHERE generation=? AND url=?", (generation, url)).fetchone()
    assert tuple(row) == ("done", 1, "2026-09-07")


def test_crawler_lock_rejects_second_process_lock(tmp_path):
    lock_path = tmp_path / "crawler.lock"
    first = lock_path.open("w")
    second = lock_path.open("w")
    try:
        fcntl.flock(first, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(OSError):
            fcntl.flock(second, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        first.close()
        second.close()
