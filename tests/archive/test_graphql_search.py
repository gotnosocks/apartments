"""The area collector against a fake GraphQL API, with no network requests."""

from datetime import UTC, datetime, timedelta
import json
import re
import urllib.parse

import pytest
import requests

from apartments import graphql_listing
from apartments.graphql_listing import api_document, parse_capture
from streeteasy_archive import graphql_search as gs
from streeteasy_archive.graphql_search import Budget, Client, Collector, Stop
from streeteasy_archive.store import ArchiveStore

SLUG = "demo-500-west-43-street-new_york"
BUILDING_PAGE = f"https://streeteasy.com/building/{SLUG}"
UNIT_12B = f"{BUILDING_PAGE}/12b"
UNIT_4A = f"{BUILDING_PAGE}/4a"


def rental(url):
    return f"https://streeteasy.com/rental/{url}"


def record(ad, unit, status, price, beds, history, latest, building="17503"):
    """An ad's record as rentalsByListingIds writes it, with typenames and float numbers."""
    return {
        "__typename": "RentalListing",
        "id": str(ad),
        "slug": unit,
        "buildingId": building,
        "status": status,
        "createdAt": "2026-09-01T12:00:00Z",
        "latestListing": {
            "id": str(latest),
            "status": "ACTIVE",
            "pricing": {"price": 1.0},
        },
        "pricing": {"__typename": "Pricing", "price": float(price)},
        "propertyDetails": {
            "address": {
                "displayUnit": "#" + unit.upper(),
                "street": "500 West 43rd Street",
            },
            "bedroomCount": None if beds is None else float(beds),
            "fullBathroomCount": 1.0,
            "halfBathroomCount": 0.0,
        },
        "propertyHistory": [
            {
                "__typename": "PropertyHistory",
                "listingId": str(h),
                "rentalEventsOfInterest": [
                    {
                        "__typename": "RentalStatusChangeOfInterest",
                        "date": f"2026-0{1 + i}-01",
                        "price": float(price),
                        "status": "LISTED",
                    }
                ],
            }
            for i, h in enumerate(history)
        ],
    }


HISTORY_12B = [1300005, 1300003, 1300001, 1199999]


def world():
    """Ads keyed by ID. Unit 12b's ad 1300003 has no record in the API."""
    ads = {
        "1300005": record(1300005, "12b", "ACTIVE", 4100, 1, HISTORY_12B, 1300005),
        "1300001": record(1300001, "12b", "RENTED", 3900, 1, HISTORY_12B, 1300005),
        "1199999": record(1199999, "12b", "RENTED", 3000, 1, HISTORY_12B, 1300005),
        "1300007": record(1300007, "4a", "ACTIVE", 2500, 0, [1300007], 1300007),
        "1300010": record(
            1300010, "7c", "ACTIVE", 5200, 2, [1300010], 1300010, "17504"
        ),
    }
    buildings = {
        "17503": {
            "__typename": "Building",
            "id": "17503",
            "slug": SLUG,
            "name": "Demo",
            "geoCenter": {"latitude": 40.76, "longitude": -73.99},
        },
        "17504": {
            "__typename": "Building",
            "id": "17504",
            "slug": None,
            "name": "No slug",
        },
    }
    return ads, buildings


def search_rows(ads, ids):
    return [
        (
            int(i),
            ads[str(i)]["pricing"]["price"],
            ads[str(i)]["propertyDetails"]["bedroomCount"],
            ads[str(i)]["status"],
        )
        for i in ids
    ]


class FakeResponse:
    def __init__(self, status_code, payload=None, headers=None):
        self.status_code = status_code
        self.headers = headers or {}
        self.payload = payload

    def json(self):
        if self.payload is None:
            raise ValueError("not JSON")
        return self.payload


def oxylabs(content, status=200):
    return FakeResponse(200, {"results": [{"status_code": status, "content": content}]})


SEARCH = re.compile(
    r"(\w+): searchRentals\(input: \{sorting: \{attribute: LISTED_AT, direction: (\w+)\}, "
    r"adStrategy: NONE, filters: \{(.*?)\}, perPage: (\d+), page: 1\}\)"
)
BY_IDS = re.compile(r"(\w+): (rentalsByListingIds|buildingsByIds)\(ids: \[([\d ]*)\]\)")


