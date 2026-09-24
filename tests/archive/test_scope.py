import json
from streeteasy_archive.scope import expand, configure, SEEDS
from streeteasy_archive.store import ArchiveStore


def payload(*objects, links=()):
    text = "".join(f"{i:x}:" + json.dumps(obj) + "\n" for i, obj in enumerate(objects))
    return {
        "scripts": [{"flight_chunks": [[1, text]]}],
        "links": [{"url": u} for u in links],
    }


def test_scope_uses_area_evidence_not_neighborhood_dictionary(tmp_path):
    s = ArchiveStore(tmp_path)
    g = s.new_generation()
    root = "https://streeteasy.com/building/inside"
    outside = "https://streeteasy.com/building/outside"
    d = payload(
        {"areaName": "Chelsea", "urlPath": "/building/inside/1a"},
        {"areaName": "Hudson Yards", "urlPath": "/building/outside/1a"},
        {"id": "115", "name": "Chelsea", "short": "chelsea"},
        links=[
            root + "/2b",
            outside + "/2b",
            "/for-rent/hudson-yards",
            "/for-rent/chelsea?page=2",
            "/for-rent/chelsea/price:5000-6000",
        ],
    )
    expand(s, g, d, SEEDS[0])
    urls = {r[0] for r in s.db.execute("SELECT url FROM scope_urls")}
    assert root in urls and root + "/2b" in urls
    assert not any("outside" in u or "hudson-yards" in u or "price:" in u for u in urls)
    assert "https://streeteasy.com/for-rent/chelsea?page=2" in urls
    s.enqueue(g, [{"url": outside + "/1a", "kind": "listing"}])
    s.close()
    s = ArchiveStore(tmp_path)
    while row := s.claim(g, now=9999999999, scoped=True):
        assert row["url"] in urls
        s.record(g, row["url"], 200, {}, b"fixture")
    assert s.claim(g, now=9999999999)["url"] == outside + "/1a"
    s.close()


def test_history_links_require_property_association(tmp_path):
    s = ArchiveStore(tmp_path)
    g = s.new_generation()
    source = "https://streeteasy.com/building/ten23/4c"
    history = {"priceHistories": [{"listingUrl": "https://streeteasy.com/rental/123"}]}
    expand(s, g, payload(history), "https://streeteasy.com/")
    assert s.db.execute("SELECT count(*) FROM scope_urls").fetchone()[0] == 0
    expand(
        s,
        g,
        payload(
            {"name": "TEN23", "slug": "ten23", "area": {"id": "west-chelsea"}}, history
        ),
        source,
    )
    assert s.db.execute(
        "SELECT 1 FROM scope_urls WHERE url=?", ("https://streeteasy.com/rental/123",)
    ).fetchone()
    s.close()


def test_directory_includes_off_market_and_reuses_completed(tmp_path):
    s = ArchiveStore(tmp_path)
    g = s.new_generation()
    root = "https://streeteasy.com/building/no-current-listings"
    expand(
        s,
        g,
        payload({"@type": "ItemList", "itemListElement": [{"item": {"url": root}}]}),
        "https://streeteasy.com/buildings/chelsea",
    )
    s.record(g, root, 200, {}, b"archived")
    configure(s, g)
    assert (
        s.db.execute("SELECT state FROM frontier WHERE url=?", (root,)).fetchone()[0]
        == "done"
    )
    assert s.db.execute("SELECT 1 FROM scope_buildings WHERE url=?", (root,)).fetchone()
    s.close()


def test_inline_flight_records_and_related_building_rejection(tmp_path):
    s = ArchiveStore(tmp_path)
    g = s.new_generation()
    primary = {"name": "Inside", "slug": "inside", "area": {"id": "chelsea"}}
    related = {"name": "Unrelated", "slug": "unrelated", "area": {"id": "chelsea"}}
    data = {
        "scripts": [
            {
                "flight_chunks": [
                    [
                        1,
                        "a:T4,text<b:"
                        + json.dumps(primary)
                        + "\n"
                        + "c:"
                        + json.dumps(related),
                    ]
                ]
            }
        ],
        "links": [],
    }
    expand(s, g, data, "https://streeteasy.com/building/inside/1a")
    roots = {r[0] for r in s.db.execute("SELECT url FROM scope_buildings")}
    assert roots == {"https://streeteasy.com/building/inside"}
    s.close()


