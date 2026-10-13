import json

import pytest
from scrapy.crawler import Crawler
from scrapy.http import HtmlResponse
from scrapy.settings import Settings
from twisted.python.failure import Failure

from streeteasy_archive import graphql_inventory as gi
from streeteasy_archive.collection_policy import inventory_unit_probes
from streeteasy_archive.oxylabs import RetryableOxylabsError

ROOT = "https://streeteasy.com/building/hanover-house"
VIEW = ROOT + "?archive_view=unavailable-rentals"
OTHER = (
    "https://streeteasy.com/building/brooklyn-point?archive_view=unavailable-rentals"
)


def doc(history, expected=(2,)):
    return {"source": gi.SOURCE, "history": history, "expected_counts": list(expected)}


def digest(ad, unit):
    return {"id": ad, "displayUnit": unit, "price": 4870, "bedroomCount": 1}


def test_history_gives_modal_shaped_inventory_and_unit_probes():
    inv = gi.inventory_from_history(
        doc(
            [
                digest("5051007", "#20I"),
                digest("5051008", "3B"),
                digest("5051007", "#20I"),
            ]
        ),
        VIEW,
    )
    assert inv["count"] == 2
    assert [x["url"] for x in inv["links"]] == [
        "https://streeteasy.com/rental/5051007",
        "https://streeteasy.com/rental/5051008",
    ]
    assert inv["records"][0]["digest"]["price"] == 4870
    assert inventory_unit_probes({"inventory": inv}, VIEW) == {
        ROOT + "/20i": "https://streeteasy.com/rental/5051007",
        ROOT + "/3b": "https://streeteasy.com/rental/5051008",
    }


def test_incomplete_history_is_rejected():
    with pytest.raises(ValueError, match="empty"):
        gi.inventory_from_history(doc([]), VIEW)
    with pytest.raises(ValueError, match="smaller"):
        gi.inventory_from_history(doc([digest("1", "#1")], expected=(1, 5)), VIEW)
    with pytest.raises(ValueError, match="advertisement ID"):
        gi.inventory_from_history(doc([{"displayUnit": "#1"}]), VIEW)
    with pytest.raises(ValueError, match="rental inventories"):
        gi.inventory_from_history(
            doc([digest("1", "#1")]), ROOT + "?archive_view=unavailable-sales"
        )


def test_query_fits_oxylabs_url_limit_and_sends_preflight_header():
    batch = [
        {"url": VIEW, "building_id": str(6468149 + i), "expected_counts": []}
        for i in range(24)
    ]
    url = gi.query_url(batch)
    assert gi.is_graphql_url(url) and len(url) < gi.MAX_URL
    assert "h23%3A+rentalsHistoryByBuildingId" in url
    payload = gi.build_payload(url)
    assert "render" not in payload
    headers = next(c["value"] for c in payload["context"] if c["key"] == "headers")
    assert headers == {"apollo-require-preflight": "true"}


def spider(tmp_path, monkeypatch, batch=24):
    monkeypatch.setattr(
        gi,
        "building_info",
        lambda store, url: {
            "url": url,
            "building_id": str(len(url)),
            "expected_counts": [1],
        },
    )
    s = gi.GraphQLInventorySpider.from_crawler(
        Crawler(gi.GraphQLInventorySpider, Settings()),
        data_dir=tmp_path,
        transport="oxylabs",
        concurrency=1,
        include_unavailable=True,
        graphql_batch=batch,
    )
    s.store.enqueue(
        s.generation,
        [{"url": VIEW, "kind": "inventory"}, {"url": OTHER, "kind": "inventory"}],
    )
    return s


def state(s, url):
    return s.store.db.execute(
        "SELECT state FROM frontier WHERE generation=? AND url=?", (s.generation, url)
    ).fetchone()[0]


def test_batch_records_each_building_and_falls_back_on_missing_history(
    tmp_path, monkeypatch
):
    s = spider(tmp_path, monkeypatch)
    request = list(s.start_requests())[0]
    batch = request.meta["archive_graphql_batch"]
    assert gi.is_graphql_url(request.url) and [b["url"] for b in batch] == [VIEW, OTHER]
    body = json.dumps(
        {
            "data": {"h0": [digest("5051007", "#20I")], "h1": None},
            "errors": [{"message": "boom", "path": ["h1"]}],
        }
    ).encode()
    response = HtmlResponse(url=request.url, body=body, request=request)
    follow = list(s.parse(response))
    assert state(s, VIEW) == "done"
    saved = s.store.db.execute(
        "SELECT content_type FROM observations WHERE url=? ORDER BY id DESC LIMIT 1",
        (VIEW,),
    ).fetchone()
    assert saved["content_type"] == "application/json"
    assert s.store.db.execute(
        "SELECT 1 FROM frontier WHERE url='https://streeteasy.com/rental/5051007'"
    ).fetchone()
    assert gi.fallen_back(s.store, s.generation, OTHER)
    # The fallen-back building went back to the queue and its next claim, made at once
    # for the freed slot, takes the browser path.
    assert state(s, OTHER) == "inflight"
    assert [r.url for r in follow] == [OTHER]
    assert "archive_graphql_batch" not in follow[0].meta
    s.store.close()


