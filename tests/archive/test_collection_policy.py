import json

from streeteasy_archive.collection_policy import annotate, exclusion_reason, setup
from streeteasy_archive.scope import expand
from streeteasy_archive.store import ArchiveStore

UNIT = "https://streeteasy.com/building/example/4c"
EPISODE = "https://streeteasy.com/rental/123"


def body(canonical=UNIT, category="rental"):
    listing = {
        "id": "123",
        "propertyDetails": {"address": {"street": "123 Test Street"}},
        "propertyHistory": [
            {
                "listingId": "123",
                category + "EventsOfInterest": [{"date": "2020-01-01", "price": 3000}],
            }
        ],
    }
    head = f'<link rel="canonical" href="{canonical}">' if canonical else ""
    return (
        "<html><head>"
        + head
        + '</head><body><script type="application/json">'
        + json.dumps({"listing": listing})
        + "</script></body></html>"
    ).encode()


def test_claim_never_spends_on_sales_or_unassociated_episodes(tmp_path):
    s = ArchiveStore(tmp_path)
    g = s.new_generation()
    setup(s, g)
    urls = [
        EPISODE,
        "https://streeteasy.com/sale/123",
        "https://streeteasy.com/building/example?archive_view=unavailable-sales",
        UNIT,
    ]
    s.enqueue(g, [{"url": u, "kind": "listing"} for u in urls])
    assert s.claim(g)["url"] == UNIT
    assert s.db.execute("SELECT count(*) FROM collection_exclusions").fetchone()[0] == 3
    assert s.db.execute("SELECT sum(attempts) FROM frontier").fetchone()[0] == 1
    s.close()


def test_canonical_rental_evidence_unlocks_episode_and_survives_resume(tmp_path):
    s = ArchiveStore(tmp_path)
    g = s.new_generation()
    setup(s, g)
    s.enqueue(g, [{"url": EPISODE, "kind": "listing"}])
    assert s.claim(g) is None
    data = {}
    annotate(s, g, data, body(), UNIT)
    assert data["collection_policy"]["eligible"]
    assert exclusion_reason(s, g, EPISODE) is None
    s.close()
    s = ArchiveStore(tmp_path)
    assert s.claim(g)["url"] == EPISODE
    assert s.db.execute("SELECT count(*) FROM collection_exclusions").fetchone()[0] == 1
    s.close()


def test_missing_canonical_sales_and_conflicting_units_do_not_expand(tmp_path):
    s = ArchiveStore(tmp_path)
    g = s.new_generation()
    setup(s, g)
    for raw in [body(canonical=None), body(category="sale")]:
        data = {"links": [{"url": EPISODE}], "scripts": []}
        annotate(s, g, data, raw, UNIT)
        assert not data["collection_policy"]["eligible"]
        expand(s, g, data, UNIT)
        assert not s.db.execute(
            "SELECT 1 FROM scope_urls WHERE url=?", (EPISODE,)
        ).fetchone()
    annotate(s, g, {}, body(), UNIT)
    other = "https://streeteasy.com/building/example/5c"
    annotate(s, g, {}, body(canonical=other), other)
    assert exclusion_reason(s, g, EPISODE) == "conflicting_canonical_unit_association"
    s.close()


def test_archived_unit_replay_establishes_membership_without_new_observations(tmp_path):
    from streeteasy_archive.extract import extract

    s = ArchiveStore(tmp_path)
    g = s.new_generation()
    raw = body()
    data = extract(raw, UNIT, "text/html")
    s.record(g, UNIT, 200, {}, raw, "text/html", data)
    setup(s, g)
    assert exclusion_reason(s, g, EPISODE) is None
    assert s.db.execute("SELECT count(*) FROM observations").fetchone()[0] == 1
    s.close()


def test_parsing_before_raw_capture_does_not_authorize_requests(tmp_path):
    s = ArchiveStore(tmp_path)
    g = s.new_generation()
    setup(s, g)
    annotate(s, g, {}, body(), UNIT, persist=False)
    assert exclusion_reason(s, g, EPISODE) == "missing_canonical_unit_association"
    assert (
        exclusion_reason(s, g, EPISODE + "-unknown")
        == "unsupported_advertisement_route"
    )
    s.close()


def save_unit(s, g, raw=None):
    from streeteasy_archive.extract import extract

    raw = raw or body()
    data = extract(raw, UNIT, "text/html")
    annotate(s, g, data, raw, UNIT, persist=False)
    digest = s.record(g, UNIT, 200, {}, raw, "text/html", data)
    annotate(s, g, data, raw, UNIT)
    return digest


def test_same_advertisement_unit_capture_reused_without_new_fetch(tmp_path):
    s = ArchiveStore(tmp_path)
    g = s.new_generation()
    setup(s, g)
    digest = save_unit(s, g)
    s.enqueue(g, [{"url": EPISODE, "kind": "listing"}])
    assert s.claim(g) is None
    state = s.db.execute(
        "SELECT state,attempts FROM frontier WHERE url=?", (EPISODE,)
    ).fetchone()
    assert tuple(state) == ("superseded", 0)
    proof = json.loads(
        s.db.execute(
            "SELECT reason FROM url_aliases WHERE url=?", (EPISODE,)
        ).fetchone()[0]
    )
    assert proof["body_hash"] == digest and proof["observation_id"]
    assert s.db.execute("SELECT count(*) FROM observations").fetchone()[0] == 1
    s.close()


def test_history_mention_does_not_replace_advertisements_own_capture(tmp_path):
    s = ArchiveStore(tmp_path)
    g = s.new_generation()
    setup(s, g)
    # The page describes advertisement 456 and mentions 123 in its history.
    save_unit(s, g, body().replace(b'"id": "123"', b'"id": "456"'))
    s.enqueue(g, [{"url": EPISODE, "kind": "listing"}])
    assert s.claim(g)["url"] == EPISODE
    s.close()