class FakeAPI:
    """Oxylabs and api-v6 together: answers each aliased field from the world's tables.

    `search` holds (ID, price, bedrooms, status) rows. `areas` maps an ID to its area, and
    a search with an `areas` filter keeps only the IDs it maps into the filter. With no map,
    every row matches. `fail(query)` may return a response in place of the answer.
    """

    def __init__(self, ads, buildings, search, fail=None):
        self.ads, self.buildings, self.search = ads, buildings, search
        self.fail = fail or (lambda query: None)
        self.areas = {}
        self.queries = []

    def __call__(self, url, **kw):
        assert url == gs.API_URL and kw["auth"] == ("user", "secret")
        target = kw["json"]["url"]
        assert target.startswith(gs.API_HOST) and len(target) <= gs.MAX_URL
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(target).query)["query"][0]
        self.queries.append(query)
        failure = self.fail(query)
        if failure is not None:
            return failure
        data = {}
        for alias, direction, filters, per_page in SEARCH.findall(query):
            data[alias] = self._search(direction, filters, int(per_page))
        for alias, root, ids in BY_IDS.findall(query):
            table = self.ads if root == "rentalsByListingIds" else self.buildings
            data[alias] = [table[i] for i in ids.split() if i in table]
        return oxylabs(json.dumps({"data": data}))

    def _search(self, direction, filters, per_page):
        rows = list(self.search)
        areas = re.search(r"areas: \[([\d, ]*)\]", filters)
        if self.areas and areas:
            wanted = {int(a) for a in areas[1].split(", ")}
            rows = [r for r in rows if self.areas.get(r[0]) in wanted]
        price = re.search(r"price: \{lowerBound: (\d+), upperBound: (\d+)\}", filters)
        beds = re.search(r"bedrooms: \{lowerBound: (\d+), upperBound: (\d+)\}", filters)
        if price:
            rows = [r for r in rows if int(price[1]) <= r[1] <= int(price[2])]
        if beds:
            rows = [
                r
                for r in rows
                if r[2] is not None and int(beds[1]) <= r[2] <= int(beds[2])
            ]
        if "rentalStatus: ACTIVE" in filters:
            rows = [r for r in rows if r[3] == "ACTIVE"]
        rows.sort(reverse=direction == "DESCENDING")
        answer = {"totalCount": len(rows)}
        if per_page > 1:
            answer["edges"] = [{"node": {"id": str(r[0])}} for r in rows[:per_page]]
        return answer


def make_api(**kw):
    ads, buildings = world()
    return FakeAPI(
        ads, buildings, search_rows(ads, [1300001, 1300005, 1300007, 1300010]), **kw
    )


def make_collector(
    root, api, *, max_requests=100, workers=1, region="test", areas=(103,), **kw
):
    client = Client(
        max_requests,
        64,
        post=api,
        credentials=lambda: ("user", "secret"),
        sleep=lambda s: None,
    )
    return Collector(
        ArchiveStore(root), client, region, list(areas), workers=workers, **kw
    )


def reads(api, root="rentalsByListingIds"):
    """The IDs of every `root` read in the API's queries."""
    return {
        int(i)
        for q in api.queries
        for ids in re.findall(root + r"\(ids: \[([\d ]*)\]\)", q)
        for i in ids.split()
    }


def frontier(c):
    return {
        r["url"]: r["state"]
        for r in c.db.execute(
            "SELECT url, state FROM frontier WHERE generation=?", (c.generation,)
        )
    }


def observations(c, url):
    return c.db.execute(
        "SELECT * FROM observations WHERE generation=? AND url=? ORDER BY id",
        (c.generation, url),
    ).fetchall()


def snapshots(c, url):
    return c.db.execute(
        "SELECT * FROM snapshots WHERE generation=? AND url=? ORDER BY id",
        (c.generation, url),
    ).fetchall()