def test_provider_failure_keeps_buildings_queued_for_retry(tmp_path, monkeypatch):
    s = spider(tmp_path, monkeypatch)
    request = list(s.start_requests())[0]
    failure = Failure(RetryableOxylabsError("Oxylabs request failed (HTTP 429)"))
    failure.request = request
    list(s.errback(failure))
    assert state(s, VIEW) == "pending" and state(s, OTHER) == "pending"
    assert not gi.fallen_back(s.store, s.generation, VIEW)
    assert not s.stopped
    s.store.close()


def test_repeated_refusals_switch_the_run_to_the_browser(tmp_path, monkeypatch):
    s = spider(tmp_path, monkeypatch, batch=1)
    for url in (
        "https://streeteasy.com/building/b%d?archive_view=unavailable-rentals" % i
        for i in range(3)
    ):
        s.store.enqueue(s.generation, [{"url": url, "kind": "inventory"}])
    for _ in range(gi.MAX_FAILED_BATCHES):
        request = s._request()
        assert "archive_graphql_batch" in request.meta
        list(
            s.parse(
                HtmlResponse(url=request.url, status=400, body=b"{}", request=request)
            )
        )
        s.outstanding = 0
    assert not s.graphql_active
    request = s._request()
    assert request is not None and "archive_graphql_batch" not in request.meta
    s.store.close()


def test_streeteasy_rate_limit_stops_the_crawl(tmp_path, monkeypatch):
    s = spider(tmp_path, monkeypatch)
    request = list(s.start_requests())[0]
    list(s.parse(HtmlResponse(url=request.url, status=429, body=b"", request=request)))
    assert s.stopped
    assert state(s, VIEW) == "pending" and not gi.fallen_back(
        s.store, s.generation, VIEW
    )
    s.store.close()


def attempts(s, url):
    return s.store.db.execute(
        "SELECT attempts FROM frontier WHERE generation=? AND url=?",
        (s.generation, url),
    ).fetchone()[0]


@pytest.mark.parametrize(
    "status,body",
    [(403, b""), (200, b"<title>Access to this page has been denied</title>")],
)
def test_block_or_challenge_stops_the_crawl(tmp_path, monkeypatch, status, body):
    s = spider(tmp_path, monkeypatch)
    request = list(s.start_requests())[0]
    list(
        s.parse(
            HtmlResponse(url=request.url, status=status, body=body, request=request)
        )
    )
    assert s.stopped and not gi.fallen_back(s.store, s.generation, VIEW)
    s.store.close()


def test_fallback_keeps_the_browser_paths_retries(tmp_path, monkeypatch):
    s = spider(tmp_path, monkeypatch, batch=1)
    request = s._request()
    gi.fall_back(s.store, s.generation, VIEW, "test")
    assert state(s, VIEW) == "pending" and attempts(s, VIEW) == 0
    s.store.close()


def test_unreadable_building_page_falls_back(tmp_path, monkeypatch):
    s = spider(tmp_path, monkeypatch)

    def broken(store, url):
        raise OSError("body missing")

    monkeypatch.setattr(gi, "building_info", broken)
    request = s._request()
    assert "archive_graphql_batch" not in request.meta
    assert gi.fallen_back(s.store, s.generation, VIEW)
    assert s.outstanding == 1 and s.sent == 1
    s.store.close()


def test_annotate_failure_finishes_the_batch(tmp_path, monkeypatch):
    import streeteasy_archive.collection_policy as policy

    s = spider(tmp_path, monkeypatch)
    request = list(s.start_requests())[0]
    real = policy.annotate

    def flaky(store, generation, data, body, url, persist=True):
        if persist and url == VIEW:
            raise RuntimeError("boom")
        return real(store, generation, data, body, url, persist=persist)

    monkeypatch.setattr(policy, "annotate", flaky)
    body = json.dumps(
        {"data": {"h0": [digest("1", "#1")], "h1": [digest("2", "#2")]}}
    ).encode()
    list(s.parse(HtmlResponse(url=request.url, body=body, request=request)))
    assert state(s, VIEW) == "done" and state(s, OTHER) == "done"
    s.store.close()
