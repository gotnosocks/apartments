import asyncio
import pytest
from scrapy.crawler import Crawler
from scrapy.http import HtmlResponse
from scrapy.settings import Settings
from streeteasy_archive.extract import extract, kind_for
from streeteasy_archive.scope import configure_building, discovery_links, expand
from streeteasy_archive.store import ArchiveStore

ROOT = "https://streeteasy.com/building/the-sierra-chelsea"
VIEW = ROOT + "?archive_view=unavailable-rentals"


def inventory_html(count=2):
    return f"""<div role="dialog"><button aria-pressed="true">For rent</button>
    <button role="tab">All ({count})</button><table><tbody>
    <tr><td><a href="/rental/123">#1A</a></td></tr>
    <tr><td><a href="/rental/456">#2A</a></td></tr>
    </tbody></table></div>""".encode()


def test_complete_inventory_discovers_detail_pages_and_rejects_truncation():
    d = extract(inventory_html(), VIEW)
    assert d["inventory"]["count"] == 2
    assert {x["url"] for x in d["inventory"]["links"]} == {
        "https://streeteasy.com/rental/123",
        "https://streeteasy.com/rental/456",
    }
    assert kind_for(VIEW) == "inventory"
    with pytest.raises(ValueError, match="incomplete"):
        extract(inventory_html(393), VIEW)
    with pytest.raises(ValueError, match="category"):
        extract(inventory_html(), ROOT + "?archive_view=unavailable-sales")


def test_sales_inventory_preserves_recorded_closings_without_queueing_them():
    body = b"""<div role="dialog"><button aria-pressed="true">For sale</button>
      <button role="tab">All (2)</button><table><tbody>
      <tr><td><a href="/sale/123">#1A</a></td></tr>
      <tr><td><a href="/closing/456">#2A</a></td></tr>
      </tbody></table></div>"""
    data = extract(body, ROOT + "?archive_view=unavailable-sales")
    assert len(data["inventory"]["records"]) == 2
    assert data["inventory"]["records"][1] == {
        "url": "https://streeteasy.com/closing/456",
        "kind": "closing",
    }
    assert len(data["inventory"]["links"]) == 1


def test_backfill_reuses_building_and_adds_inventory_and_history(tmp_path):
    s = ArchiveStore(tmp_path)
    g = s.new_generation()
    d = extract(b'<a href="/building/the-sierra-chelsea/3j">3J</a>', ROOT)
    s.enqueue(g, [{"url": ROOT, "kind": "building"}])
    s.record(g, ROOT, 200, {}, b"building", "text/html", d)
    configure_building(s, g, ROOT)
    assert (
        s.db.execute("SELECT state FROM frontier WHERE url=?", (ROOT,)).fetchone()[0]
        == "done"
    )
    assert s.db.execute("SELECT 1 FROM scope_urls WHERE url=?", (VIEW,)).fetchone()
    inv = extract(inventory_html(), VIEW)
    s.record(g, VIEW, 200, {}, inventory_html(), "text/html", inv)
    expand(s, g, inv, VIEW, building=ROOT)
    assert s.db.execute(
        "SELECT 1 FROM scope_urls WHERE url='https://streeteasy.com/rental/123'"
    ).fetchone()
    configure_building(
        s, g, ROOT
    )  # Resume does not download completed inventory again.
    assert (
        s.db.execute("SELECT state FROM frontier WHERE url=?", (VIEW,)).fetchone()[0]
        == "done"
    )
    configure_building(s, g, ROOT, False)
    urls = {r[0] for r in s.db.execute("SELECT url FROM scope_urls")}
    assert urls == {ROOT, ROOT + "/3j"}
    s.close()


def test_current_discovery_does_not_follow_price_event_urls():
    d = {
        "scripts": [{"json": {"priceHistories": [{"listingUrl": "/rental/123"}]}}],
        "links": [{"url": "/rental/123"}, {"url": ROOT + "/3j"}],
    }
    assert discovery_links(d, ROOT + "/3j", False) == []


