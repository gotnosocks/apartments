
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


def test_imported_snapshot_keeps_original_collection_time(tmp_path):
    s = ArchiveStore(tmp_path)
    g = s.new_generation('import')
    s.record(g, 'https://streeteasy.com/rental/1', 200, {}, b'body',
             extracted={'extraction_version': 1}, fetched=1000)
    assert s.db.execute('SELECT fetched FROM observations').fetchone()[0] == 1000
    assert s.db.execute('SELECT observed FROM snapshots').fetchone()[0] == 1000


def test_status_distinguishes_current_from_cumulative_coverage_gaps(tmp_path):
    s = ArchiveStore(tmp_path)
    g = s.new_generation()
    url = 'https://streeteasy.com/rental/1'
    s.enqueue(g, [{'url': url, 'kind': 'listing'}])
    s.record_gap(g, url, 404, {}, 'HTTP 404 coverage gap', body=b'missing')
    assert s.status(g)['coverage_gaps'] == 1
    assert s.status(g)['current_coverage_gaps'] == 1
    s.enqueue(g, [{'url': url, 'kind': 'listing'}])
    s.claim(g)
    s.record(g, url, 200, {}, b'<html/>', 'text/html', {'title': 'recovered'})
    assert s.status(g)['coverage_gaps'] == 1
    assert s.status(g)['current_coverage_gaps'] == 0
    s.close()
    s.close()


def test_cooldown_keeps_frontier_and_redirect_scope(tmp_path):
    s = ArchiveStore(tmp_path); g = s.new_generation("blocked"); url = "https://streeteasy.com/building/a"
    s.enqueue(g, [{"url": url, "kind": "building"}]); s.claim(g); s.cooldown(g, 120, "403")
    assert s.status(g)["pending"] == 1
    assert approved_links([{"url": "/login", "kind": "building"}, {"url": "/building/a", "kind": "building"}], url)[0]["url"].endswith("/building/a")
    assert retry_after({"Retry-After": "999999"}) == 999999.0


def test_unavailable_inventory_gets_turn_before_growing_listing_queue(tmp_path):
    store = ArchiveStore(tmp_path)
    gen = store.new_generation()
    store.enqueue(gen, [
        {'url': 'https://streeteasy.com/rental/123', 'kind': 'listing'},
        {'url': 'https://streeteasy.com/building/example?archive_view=unavailable-rentals', 'kind': 'inventory'},
        {'url': 'https://streeteasy.com/building/example', 'kind': 'building'},
    ])
    assert store.claim(gen, prefer_inventory=True)['kind'] == 'inventory'
    assert store.claim(gen, prefer_inventory=True)['kind'] == 'listing'
    store.close()