def test_backfill_writes_buildings_units_and_ads(tmp_path):
    api = make_api()
    c = make_collector(tmp_path / "archive", api)
    report = c.collect()

    assert report["invocation"]["stopped"] is None
    assert report["enumeration"]["total"] == 4 and report["enumeration"]["hits"] == 4
    assert frontier(c) == {
        BUILDING_PAGE: "done",
        UNIT_12B: "done",
        UNIT_4A: "done",
        rental(1300005): "superseded",
        rental(1300007): "superseded",
        rental(1300001): "done",
        rental(1300003): "done",
        rental(1199999): "excluded",
        rental(1300010): "excluded",
    }
    # The unit page holds its latest ad's record, and the latest ad's route points at it.
    building = {"id": "17503", "slug": SLUG, "page": BUILDING_PAGE}
    (unit,) = observations(c, UNIT_12B)
    body = c.store.get_body(unit["body_hash"])
    assert body == graphql_listing.listing_body(1300005, building, api.ads["1300005"])
    row, events = parse_capture(body, UNIT_12B)
    assert row["parse_status"] == "ok" and row["canonical_unit_url"] == UNIT_12B
    assert row["listing_id"] == "1300005" and len(events) == 4
    alias = c.db.execute(
        "SELECT * FROM url_aliases WHERE url=?", (rental(1300005),)
    ).fetchone()
    assert alias["target_url"] == UNIT_12B
    # An older ad goes in under its own route with its own record.
    (older,) = observations(c, rental(1300001))
    assert (
        api_document(c.store.get_body(older["body_hash"]))["record"]["status"]
        == "RENTED"
    )
    (gap,) = observations(c, rental(1300003))
    assert gap["error"] == "API gave no record" and gap["body_hash"] is None
    exclusions = dict(
        c.db.execute(
            "SELECT url, reason FROM collection_exclusions WHERE generation=?",
            (c.generation,),
        )
    )
    assert exclusions == {
        rental(1199999): "before_min_listing_id",
        rental(1300010): "missing_canonical_unit_association",
    }
    memberships = dict(
        c.db.execute(
            "SELECT listing_key, unit_url FROM collection_memberships WHERE generation=?",
            (c.generation,),
        )
    )
    assert memberships == {
        "rental:1300005:detail": UNIT_12B,
        "rental:1300003:detail": UNIT_12B,
        "rental:1300001:detail": UNIT_12B,
        "rental:1199999:detail": UNIT_12B,
        "rental:1300007:detail": UNIT_4A,
    }
    (page,) = snapshots(c, BUILDING_PAGE)
    data = json.loads(page["extracted"])
    assert data["json"]["source"] == "buildingsByIds"
    assert graphql_listing.export_building(data)["latitude"] == 40.76
    assert report["write"] == {
        "ads_excluded": 1,
        "ads_gap": 1,
        "ads_record": 1,
        "ads_superseded": 2,
        "buildings_without_page": 1,
        "buildings_written": 1,
        "scoped_ads_before_cutoff": 1,
        "units_without_page": 1,
        "units_written": 2,
    }
    # Counts and ID reads go in one request each, ads in two rounds, buildings in one.
    kinds = [
        "count"
        if "totalCount" in q and "edges" not in q
        else "slice"
        if "edges" in q
        else q[6:15]
        for q in api.queries
    ]
    assert kinds == ["count", "slice", "ArchiveRe", "ArchiveRe", "ArchiveBu"]
    assert report["run_requests"] == {"ads": 2, "buildings": 1, "count": 1, "slice": 1}
    assert (tmp_path / "archive" / "graphql-search" / f"run-{c.run}.json").is_file()


def test_resume_after_budget_matches_one_run(tmp_path):
    whole = make_collector(tmp_path / "whole", make_api(), workers=4)
    whole.collect()

    api = make_api()
    first = make_collector(tmp_path / "parts", api, max_requests=3)
    report = first.collect()
    assert report["invocation"]["stopped"].startswith("spent the budget")
    first.store.close()
    second = make_collector(tmp_path / "parts", api)
    assert second.run == first.run
    report = second.collect()
    assert report["invocation"]["stopped"] is None
    assert frontier(second) == frontier(whole)
    # The resumed invocation reads only what the first one left.
    assert len(api.queries) == 5