def test_missing_body_or_later_failure_prevents_unit_reuse(tmp_path):
    for failure in ("missing_body", "later_failure"):
        s = ArchiveStore(tmp_path / failure)
        g = s.new_generation()
        setup(s, g)
        digest = save_unit(s, g)
        if failure == "missing_body":
            s.body_path(digest).unlink()
        else:
            s.record_gap(g, UNIT, 404, {}, "not found", body=b"not found")
        s.enqueue(g, [{"url": EPISODE, "kind": "listing"}])
        assert s.claim(g)["url"] == EPISODE
        s.close()


def test_legacy_unit_capture_is_reinterpreted_without_rewriting_snapshot(tmp_path):
    from streeteasy_archive.extract import extract

    s = ArchiveStore(tmp_path)
    g = s.new_generation()
    raw = body()
    data = extract(raw, UNIT, "text/html")
    s.record(g, UNIT, 200, {}, raw, "text/html", data)
    original = s.db.execute("SELECT extracted FROM snapshots").fetchone()[0]
    setup(s, g)
    s.enqueue(g, [{"url": EPISODE, "kind": "listing"}])
    assert s.claim(g) is None
    assert s.db.execute("SELECT extracted FROM snapshots").fetchone()[0] == original
    s.close()


INVENTORY = "https://streeteasy.com/building/example?archive_view=unavailable-rentals"


def inventory_row(ad, label):
    link = f'<a href="{ad}" target="_blank">'
    return (
        f"<tr><td>{link}09/15/26</a></td><td>{link}{label}</a></td>"
        "<td><h6>$4,995</h6></td><td>1 bed</td><td>1 bath</td><td>- ft²</td><td>-</td></tr>"
    )


def inventory_data(rows):
    return {
        "inventory": {"rows": [inventory_row(ad, label) for ad, label in rows]},
        "links": [],
        "scripts": [],
    }


def test_inventory_labels_become_unit_probes_only_for_rental_ads():
    from streeteasy_archive.collection_policy import inventory_unit_probes

    data = inventory_data(
        [
            (EPISODE, "#4C"),
            ("https://streeteasy.com/rental/124", "#9C-EAST"),
            ("https://streeteasy.com/rental/125", ""),
            ("https://streeteasy.com/sale/126", "#5A"),
            ("https://streeteasy.com/rental/127", "#Photos"),
            ("https://streeteasy.com/rental/128", "#4c"),
        ]
    )
    assert inventory_unit_probes(data, INVENTORY) == {
        UNIT: EPISODE,
        "https://streeteasy.com/building/example/9ceast": "https://streeteasy.com/rental/124",
    }
    sales = INVENTORY.replace("rentals", "sales")
    assert inventory_unit_probes(data, sales) == {}
    assert inventory_unit_probes(data, "https://streeteasy.com/building/example") == {}


def test_archived_in_scope_inventories_enroll_probes_offline(tmp_path):
    s = ArchiveStore(tmp_path)
    g = s.new_generation()
    other = "https://streeteasy.com/building/elsewhere?archive_view=unavailable-rentals"
    for url in (INVENTORY, other):
        s.record(
            g,
            url,
            200,
            {},
            b"<html></html>",
            "text/html",
            inventory_data([(EPISODE, "#4C")]),
        )
    s.db.execute(
        "INSERT INTO scope_buildings VALUES(?,?)",
        (g, "https://streeteasy.com/building/example"),
    )
    s.db.commit()
    before = s.db.execute("SELECT count(*) FROM observations").fetchone()[0]
    setup(s, g)
    setup(s, g)
    reasons = s.db.execute(
        "SELECT url, reason FROM scope_urls WHERE reason LIKE 'inventory-label%'"
    ).fetchall()
    assert [tuple(r) for r in reasons] == [
        (UNIT, f"inventory-label-unit-probe-v1 from {EPISODE}")
    ]
    assert s.db.execute("SELECT count(*) FROM observations").fetchone()[0] == before
    assert s.claim(g, scoped=True, prefer_units=True)["url"] == UNIT
    s.close()


def test_live_inventory_expansion_enrolls_probe_for_verified_building(tmp_path):
    s = ArchiveStore(tmp_path)
    g = s.new_generation()
    setup(s, g)
    s.db.execute(
        "INSERT INTO scope_buildings VALUES(?,?)",
        (g, "https://streeteasy.com/building/example"),
    )
    s.db.commit()
    expand(
        s, g, inventory_data([(EPISODE, "#4C")]), INVENTORY, neighborhood="west-village"
    )
    assert s.db.execute("SELECT 1 FROM scope_urls WHERE url=?", (UNIT,)).fetchone()
    expand(
        s,
        g,
        inventory_data([("https://streeteasy.com/rental/9", "#7")]),
        "https://streeteasy.com/building/elsewhere?archive_view=unavailable-rentals",
        neighborhood="west-village",
    )
    assert not s.db.execute(
        "SELECT 1 FROM scope_urls WHERE url LIKE '%elsewhere/7'"
    ).fetchone()
    s.close()


def test_unit_routes_are_claimed_before_associated_ads(tmp_path):
    s = ArchiveStore(tmp_path)
    g = s.new_generation()
    setup(s, g)
    annotate(s, g, {}, body(), UNIT)  # EPISODE is now associated
    other = "https://streeteasy.com/building/example/5d"
    s.enqueue(
        g, [{"url": EPISODE, "kind": "listing"}, {"url": other, "kind": "listing"}]
    )
    assert s.claim(g, prefer_units=True)["url"] == other
    assert s.claim(g, prefer_units=True)["url"] == EPISODE
    s.close()