def test_membership_split_across_flight_scripts(tmp_path):
    s = ArchiveStore(tmp_path)
    g = s.new_generation()
    text = "a:" + json.dumps({"areaName": "Chelsea", "urlPath": "/building/inside/09b"})
    data = {
        "scripts": [
            {"flight_chunks": [[1, text[:20]]]},
            {"flight_chunks": [[1, text[20:]]]},
        ],
        "links": [],
    }
    expand(s, g, data, "https://streeteasy.com/for-rent/chelsea")
    assert s.db.execute(
        "SELECT 1 FROM scope_urls WHERE url=?",
        ("https://streeteasy.com/building/inside/09b",),
    ).fetchone()
    s.close()


def test_legacy_directory_cards_exclude_navigation_and_other_areas(tmp_path):
    from streeteasy_archive.extract import extract

    html = b"""<a href='/building/menu'>menu</a>
    <li class='item building'><h2 class='details-title'><a href='/building/offmarket'>Home</a></h2><div class='details_info'><span class='detail_cell'>Rental Building in West Chelsea</span></div></li>
    <li class='item building'><h2 class='details-title'><a href='/building/outside'>Other</a></h2><div class='details_info'><span class='detail_cell'>Condo in Hudson Yards</span></div></li>"""
    url = "https://streeteasy.com/buildings/chelsea"
    s = ArchiveStore(tmp_path)
    g = s.new_generation()
    expand(s, g, extract(html, url, "text/html"), url)
    roots = {r[0] for r in s.db.execute("SELECT url FROM scope_buildings")}
    assert roots == {"https://streeteasy.com/building/offmarket"}
    s.close()


def test_resume_watermark_skips_old_evidence_and_reads_new(tmp_path, monkeypatch):
    import streeteasy_archive.scope as scope

    s = ArchiveStore(tmp_path)
    g = s.new_generation()
    root = "https://streeteasy.com/building/inside"
    s.record(
        g,
        root,
        200,
        {},
        b"first",
        "text/html",
        payload({"name": "Inside", "slug": "inside", "area": {"id": "chelsea"}}),
    )
    configure(s, g)
    original = scope.expand
    calls = []

    def track(*args, **kwargs):
        calls.append(args[3])
        return original(*args, **kwargs)

    monkeypatch.setattr(scope, "expand", track)
    configure(s, g)
    assert calls == []
    s.record(
        g,
        root,
        200,
        {},
        b"next",
        "text/html",
        payload(
            {"name": "Inside", "slug": "inside", "area": {"id": "chelsea"}},
            links=[root + "/2a"],
        ),
    )
    configure(s, g)
    assert calls == [root]
    assert s.db.execute(
        "SELECT 1 FROM scope_urls WHERE url=?", (root + "/2a",)
    ).fetchone()
    s.close()


def test_scope_batch_rolls_back_its_watermark_on_failure(tmp_path, monkeypatch):
    import pytest
    import streeteasy_archive.scope as scope

    s = ArchiveStore(tmp_path)
    g = s.new_generation()
    root = "https://streeteasy.com/building/inside"
    s.record(
        g,
        root,
        200,
        {},
        b"first",
        "text/html",
        payload({"name": "Inside", "slug": "inside", "area": {"id": "chelsea"}}),
    )
    original = scope._enroll

    def fail(store, generation, urls, roots=()):
        original(store, generation, urls, roots)
        if root in roots:
            raise RuntimeError("simulated interruption")

    monkeypatch.setattr(scope, "_enroll", fail)
    with pytest.raises(RuntimeError):
        configure(s, g)
    assert (
        s.db.execute(
            "SELECT value FROM metadata WHERE key=?",
            (scope._marker_key(g, None, True),),
        ).fetchone()[0]
        == "0"
    )
    assert not s.db.execute(
        "SELECT 1 FROM scope_buildings WHERE url=?", (root,)
    ).fetchone()
    monkeypatch.setattr(scope, "_enroll", original)
    configure(s, g)
    assert s.db.execute("SELECT 1 FROM scope_buildings WHERE url=?", (root,)).fetchone()
    s.close()