def test_enumeration_splits_bands_down_to_bedrooms(tmp_path, monkeypatch):
    monkeypatch.setattr(gs, "CAP", 3)
    monkeypatch.setattr(gs, "EDGES", [0, 2000, 3000])
    monkeypatch.setattr(gs, "MAX_BEDS", 2)
    search = [(1300100 + i, 2500.0, 1.0, "ACTIVE") for i in range(5)]
    search += [(1300200, 2500.0, None, "ACTIVE"), (1300300, 1000.0, 0.0, "ACTIVE")]
    api = FakeAPI({}, {}, search)
    c = make_collector(tmp_path / "archive", api)
    c.enumerate()

    tree = c.tree()
    assert tree["total"] == 7 and not tree["pending"]
    assert sorted(tree["leaves"]) == [((0, 2000, -1), 1), ((2500, 2500, 1), 5)]
    assert tree["gaps"] == [((2500, 2500, -1), 1)]
    hits = {r[0] for r in c.db.execute("SELECT listing_id FROM graphql_search_hits")}
    # Five ads at one price and bedroom count: read from both ends of the listing order.
    assert hits == {1300100, 1300101, 1300102, 1300103, 1300104, 1300300}
    directions = {
        (r["lo"], r["direction"])
        for r in c.db.execute("SELECT * FROM graphql_search_slices")
    }
    assert directions == {(0, "ASCENDING"), (2500, "ASCENDING"), (2500, "DESCENDING")}


def test_failed_batches_split_and_single_ads_give_up(tmp_path):
    def fail(query):
        if "rentalsByListingIds" in query and "1300007" in query:
            return oxylabs("{}", status=400)

    api = make_api(fail=fail)
    c = make_collector(tmp_path / "archive", api)
    report = c.collect()

    assert report["invocation"]["stopped"] is None
    ad = c.db.execute(
        "SELECT * FROM graphql_search_ads WHERE listing_id=1300007"
    ).fetchone()
    assert ad["response_id"] is None
    tries = [q for q in api.queries if "rentalsByListingIds" in q and "1300007" in q]
    # The batch of four, its half, then three tries of the ad alone.
    assert len(tries) == 5
    errors = [
        r["error"]
        for r in c.db.execute("SELECT error FROM graphql_search_calls WHERE kind='ads'")
    ]
    assert errors.count("StreetEasy HTTP 400") == 5
    assert frontier(c)[rental(1300001)] == "done"
    assert frontier(c)[UNIT_12B] == "done"


def test_six_failures_in_a_row_stop_the_run(tmp_path):
    api = make_api(fail=lambda query: oxylabs("{}", status=500))
    c = make_collector(tmp_path / "archive", api)
    report = c.collect()
    assert report["invocation"]["stopped"] == "6 requests in a row failed"
    assert len(api.queries) == gs.FAILURES_IN_A_ROW
    assert (
        c.db.execute("SELECT finished FROM graphql_search_runs").fetchone()[0] is None
    )


def client(post, max_requests=10, rate=64, *, still=False):
    """A client on a clock that moves only when it sleeps, or never when `still` is set."""
    sleeps = []
    c = Client(
        max_requests,
        rate,
        post=post,
        credentials=lambda: ("user", "secret"),
        clock=lambda: 0.0 if still else sum(sleeps),
        sleep=sleeps.append,
    )
    return c, sleeps


def sequence(*responses):
    responses = list(responses)

    def post(url, **kw):
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    return post


def test_client_stops_on_refusals_and_challenges():
    for response in (
        FakeResponse(401),
        FakeResponse(402),
        oxylabs("{}", status=403),
        oxylabs("{}", status=429),
        oxylabs("<html><title>Just a moment...</title></html>"),
    ):
        c, _ = client(sequence(response))
        with pytest.raises(Stop):
            c.get(gs.API_HOST + "?query=x")