def test_flight_summary_prevents_false_empty_inventory():
    script = b"""<script>self.__next_f.push([1,"a:{\\"rentalSummary\\":\\"$b\\",\\"saleSummary\\":\\"$d\\"}\\nb:[\\"$c\\"]\\nc:{\\"unavailableCount\\":393}\\nd:[\\"$e\\"]\\ne:{\\"unavailableCount\\":0}\\n"])</script>"""
    data = extract(script, ROOT)
    urls = {x["url"] for x in discovery_links(data, ROOT)}
    assert VIEW in urls
    assert ROOT + "?archive_view=unavailable-sales" not in urls
    empty = b'<div role="dialog"><button aria-pressed="true">For rent</button><button role="tab">All (0)</button></div>'
    with pytest.raises(ValueError, match="summary"):
        extract(script + empty, VIEW)


def test_inventory_transport_expands_correct_category(monkeypatch):
    from scrapy import Request
    from streeteasy_archive.oxylabs import OxylabsDownloadHandler
    from streeteasy_archive import oxylabs

    monkeypatch.setattr(oxylabs, "_credentials", lambda: ("user", "password"))
    payloads = []

    class Result:
        status_code = 200
        headers = {}

        def json(self):
            return {
                "results": [{"status_code": 200, "content": inventory_html().decode()}]
            }

    def post(*args, **kwargs):
        payloads.append(kwargs["json"])
        return Result()

    monkeypatch.setattr(oxylabs.requests, "post", post)
    response = asyncio.run(OxylabsDownloadHandler().download_request(Request(VIEW)))
    assert payloads[0]["url"] == ROOT
    assert payloads[0]["render"] == "html"
    instructions = payloads[0]["browser_instructions"]
    assert "For rent" in instructions[2]["selector"]["value"]
    assert [item["type"] for item in instructions] == [
        "click",
        "wait_for_element",
        "click",
        "wait_for_element",
        "wait_for_element",
    ]
    assert 'aria-pressed="true"' in instructions[3]["selector"]["value"]
    assert "/rental/" in instructions[4]["selector"]["value"]
    assert ".//a[" in instructions[4]["selector"]["value"]
    assert response.url == VIEW  # Distinct durable queue/capture identity.

    sale_view = ROOT + "?archive_view=unavailable-sales"
    asyncio.run(OxylabsDownloadHandler().download_request(Request(sale_view)))
    assert "/sale/" in payloads[-1]["browser_instructions"][-1]["selector"]["value"]
    assert "/closing/" in payloads[-1]["browser_instructions"][-1]["selector"]["value"]


def test_inventory_parser_gap_is_saved_and_does_not_pause_other_work(tmp_path):
    from streeteasy_archive.crawler import ArchiveSpider

    spider = ArchiveSpider.from_crawler(
        Crawler(ArchiveSpider, Settings()),
        data_dir=tmp_path,
        transport="oxylabs",
        concurrency=1,
        include_unavailable=True,
    )
    spider.store.enqueue(spider.generation, [{"url": VIEW, "kind": "inventory"}])
    request = list(spider.start_requests())[0]
    response = HtmlResponse(
        url=VIEW, body=b'<div role="dialog"></div>', request=request
    )
    assert list(spider.parse(response)) == []
    row = spider.store.db.execute(
        "SELECT state,next_attempt FROM frontier WHERE generation=? AND url=?",
        (spider.generation, VIEW),
    ).fetchone()
    assert row["state"] == "pending" and row["next_attempt"] > 0
    assert spider.store.db.execute(
        "SELECT body_hash FROM observations WHERE url=? ORDER BY id DESC LIMIT 1",
        (VIEW,),
    ).fetchone()["body_hash"]
    assert not spider.stopped
    assert spider.store.status(spider.generation)["status"] != "paused"
    spider.store.close()
