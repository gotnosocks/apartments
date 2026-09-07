import time

from streeteasy_archive.store import ArchiveStore
from streeteasy_archive.crawler import approved_links, retry_after


def test_crash_recovery_and_atomic_discovery(tmp_path):
    s = ArchiveStore(tmp_path); g = s.new_generation("test")
    s.enqueue(g, [{"url": "https://streeteasy.com/building/a", "kind": "building"}])
    assert s.claim(g)["state"] == "pending"
    s.close()
    s = ArchiveStore(tmp_path); s.recover_inflight(g)
    assert s.claim(g)["url"].endswith("/building/a")
    s.record(g, "https://streeteasy.com/building/a", 200, {"ETag": "v1", "Cookie": "secret"}, b"<html/>", "text/html", {"extraction_version": 1}, discovered=[{"url": "https://streeteasy.com/rental/1", "kind": "listing"}])
    assert s.status(g)["pending"] == 1
    assert "Cookie" not in next(iter(s.observations(g)))["headers"]


def test_content_dedup_and_304_reuses_previous_generation(tmp_path):
    s = ArchiveStore(tmp_path); g1 = s.new_generation("one"); url = "https://streeteasy.com/building/a"
    s.enqueue(g1, [{"url": url, "kind": "building"}]); s.claim(g1)
    digest = s.record(g1, url, 200, {"ETag": "v1"}, b"body", "text/plain")
    assert s.body_path(digest).exists()
    g2 = s.new_generation("two"); s.enqueue(g2, [{"url": url, "kind": "building"}]); s.claim(g2)
    assert s.record(g2, url, 304, {}, b"", "text/plain") == digest
    assert s.latest_body(None, url) == digest


def test_cooldown_keeps_frontier_and_redirect_scope(tmp_path):
    s = ArchiveStore(tmp_path); g = s.new_generation("blocked"); url = "https://streeteasy.com/building/a"
    s.enqueue(g, [{"url": url, "kind": "building"}]); s.claim(g); s.cooldown(g, 120, "403")
    assert s.status(g)["pending"] == 1
    assert approved_links([{"url": "/login", "kind": "building"}, {"url": "/building/a", "kind": "building"}], url)[0]["url"].endswith("/building/a")
    assert retry_after({"Retry-After": "999999"}) == 999999.0