def test_client_retries_failed_posts_and_reports_failures():
    c, sleeps = client(
        sequence(
            FakeResponse(500),
            FakeResponse(429, headers={"Retry-After": "7"}),
            oxylabs('{"data": {}}'),
        )
    )
    reply = c.get(gs.API_HOST + "?query=x")
    assert reply.ok and reply.attempts == 3 and reply.body == b'{"data": {}}'
    assert sleeps == [5, 7.0] and c.calls == 3

    c, sleeps = client(sequence(requests.ConnectionError(), oxylabs("[]")))
    assert c.get(gs.API_HOST + "?query=x").ok and sleeps == [5]

    c, _ = client(sequence(FakeResponse(503), FakeResponse(503), FakeResponse(503)))
    reply = c.get(gs.API_HOST + "?query=x")
    assert not reply.ok and reply.error == "Oxylabs HTTP 503" and c.calls == 3

    c, _ = client(sequence(FakeResponse(200, {"results": []})))
    reply = c.get(gs.API_HOST + "?query=x")
    assert not reply.ok and "one result" in reply.error

    c, _ = client(sequence(oxylabs("{}", status=400)))
    reply = c.get(gs.API_HOST + "?query=x")
    assert not reply.ok and reply.status == 400 and reply.error == "StreetEasy HTTP 400"


def test_client_spaces_requests_and_keeps_to_its_budget():
    c, sleeps = client(
        lambda url, **kw: oxylabs("{}"), max_requests=3, rate=30, still=True
    )
    for _ in range(3):
        c.get(gs.API_HOST + "?query=x")
    assert sleeps == [2.0, 4.0]
    with pytest.raises(Budget):
        c.get(gs.API_HOST + "?query=x")
    for rate in (0, 64.5, 100):
        with pytest.raises(ValueError):
            client(lambda url, **kw: None, rate=rate)


def test_daily_run_rereads_live_ads_and_finds_new_ones(tmp_path):
    api = make_api()
    c = make_collector(tmp_path / "archive", api)
    c.collect()
    unit_snapshots = len(snapshots(c, UNIT_12B))
    rented_read = c.db.execute(
        "SELECT read FROM graphql_search_ads WHERE listing_id=1300001"
    ).fetchone()[0]
    c.store.close()

    # Unit 4a is let again under a new ad, and its old ad is rented.
    api.ads["1300020"] = record(
        1300020, "4a", "ACTIVE", 2700, 0, [1300020, 1300007], 1300020
    )
    api.ads["1300007"] = record(
        1300007, "4a", "RENTED", 2500, 0, [1300020, 1300007], 1300020
    )
    api.search = search_rows(api.ads, [1300001, 1300005, 1300007, 1300010, 1300020])
    api.queries.clear()
    daily = make_collector(tmp_path / "archive", api, active_only=True, new_run=True)
    report = daily.collect()

    assert (
        report["invocation"]["stopped"] is None and report["enumeration"]["hits"] == 3
    )
    reads = [q for q in api.queries if "rentalsByListingIds" in q]
    read_ids = {int(i) for q in reads for i in re.findall(r"\d{7}", q)}
    assert read_ids == {1300005, 1300007, 1300010, 1300020}
    # The unchanged latest ad gets a new observation of its unit and no new snapshot.
    assert len(observations(daily, UNIT_12B)) == 2
    assert len(snapshots(daily, UNIT_12B)) == unit_snapshots
    # The new ad takes over the unit page, and the old one is recorded under its own route.
    assert (
        api_document(
            daily.store.get_body(observations(daily, UNIT_4A)[-1]["body_hash"])
        )["listing_id"]
        == "1300020"
    )
    assert frontier(daily)[rental(1300020)] == "superseded"
    assert frontier(daily)[rental(1300007)] == "done"
    (own,) = observations(daily, rental(1300007))
    assert (
        api_document(daily.store.get_body(own["body_hash"]))["record"]["status"]
        == "RENTED"
    )
    assert len(observations(daily, rental(1300001))) == 1
    assert (
        daily.db.execute(
            "SELECT read FROM graphql_search_ads WHERE listing_id=1300001"
        ).fetchone()[0]
        == rented_read
    )


