import gzip
import json
from streeteasy_archive.extract import (
    is_gallery_url,
    kind_for,
    canonical_url,
    discover,
    extract,
)


def test_scope_and_identity():
    assert (
        canonical_url("/rental/123?featured=1&utm_source=x&page=2#foo")
        == "https://streeteasy.com/rental/123?page=2"
    )
    assert canonical_url("https://streeteasy.com.evil.test/rental/123") is None
    assert not discover(
        b'<a href="/users/auth/google">login</a><a href="/building/x/documents">private</a>',
        "https://streeteasy.com",
    )


def test_off_market_sitemap_and_lastmod():
    xml = b'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>https://streeteasy.com/sitemaps/secure/nyc_off_market_buildings_16.xml.gz</loc><lastmod>2026-09-07</lastmod></sitemap><sitemap><loc>https://streeteasy.com/sitemaps/secure/nyc_agents_0.xml.gz</loc></sitemap></sitemapindex>'
    links = discover(
        gzip.compress(xml),
        "https://streeteasy.com/sitemaps/secure/nyc_sitemap_index.xml",
    )
    assert len(links) == 1
    assert links[0]["lastmod"] == "2026-09-07"


def test_flight_history_and_unknown_fields_preserved():
    chunk = [
        1,
        'a:["$",null,{"history":[{"url":"/building/example/rental/123","unknownFutureField":42}]}]',
    ]
    html = (
        "<html><body><script>self.__next_f.push("
        + json.dumps(chunk)
        + ')</script><script type="application/ld+json">{"price":100}</script><table><tr><td>2020 rented</td></tr></table></body></html>'
    ).encode()
    data = extract(html, "https://streeteasy.com/building/example")
    assert data["scripts"][0]["flight_chunks"] == [chunk]
    assert data["scripts"][1]["json"] == {"price": 100}
    assert (
        data["links"][0]["url"] == "https://streeteasy.com/building/example/rental/123"
    )
    assert "2020 rented" in data["tables"][0]


def test_modern_unit_urls_and_pagination():
    links = discover(
        b'<a href="/building/ruby-chelsea/n02m">unit</a><a href="/building/x/ph">penthouse</a><a href="/for-rent/chelsea?page=2">next</a>',
        "https://streeteasy.com",
    )
    assert [x["kind"] for x in links] == ["listing", "listing", "search"]


def test_raw_json_and_security_scope():
    assert (
        extract(
            b'{"unknown":{"nested":17}}',
            "https://streeteasy.com/rental/1",
            "application/json",
        )["json"]["unknown"]["nested"]
        == 17
    )
    assert canonical_url("https://user:password@streeteasy.com/rental/1") is None
    assert canonical_url("https://streeteasy.com:9999/rental/1") is None
    assert (
        discover(
            b'<a href="https://streeteasy.com.evil.org/sale/123">x</a>',
            "https://streeteasy.com",
        )
        == []
    )


def test_detail_tracking_token_does_not_duplicate_canonical_listing():
    assert (
        canonical_url(
            "/building/ten23/04c?lstt=opaque-tracking&featured=1&utm_source=x"
        )
        == "https://streeteasy.com/building/ten23/04c"
    )


def test_showcase_alias_and_nonlisting_endpoints():
    base = "https://streeteasy.com/building/example"
    assert canonical_url(base + "/1a?showcase=1&similarHDP2=1") == base + "/1a"
    assert kind_for(base + "/export_owner_list") is None
    assert kind_for(base + "/media_gallery") is None


def test_media_gallery_routes_are_excluded_but_source_metadata_is_retained():
    routes = [
        "/building/example/media_gallery",
        "/building/example/4c/media_gallery",
        "/building/example/rental/123/media_gallery",
        "/rental/123/media_gallery",
        "/sale/456/media_gallery",
    ]
    for route in routes:
        url = "https://streeteasy.com" + route
        assert is_gallery_url(url)
        assert kind_for(url) is None

    body = b"""<html><body><script>window.gallery = true</script>
      <img src="https://images.example.test/photo.jpg">
    </body></html>"""
    data = extract(body, "https://streeteasy.com/building/example/4c/media_gallery")
    assert data["scripts"][0]["text"].strip() == "window.gallery = true"
    assert data["images"][0]["src"].endswith("/photo.jpg")


def test_non_gallery_detail_history_and_inventory_routes_remain_classified():
    assert not is_gallery_url("https://streeteasy.com/building/example/4c")
    assert not is_gallery_url("https://streeteasy.com/building/example/history")
    assert not is_gallery_url(
        "https://streeteasy.com/building/example?archive_view=unavailable-rentals"
    )
    assert kind_for("https://streeteasy.com/building/example/4c") == "listing"
    assert kind_for("https://streeteasy.com/building/example/history") == "building"
    assert (
        kind_for(
            "https://streeteasy.com/building/example?archive_view=unavailable-rentals"
        )
        == "inventory"
    )


def test_main_building_presentation_filters_collapse_aliases():
    base = "https://streeteasy.com/building/example"
    assert canonical_url(base + "?similar=1&unit_type=rentals") == canonical_url(base)
    assert canonical_url(base + "?unit_type=sales&similar=1") == canonical_url(base)


def test_main_building_inventory_intents_and_other_parameters_are_preserved():
    base = "https://streeteasy.com/building/example"
    rentals = canonical_url(
        base + "?archive_view=unavailable-rentals&similar=1&page=2&future=x"
    )
    sales = canonical_url(
        base + "?archive_view=unavailable-sales&unit_type=sales&page=2&future=x"
    )
    assert (
        rentals
        == "https://streeteasy.com/building/example?archive_view=unavailable-rentals&future=x&page=2"
    )
    assert (
        sales
        == "https://streeteasy.com/building/example?archive_view=unavailable-sales&future=x&page=2"
    )

    unit = canonical_url(base + "/4c?similar=1&unit_type=sales&page=2&future=x")
    assert (
        unit
        == "https://streeteasy.com/building/example/4c?future=x&page=2&similar=1&unit_type=sales"
    )


def test_flight_urls_split_across_script_tags():
    import json
    from streeteasy_archive.extract import discover

    base = "https://streeteasy.com/building/ohm-312-11th-avenue-new_york"
    parts = [
        'a:{"documentsUrl":"' + base + "/d",
        'ocuments","urlPath":"' + base + '/09b"}\n',
    ]
    body = "".join(
        "<script>self.__next_f.push(" + json.dumps([1, text]) + ")</script>"
        for text in parts
    ).encode()
    urls = {r["url"] for r in discover(body, base)}
    assert base + "/d" not in urls
    assert base + "/documents" not in urls
    assert base + "/09b" in urls