def test_current_listings_publish_and_point_the_site_at_the_newest(
    tmp_path, monkeypatch
):
    ticks = iter(
        datetime(2026, 10, 15, 6, tzinfo=UTC) + timedelta(minutes=i) for i in range(10)
    )

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return next(ticks)

    monkeypatch.setattr(gs, "datetime", Clock)
    root = tmp_path / "current"
    root.mkdir()
    c = make_collector(tmp_path / "archive", make_api(), active_only=True)
    report = c.collect(current_root=root)

    current = report["current_listings"]
    assert current["active_advertisements"] == 3
    assert current["candidates"] == 2 and current["failures"] == 1
    link = root / "api-test"
    assert (
        link.is_symlink()
        and link.resolve()
        == (
            tmp_path / "archive" / "current-listings" / "test" / "20261015T060000Z-run1"
        ).resolve()
    )
    (path,) = root.glob("*/details/snapshot/candidates.jsonl")
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert {r["crawl_provenance"]["requested_url"] for r in rows} == {
        rental(1300005),
        rental(1300007),
    }
    assert (link / "details" / "archive").resolve() == (tmp_path / "archive").resolve()
    from apartments.site import ad_dates

    bodies = ad_dates._Bodies(root)
    try:
        for r in rows:
            (sha,) = c.db.execute(
                "SELECT body_hash FROM observations WHERE id=?",
                (r["crawl_provenance"]["observation_id"],),
            ).fetchone()
            assert bodies.get(sha) is not None
    finally:
        bodies.close()
    failures = (link / "details" / "snapshot" / "failures.jsonl").read_text()
    assert "no single canonical unit" in failures

    for _ in range(2):
        c.current_listings(root)
    names = sorted(
        p.name for p in (tmp_path / "archive" / "current-listings" / "test").iterdir()
    )
    assert names == ["20261015T060100Z-run1", "20261015T060200Z-run1"]
    assert link.resolve().name == "20261015T060200Z-run1"

    link.unlink()
    link.mkdir()
    with pytest.raises(RuntimeError, match="not a symlink"):
        c.current_listings(root)
    assert (
        sorted(
            p.name
            for p in (tmp_path / "archive" / "current-listings" / "test").iterdir()
        )
        == names
    )
    api = make_api()
    blocked = make_collector(tmp_path / "blocked", api, active_only=True)
    with pytest.raises(RuntimeError, match="not a symlink"):
        blocked.collect(current_root=root)
    assert api.queries == []


def test_regions_share_an_archive_and_read_only_their_own_ads(tmp_path):
    api = make_api()
    # Unit 9d's latest ad, 1300012, is missing from the search, and ad 1300003 is in the
    # search with no record in the API.
    api.ads["1300011"] = record(
        1300011, "9d", "RENTED", 3100, 1, [1300012, 1300011], 1300012
    )
    api.ads["1300012"] = record(
        1300012, "9d", "ACTIVE", 3300, 1, [1300012, 1300011], 1300012
    )
    api.search += [(1300003, 3950, 1, "RENTED"), (1300011, 3100, 1, "RENTED")]
    api.areas = {
        1300001: 103,
        1300003: 103,
        1300005: 103,
        1300010: 103,
        1300011: 103,
        1300007: 104,
    }
    archive = tmp_path / "archive"
    plain = {"region": "plain", "areas": (103,), "follow_history": False}
    full = {"region": "full", "areas": (104,), "follow_history": True}

    # The plain region's run spends its three requests on the search and its ads.
    first = make_collector(archive, api, max_requests=3, **plain)
    assert first.collect()["invocation"]["stopped"] is not None
    assert reads(api) == {1300001, 1300003, 1300005, 1300010, 1300011}
    first.store.close()

    # A history region's run leaves the plain region's units, latest ads, histories, missing
    # ads and building 17504 to the plain region, though all of them are unread.
    api.queries.clear()
    second = make_collector(archive, api, **full)
    assert second.collect()["invocation"]["stopped"] is None
    assert second.generation == first.generation
    assert reads(api) == {1300007}
    assert reads(api, "buildingsByIds") == {17503}
    second.store.close()

    api.queries.clear()
    resumed = make_collector(archive, api, **plain)
    report = resumed.collect()
    assert resumed.run == first.run and report["invocation"]["stopped"] is None
    assert reads(api) == {1300003, 1300012}
    assert reads(api, "buildingsByIds") == {17504}
    assert not [k for k in report["write"] if "waiting" in k]
    resumed.store.close()

    # Each daily run re-reads its own region's live ads and keeps its own current listings.
    root = tmp_path / "current"
    root.mkdir()
    for region, live in ((full, {1300007}), (plain, {1300005, 1300010, 1300012})):
        api.queries.clear()
        daily = make_collector(archive, api, active_only=True, new_run=True, **region)
        daily.collect(current_root=root)
        assert reads(api) == live
        daily.store.close()
    links = {p.name: p.resolve() for p in root.iterdir()}
    assert {name: path.parent.name for name, path in links.items()} == {
        "api-full": "full",
        "api-plain": "plain",
    }
    assert all(path.is_dir() for path in links.values())


def test_a_daily_run_of_another_region_leaves_a_backfill_its_ads(tmp_path):
    api = make_api()
    # Unit 4a has an older ad, 1300004, missing from the search.
    api.ads["1300007"] = record(
        1300007, "4a", "ACTIVE", 2500, 0, [1300007, 1300004], 1300007
    )
    api.ads["1300004"] = record(
        1300004, "4a", "RENTED", 2400, 0, [1300007, 1300004], 1300007
    )
    archive, root = tmp_path / "archive", tmp_path / "current"
    root.mkdir()
    history = {"region": "history", "areas": (103,), "follow_history": True}

    # The backfill stops after its first ad read, before it follows the units' histories.
    first = make_collector(archive, api, max_requests=3, **history)
    assert first.collect(current_root=root)["invocation"]["stopped"] is not None
    first.store.close()

    # A daily run of a region over a parent area re-reads the backfill's ACTIVE ads.
    api.queries.clear()
    parent = make_collector(
        archive,
        api,
        region="parent",
        areas=(116,),
        active_only=True,
        follow_history=False,
    )
    assert (
        parent.collect(current_root=root)["current_listings"]["active_advertisements"]
        == 3
    )
    assert reads(api) == {1300005, 1300007, 1300010}
    parent.store.close()

    # The resumed backfill still follows the histories of units 12b and 4a, and its
    # capture holds the ACTIVE ads the daily run read after the backfill started.
    api.queries.clear()
    resumed = make_collector(archive, api, **history)
    report = resumed.collect(current_root=root)
    assert resumed.run == first.run and report["invocation"]["stopped"] is None
    assert reads(api) == {1300003, 1300004}
    assert report["current_listings"]["active_advertisements"] == 3
    assert {p.name for p in root.iterdir()} == {"api-history", "api-parent"}


def test_batches_fit_in_the_url(tmp_path, monkeypatch):
    c = make_collector(tmp_path / "archive", make_api())
    from collections import deque

    queue = deque(range(1_300_000, 1_300_600))
    job = c._take("ads", queue, gs.MAX_BATCH)
    assert len(job.items) == 500 and len(job.url) <= gs.MAX_URL and len(queue) == 100
    assert len(job.fields) == 5
    job = c._take("buildings", deque(str(i) for i in range(17000, 17300)), 250)
    assert len(job.items) == 250 and len(job.fields) == 5
    job = c._take(
        "count", deque([gs.FULL, *gs.children(gs.FULL)]), gs.COUNTS_PER_REQUEST
    )
    assert len(job.items) == 16

    limit = len(c._job("ads", list(range(1_300_000, 1_300_010))).url)
    monkeypatch.setattr(gs, "MAX_URL", limit)
    queue = deque(range(1_300_000, 1_300_600))
    job = c._take("ads", queue, gs.MAX_BATCH)
    assert 1 <= len(job.items) <= 10 and len(queue) == 600 - len(job.items)
    monkeypatch.setattr(gs, "MAX_URL", 10)
    with pytest.raises(ValueError):
        c._take("ads", deque([1_300_000]), 1)


def test_ad_batches_follow_response_size(tmp_path):
    c = make_collector(tmp_path / "archive", make_api())
    assert c._ad_batch() == 150
    with c.store._tx():
        c.db.execute(
            "INSERT INTO graphql_search_responses(kind, entries, bytes) VALUES('ads', 100, 600000)"
        )
    assert c._ad_batch() == 500
    with c.store._tx():
        c.db.execute(
            "INSERT INTO graphql_search_responses(kind, entries, bytes) VALUES('ads', 1, 90000000)"
        )
    assert c._ad_batch() == 3


def test_a_timed_out_read_makes_later_reads_smaller(tmp_path):
    from collections import deque

    c = make_collector(tmp_path / "archive", make_api())
    with c.store._tx():
        c.db.execute(
            "INSERT INTO graphql_search_responses(kind, entries, bytes) VALUES('ads', 100, 600000)"
        )
    assert c._ad_batch() == 500
    c.retry = deque()
    job = c._job("ads", list(range(1_300_000, 1_300_400)))
    other = gs.Reply(True, 200, b'{"data": null}', {}, 0.0, 1, 200)
    assert c._handle(job, other) is False
    assert c._ad_batch() == 500
    data = {f"a{i}": None for i in range(4)}
    error = {"message": "Your request has been timed out"}
    error["extensions"] = {"code": "GATEWAY_TIMEOUT", "service": "listing"}
    body = json.dumps({"data": data, "errors": [error]}).encode()
    timed_out = gs.Reply(True, 200, body, {}, 0.0, 1, 200)
    assert c._handle(job, timed_out) is False
    assert c._ad_batch() == 300
    assert [len(j.items) for j in c.retry] == [200, 200, 200, 200]
    for job in list(c.retry):
        c._handle(job, timed_out)
    assert c._ad_batch() == 300
    c._handle(c._job("ads", list(range(1_300_000, 1_300_500))), timed_out)
    assert c._ad_batch() == 300
    c._handle(c._job("ads", [1_300_000]), timed_out)
    assert c._ad_batch() == 300
    for size in (300, 225, 168, 126, 100, 100):
        c._handle(c._job("ads", list(range(1_300_000, 1_300_000 + size))), timed_out)
    assert c._ad_batch() == 100

    c = make_collector(tmp_path / "other", make_api())
    with c.store._tx():
        c.db.execute(
            "INSERT INTO graphql_search_responses(kind, entries, bytes) VALUES('ads', 100, 840000)"
        )
    assert c._ad_batch() == 357
    c.retry = deque()
    c._handle(c._job("ads", list(range(1_300_000, 1_300_357))), timed_out)
    assert c._ad_batch() == 267


def test_search_fields_and_bands():
    assert gs.search_field(
        "c0",
        [103, 104],
        (2001, 2500, 1),
        ids=True,
        direction="DESCENDING",
        active_only=True,
    ) == (
        "c0: searchRentals(input: {sorting: {attribute: LISTED_AT, direction: DESCENDING}, "
        "adStrategy: NONE, filters: {areas: [103, 104], price: {lowerBound: 2001, "
        "upperBound: 2500}, bedrooms: {lowerBound: 1, upperBound: 1}, rentalStatus: ACTIVE}, "
        "perPage: 1000, page: 1}) { totalCount edges { ... on OrganicRentalEdge { node { id } } } }"
    )
    assert gs.search_field("c1", [103], gs.FULL).endswith(
        "perPage: 1, page: 1}) { totalCount }"
    )
    bands = gs.children(gs.FULL)
    assert bands[0] == (0, 1500, -1) and bands[1] == (1501, 2000, -1)
    assert bands[-1] == (25001, 10**8, -1)
    assert gs.children((2001, 2500, -1)) == [(2001, 2250, -1), (2251, 2500, -1)]
    assert gs.children((2500, 2500, -1)) == [(2500, 2500, b) for b in range(8)]
    assert gs.children((2500, 2500, 3)) == []
