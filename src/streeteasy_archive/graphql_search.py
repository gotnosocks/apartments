"""Collect StreetEasy rental ads by area through the site's GraphQL API.

A page crawl spends a request on each ad page and on each unit page. This collector sends
plain GETs to api-v6.streeteasy.com, the API behind StreetEasy's own pages, through the
Oxylabs Realtime API, and reads hundreds of ads in a request
(data/probes/graphql-search-20261015/). A run over a region goes through these steps:

  1. Enumerate the region's ads with `searchRentals`. The search answers at most 1,000
     results for a query but gives a total count for any filter, so the collector counts
     the region in fixed price bands. It splits a band holding more than 1,000 ads in half
     by price, and it splits a single price into bedroom counts 0 to 7 and a band of 8 or
     more bedrooms. It splits a band of a single price and bedroom count holding more than
     1,000 ads into the region's areas. A band still above 1,000 in an area goes into map
     boxes: the collector starts from the four boxes around New York (root_boxes), halves
     each by latitude, halves each half by longitude, and goes on halving each box holding
     more than 1,000 ads (box_edges). Then it reads the IDs in each band sorted by listing
     date. Reads from both ends of that order miss some of the ads between them (17 of a
     band of 1,971 on Oct 15), so the collector splits down to 1,000 ads rather than
     reading a band from both ends. A request carries 25 counts, or up to 25 ID reads of
     4,000 ads between them, as aliased fields, as many as fit in the URL.
  2. Read the ads with `rentalsByListingIds`, up to 100 IDs in a field and five fields in a
     request, as many as fit in the URL and in an answer of about 3 MB. When the listing
     service answers every field of a read near the current size with GATEWAY_TIMEOUT,
     the collector cuts the most ads it puts in a request to three quarters of that read, no
     lower than 100, for the rest of the invocation. Each record is the `RentalListing`
     object of the ad's page. Besides the search hits, the collector reads the latest ad of
     each ad's unit and, in history regions, each ad of the unit's history at or above the
     collection policy's ID cutoff. Each round of reads can find new IDs, so it goes up to
     four rounds.
  3. Read each ad's building with `buildingsByIds`, 50 to a field, for its slug and its
     attributes.
  4. Write the records into the archive with no further requests, in the steps a page
     crawl follows for its pages (store.record and collection_policy.annotate). Then
     granular_export and the collection audit read the archive as they read a crawl's.
     The collector records each building at its page's URL, then each unit from its latest
     ad, then the ads:
       - The unit page shows the unit's latest ad, so that ad's record stands in for the
         unit page. collection_policy.reuse_unit_capture then retires the ad's own route
         as superseded by the unit.
       - Each older ad goes in under /rental/ID with its own record.
       - An ad with no record from the API gets a gap observation.
     An ad waits until its unit's capture is written, and the policy excludes ads with no
     unit membership, as in a crawl. The collector commits these writes 500 rows at a
     time. A stop loses the open batch, and the next run writes its rows again.

Ad bodies come from apartments.graphql_listing.listing_body and building bodies from
building_body. The raw response of each request also goes into the archive's bodies, and
the `graphql_search_*` tables keep each run's counts, hits, reads and calls.

Every region writes into a single archive, ARCHIVE, under one collection generation, and
each run is a row of graphql_search_runs carrying its region. Every ad a run reads, with a
record or without one, joins the run's region in graphql_search_members, and an ad stays in
each region whose runs read it, as an ad in a child area of two regions' areas would. When
a run picks the units, histories and buildings to read, it starts from its region's ads.
The write step records whatever any run has read and left unwritten, since it sends no
requests.

With --active-only the search keeps ACTIVE ads only. A top-up run in this mode reads the
region's current ads and re-reads the region's ads with a status other than RENTED,
NO_LONGER_AVAILABLE or DELISTED. Those ads get a new observation on each read, and the
snapshot table gains a row only when a record changes, since an unchanged record gives the
same body bytes.

The collector sends at most --rate requests a minute, never more than 64, and stops at
--max-requests. It stops earlier on an Oxylabs credential or billing refusal, a StreetEasy
401, 403 or 429, a challenge page, or six failed requests in a row. The client sends a
request up to three times when the connection fails, Oxylabs answers 429 or 5xx, or its
result comes back with no status or content, and counts it as failed after the third. It
waits 5 and then 10 seconds between tries, or as long as a 429 or 5xx asks, up to 120.
After a failed request for several items, the collector retries each half, and a single
item gets three tries. Each step reads its progress from the tables, so the same command
resumes an unfinished run. --reopen resumes the region's latest run even after it finished,
so a newer collector can count and read the bands from its finer split. --new-run starts a
fresh run.

Limits:
  - About 12% of NoMad's ads have no `slug` in their record. With no canonical unit page,
    the policy excludes them.
  - A unit's capture holds the record of its latest ad, as the unit page does.
  - Buildings are read once and never refreshed, and their records have no `pageTitle`.
  - building_field_recovery and the model audits read page captures only.
  - The collector writes no building inventory rows.
  - Some ads match the price filter of more than one band, and an ad on the edge between
    two boxes can match both, so a band's halves can hold more ads between them than the
    band, and most of the report's gaps are negative.
  - An ad with no map position, or with a position outside the four boxes around New York,
    falls outside every box. The collector misses it, and the report counts it in the gap
    of the band where the box split starts.
  - When more than 1,000 ads of a band share a box a microdegree across, the collector
    reads the box from both ends of the listing-date order and misses some of the ads
    between them. The report lists such bands as truncated.
  - When the API has no record for a unit's latest ad, the policy excludes the unit's other
    ads for a missing unit membership.
"""

from __future__ import annotations

import argparse
from collections import Counter, deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
import fcntl
import hashlib
from itertools import islice
import json
from pathlib import Path
import sys
import threading
import time
import urllib.parse

import requests

from apartments.graphql_listing import (
    SOURCE,
    building_body,
    building_document,
    canonical_link,
    listing_body,
)

from . import collection_policy as policy
from .capture import redact
from .crawler import is_challenge
from .extract import VERSION, canonical_url, kind_for
from .graphql_inventory import API_HOST, MAX_URL, build_payload
from .listing_identity import listing_key
from .oxylabs import (
    API_URL,
    MAX_BODY,
    RetryableOxylabsError,
    _credentials,
    _result_item,
)
from .store import ArchiveStore

SEARCH_VERSION = "graphql-search-v1"
# The collection policy's cutoff for new archives: ads below it mostly lack a canonical unit.
MIN_LISTING_ID = 1_210_000
PRICE = 1.14 / 1000  # dollars per Oxylabs request
CAP = 1000  # searchRentals answers offset + perPage <= 1,000
COUNTS_PER_REQUEST = 25
SLICES_PER_REQUEST = 25
# On Oct 15 a request with 20 ID reads, 3,838 ads between them, came back whole in
# about 100 KB.
SLICE_IDS_PER_REQUEST = 4000
IDS_PER_FIELD = 100  # rentalsByListingIds answers at most 100 IDs in a field
FIELDS_PER_REQUEST = 5
MAX_BATCH = IDS_PER_FIELD * FIELDS_PER_REQUEST
BUILDINGS_PER_FIELD = 50
BUILDINGS_PER_REQUEST = 250
WRITE_BATCH = 500  # rows the write phase commits at once
# On Oct 15, with four requests running at once, the listing service answered 148 of 152
# Manhattan reads of about 500 ads (about 4 MB) with GATEWAY_TIMEOUT, against 1 of 299
# smaller reads. Probe reads of 375 ads (about 3 MB) all came back.
TARGET_BYTES = 3_000_000
FIRST_BYTES_PER_AD = 20_000
EDGES = [0, 1500, 2000, 2500, 3000, 3500, 4000, 4500, 5000, 6000, 7000, 8000, 10000]
EDGES += [15000, 25000, 10**8]
NO_PRICE = ANY_BEDS = ANY_AREA = ANY_BOX = -1
FULL = (NO_PRICE, NO_PRICE, ANY_BEDS, ANY_AREA, ANY_BOX)
# The whole map as south, north, west and east edges in microdegrees: box 1 of the box split.
WORLD = (-90_000_000, 90_000_000, -180_000_000, 180_000_000)
# New York City's five boroughs, in the same order and units.
NEW_YORK = (40_477_400, 40_917_600, -74_259_100, -73_700_400)
# An area band's box split starts this many halvings below box 1 (root_boxes).
ROOT_DEPTH = 18
# The bedroom split's last band holds this many bedrooms or more.
TOP_BEDS = 8
FINAL = frozenset({"RENTED", "NO_LONGER_AVAILABLE", "DELISTED"})
FAILURES_IN_A_ROW = 6
MAX_RATE = 64
AD_ROUNDS = 4
TRIES = {"count": 3, "slice": 3, "ads": 3, "buildings": 2}
ARCHIVE = Path("/data1/apartments/archive/crawls/api")

# Region: (StreetEasy area IDs, whether to read each unit's older ads).
REGIONS = {
    "manhattan-below-59th": (
        [103, 104, 114, 105, 107, 166, 108, 109, 111, 110, 112, 118, 162, 120, 122, 130]
        + [131, 132, 134, 133, 121],
        True,
    ),
    "manhattan-59th-110th": ([135, 139, 155], True),
    "brooklyn-prospect-park": (
        [319, 326, 320, 321, 322, 306, 305, 307, 308, 303, 304, 364, 318, 328],
        True,
    ),
    "brooklyn-north-crown-heights": ([301, 302, 373, 313, 310, 325], True),
    # Areas the page crawls collected. The weekly top-up keeps their current ads fresh. Like
    # the other regions, this region reads its units' older ads, since the area search leaves
    # some out.
    "manhattan-page-crawl-areas": (
        [115, 163, 157, 116, 158, 113, 159, 117, 106, 124, 146, 152],
        True,
    ),
}

# The fields of an ad page's listing object that the API gives (frag2.graphql in
# data/probes/graphql-rental-20261015/).
FRAGMENT = " ".join(
    """
fragment R on RentalListing { __typename availableAt buildingId createdAt daysOnMarket
description id interestingChangeAt isPremiumHdpEnabled latestListing { id pricing { price }
status } legacy { license { address { city displayUnit state street zipCode } businessName
licenseType } sourceGroupLabel } listingSource { sourceListingId sourceType } media {
floorPlans { key } photos { key } tour3dUrl videos { id imageUrl provider url } } mlsNumber
offMarketAt onMarketAt recentListingsPriceStats { bedroomCount rentalPriceStats { maxPrice
medianPrice minPrice numListings } salePriceStats { maxPrice medianPrice minPrice numListings
} } signatureMediaGallery { __typename } pricing { additionalFees { __typename } dueUpFront
furnishedRent interestingPriceDelta leaseTermMonths monthlyFees { calculation {
calculationType feeQuantifier maxQuantifier } refundability { type } requirement schedule {
occurrenceType timing } typeLabel } monthsFree moveInFees { calculation { calculationType
feeQuantifier maxQuantifier } refundability { type } requirement schedule { occurrenceType
timing } typeLabel } netEffectiveRent price priceChanges { changedAt price } priceDelta
rentedPrice securityDeposit totalMonthlyPrice } propertyDetails { address { city displayUnit
state street zipCode } amenities { doormanTypes list parkingTypes sharedOutdoorSpaceTypes
storageSpaceTypes } bedroomCount features { fireplaceTypes list privateOutdoorSpaceTypes views
} fullBathroomCount halfBathroomCount livingAreaSize lotAreaSize roomCount } propertyHistory {
__typename listingId offMarketAt photos { key } rentalEventsOfInterest { __typename date price
... on RentalStatusChangeOfInterest { status } ... on PriceChangeOfInterest {
pricePercentChange } } sourceGroupLabel } propertyId slug status statusChanges { changedAt
status } upcomingOpenHouses { appointmentOnly endTime id startTime } updatedAt urlPath }
""".split()
)
BUILDING_FRAGMENT = (
    "fragment B on Building { id slug name type status yearBuilt floorCount "
    "residentialUnitCount geoCenter { latitude longitude } address { street city state "
    "zipCode } se { areaId } nyc { communityDistrict buildingClass "
    "buildingClassDescription } amenities { list doormanTypes parkingTypes "
    "sharedOutdoorSpaceTypes storageSpaceTypes } policies { list } area { id name slug } "
    "description isGreen isLandLease isWaterfront complexId complex { id name slug } "
    "hasOwnerData interestingChangeAt additionalDetails { leasingStartDate salesStartDate } "
    "heroImage { key } media { photos { key } videos { url imageUrl id provider } "
    "tour3dUrl floorPlans { key } } rentalInventorySummary { availableListingDigests { id } } "
    "saleInventorySummary { availableListingDigests { id } } nearby { transitStations { "
    "name routes distance } pointsOfInterest { distance name type } } }"
)

# The ads of the run's region, as a condition on graphql_search_ads a.
MINE = (
    "EXISTS (SELECT 1 FROM graphql_search_members m WHERE m.generation=a.generation "
    "AND m.region=:region AND m.listing_id=a.listing_id)"
)

# The columns of the band tables, keyed by a band's price range, bedroom count, area and box.
BAND = "lo,hi,beds,area,box"
BAND_TABLES = {
    "graphql_search_counts": "run INTEGER, lo INTEGER, hi INTEGER, beds INTEGER, "
    f"area INTEGER, box INTEGER, total INTEGER, PRIMARY KEY(run,{BAND})",
    "graphql_search_slices": "run INTEGER, lo INTEGER, hi INTEGER, beds INTEGER, "
    "area INTEGER, box INTEGER, direction TEXT, total INTEGER, ids INTEGER, "
    f"PRIMARY KEY(run,{BAND},direction)",
}
# The columns added to the band tables since their first version, with the value of the
# old rows, which covered every area and the whole map.
ADDED_BAND_COLUMNS = {"area": ANY_AREA, "box": ANY_BOX}

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS graphql_search_runs(id INTEGER PRIMARY KEY, generation INTEGER,
    region TEXT, areas TEXT, active_only INTEGER, follow_history INTEGER, started REAL,
    finished REAL, report TEXT);
CREATE TABLE IF NOT EXISTS graphql_search_counts({BAND_TABLES["graphql_search_counts"]});
CREATE TABLE IF NOT EXISTS graphql_search_slices({BAND_TABLES["graphql_search_slices"]});
CREATE TABLE IF NOT EXISTS graphql_search_hits(run INTEGER, listing_id INTEGER,
    PRIMARY KEY(run,listing_id));
CREATE TABLE IF NOT EXISTS graphql_search_responses(id INTEGER PRIMARY KEY AUTOINCREMENT,
    sha256 TEXT, run INTEGER, query_sha256 TEXT, kind TEXT, entries INTEGER, bytes INTEGER,
    fetched REAL, capture TEXT);
CREATE TABLE IF NOT EXISTS graphql_search_ads(generation INTEGER, listing_id INTEGER,
    run INTEGER, response_id INTEGER, building_id TEXT, latest_id INTEGER, status TEXT,
    history TEXT, record_sha256 TEXT, read REAL, unit_written INTEGER, written_run INTEGER,
    PRIMARY KEY(generation,listing_id));
CREATE INDEX IF NOT EXISTS graphql_search_ads_latest ON graphql_search_ads(generation,latest_id);
CREATE TABLE IF NOT EXISTS graphql_search_members(generation INTEGER, region TEXT,
    listing_id INTEGER, PRIMARY KEY(generation,region,listing_id));
CREATE TABLE IF NOT EXISTS graphql_search_buildings(generation INTEGER, building_id TEXT,
    run INTEGER, response_id INTEGER, slug TEXT, read REAL, written_run INTEGER,
    PRIMARY KEY(generation,building_id));
CREATE TABLE IF NOT EXISTS graphql_search_calls(run INTEGER, kind TEXT, started REAL,
    seconds REAL, api_status INTEGER, target_status INTEGER, bytes INTEGER,
    url_length INTEGER, attempt INTEGER, error TEXT);
"""


def search_field(
    alias, areas, node, *, ids=False, direction="ASCENDING", active_only=False
):
    """An aliased `searchRentals` field for a band: its total, and its IDs when `ids`."""
    lo, hi, beds, area, box = node
    if area != ANY_AREA:
        areas = [area]
    filters = [f"areas: [{', '.join(map(str, areas))}]"]
    if lo != NO_PRICE:
        filters.append(f"price: {{lowerBound: {lo}, upperBound: {hi}}}")
    if beds == TOP_BEDS:
        filters.append(f"bedrooms: {{lowerBound: {beds}}}")
    elif beds != ANY_BEDS:
        filters.append(f"bedrooms: {{lowerBound: {beds}, upperBound: {beds}}}")
    if box != ANY_BOX:
        south, north, west, east = (f"{v / 1e6:.6f}" for v in box_edges(box))
        filters.append(
            f"boundingBox: {{topLeft: {{latitude: {north}, longitude: {west}}}, "
            f"bottomRight: {{latitude: {south}, longitude: {east}}}}}"
        )
    if active_only:
        filters.append("rentalStatus: ACTIVE")
    selection = (
        "totalCount edges { ... on OrganicRentalEdge { node { id } } }"
        if ids
        else "totalCount"
    )
    return (
        f"{alias}: searchRentals(input: {{sorting: {{attribute: LISTED_AT, direction: "
        f"{direction}}}, adStrategy: NONE, filters: {{{', '.join(filters)}}}, "
        f"perPage: {CAP if ids else 1}, page: 1}}) {{ {selection} }}"
    )


def box_edges(box):
    """The south, north, west and east edges of a box of the box split, in microdegrees.

    Box 1 is the whole map, and box k splits into boxes 2k and 2k + 1. A box at an even
    depth (box 1 at depth 0, boxes 2 and 3 at depth 1) splits by latitude into its southern
    and northern halves, and a box at an odd depth by longitude into its western and eastern
    halves. The halves share the edge between them.
    """
    south, north, west, east = WORLD
    for depth, half in enumerate(bin(box)[3:]):
        if depth % 2 == 0:
            mid = (south + north) // 2
            south, north = (south, mid) if half == "0" else (mid, north)
        else:
            mid = (west + east) // 2
            west, east = (west, mid) if half == "0" else (mid, east)
    return south, north, west, east


def root_boxes():
    """The boxes ROOT_DEPTH halvings below box 1 overlapping New York.

    At depth 18 a box spans 0.35 degrees of latitude and 0.70 of longitude, and four such
    boxes cover the city. In the backfill runs, 3,146 of run 3's 4,504 box counts went to
    the 18 halvings from the whole map down to these boxes, and every ad lay inside them.
    The report counts an ad placed outside them in the gap of its area band.
    """
    boxes = [1]
    for _ in range(ROOT_DEPTH):
        boxes = [
            k
            for box in boxes
            for k in (2 * box, 2 * box + 1)
            if _overlaps(box_edges(k), NEW_YORK)
        ]
    return boxes


def _overlaps(a, b):
    return a[0] < b[1] and b[0] < a[1] and a[2] < b[3] and b[2] < a[3]


def children(node, areas):
    """The bands a band splits into: price bands, price halves, bedroom counts, areas, boxes.

    A band of a single price and bedroom count splits into the region's areas. An area band,
    or such a band in a region with a single area, splits into ROOTS, the boxes around New
    York, and a box band into the halves of its box, down to a box a microdegree across.
    """
    lo, hi, beds, area, box = node
    if node == FULL:
        return [
            (
                EDGES[i] if i == 0 else EDGES[i] + 1,
                EDGES[i + 1],
                ANY_BEDS,
                ANY_AREA,
                ANY_BOX,
            )
            for i in range(len(EDGES) - 1)
        ]
    if hi > lo:
        mid = (lo + hi) // 2
        return [(lo, mid, beds, area, box), (mid + 1, hi, beds, area, box)]
    if beds == ANY_BEDS:
        return [(lo, hi, b, area, box) for b in range(TOP_BEDS + 1)]
    if box == ANY_BOX:
        if area == ANY_AREA and len(areas) > 1:
            return [(lo, hi, beds, a, box) for a in areas]
        return [(lo, hi, beds, area, b) for b in ROOTS]
    south, north, west, east = box_edges(box)
    span = north - south if (box.bit_length() - 1) % 2 == 0 else east - west
    if span < 2:
        return []
    return [(lo, hi, beds, area, 2 * box), (lo, hi, beds, area, 2 * box + 1)]


ROOTS = root_boxes()


def history_links(record):
    """A link to each ad in the record's property history."""
    history = record.get("propertyHistory") if isinstance(record, dict) else None
    ids = [
        str(episode.get("listingId"))
        for episode in history or []
        if isinstance(episode, dict) and str(episode.get("listingId", "")).isdigit()
    ]
    return [
        {"url": f"https://streeteasy.com/rental/{ad}", "kind": "listing"}
        for ad in dict.fromkeys(ids)
    ]


def _unit_route(url):
    """The URL when it is a unit page in the frontier's own spelling, else None."""
    from apartments.unit_canonical import unit_page

    page = unit_page(url) if url else None
    if not page or canonical_url(page) != page or listing_key(page):
        return None
    return page


def _sha256(data):
    return hashlib.sha256(data.encode() if isinstance(data, str) else data).hexdigest()


def _timed_out(doc):
    """True when api-v6 reports that a service behind it ran out of time on the request."""
    errors = doc.get("errors") if isinstance(doc, dict) else None
    return any(
        isinstance(e, dict)
        and isinstance(e.get("extensions"), dict)
        and e["extensions"].get("code") == "GATEWAY_TIMEOUT"
        for e in (errors if isinstance(errors, list) else [])
    )


def _int_id(value):
    return int(value) if str(value or "").isdigit() else None


def _iso(seconds):
    return datetime.fromtimestamp(seconds, UTC).isoformat()


class Stop(RuntimeError):
    """A refusal, a block or repeated failures: the run stops and writes what it read."""


class Budget(RuntimeError):
    """The invocation used up --max-requests."""


@dataclass
class Reply:
    ok: bool
    status: int | None
    body: bytes
    provider: dict
    fetched: float
    attempts: int
    api_status: int | None = None
    error: str | None = None


@dataclass
class Job:
    kind: str
    items: list
    fields: dict
    url: str


def _retry_after(value, default):
    try:
        return min(120.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return default


class Client:
    """Oxylabs Realtime GETs at a fixed rate, counted against a request budget.

    Every POST to Oxylabs counts, retries included. The client spaces POSTs 60/rate
    seconds apart across all threads and raises Budget once `max_requests` have gone out.
    """

    def __init__(
        self,
        max_requests,
        rate=30,
        *,
        post=requests.post,
        credentials=_credentials,
        clock=time.monotonic,
        sleep=time.sleep,
    ):
        if not 0 < rate <= MAX_RATE:
            raise ValueError(f"rate must be above 0 and at most {MAX_RATE} a minute")
        self.max_requests, self.rate = max_requests, rate
        self.post, self.clock, self.sleep = post, clock, sleep
        self.auth = credentials()
        self.lock = threading.Lock()
        self.calls = 0
        self.next_at = None

    def _slot(self):
        with self.lock:
            if self.calls >= self.max_requests:
                raise Budget(f"spent the budget of {self.max_requests} requests")
            self.calls += 1
            now = self.clock()
            start = now if self.next_at is None else max(now, self.next_at)
            self.next_at = start + 60 / self.rate
        if start > now:
            self.sleep(start - now)

    def get(self, url):
        payload = build_payload(url)
        started = time.time()
        error = api_status = None
        for attempt in range(3):
            self._slot()
            try:
                response = self.post(
                    API_URL,
                    json=payload,
                    auth=self.auth,
                    timeout=180,
                    allow_redirects=False,
                )
            except requests.RequestException as exc:
                error = "Oxylabs request failed (" + type(exc).__name__ + ")"
                api_status = None
                if attempt < 2:
                    self.sleep(5 * 2**attempt)
                continue
            api_status = response.status_code
            if response.status_code in (401, 402, 403):
                raise Stop(f"Oxylabs refused the request (HTTP {response.status_code})")
            if response.status_code == 429 or response.status_code >= 500:
                error = f"Oxylabs HTTP {response.status_code}"
                if attempt < 2:
                    wait_for = _retry_after(
                        response.headers.get("Retry-After"), 5 * 2**attempt
                    )
                    self.sleep(wait_for)
                continue
            try:
                return self._reply(url, payload, response, started, attempt + 1)
            except RetryableOxylabsError as exc:
                # On Oct 15 bursts of Oxylabs results with no status or content stopped
                # a run twice, and the same requests sent again came back whole.
                error = str(exc)
                if attempt < 2:
                    self.sleep(5 * 2**attempt)
        return Reply(False, None, b"", {}, time.time(), 3, api_status, error)

    def _reply(self, url, payload, response, started, attempts):
        fetched = time.time()
        provider = {
            "provider": "oxylabs",
            "api_endpoint": API_URL,
            "api_status": response.status_code,
            "started_at": started,
            "completed_at": fetched,
            "source": payload["source"],
            "render": None,
            "target_url_sha256": _sha256(url),
            "browser_instructions": [],
            "api_headers": {
                k: v
                for k, v in response.headers.items()
                if k.lower().startswith("x-ratelimit-")
                or k.lower() == "x-oxylabs-job-id"
            },
            "submission_attempts": attempts,
        }

        def failed(error, status=None):
            return Reply(
                False,
                status,
                b"",
                redact(provider),
                fetched,
                attempts,
                response.status_code,
                error,
            )

        if response.status_code != 200:
            return failed(f"Oxylabs HTTP {response.status_code}")
        try:
            results, _, status, content = _result_item(response.json())
        except (ValueError, TypeError):
            return failed("Oxylabs returned invalid JSON")
        provider["results"] = [
            {
                **{k: v for k, v in item.items() if k not in ("content", "url")},
                "url_sha256": _sha256(url),
            }
            for item in results
        ]
        body = content.encode("utf-8") if isinstance(content, str) else content
        if len(body) > MAX_BODY:
            return failed("Oxylabs response exceeds 32 MiB", status)
        if status in (401, 403, 429):
            raise Stop(f"StreetEasy answered HTTP {status}")
        if body.lstrip()[:1] not in (b"{", b"[") and is_challenge(body):
            raise Stop("StreetEasy answered with a challenge page")
        if status != 200:
            return failed(f"StreetEasy HTTP {status}", status)
        return Reply(True, status, body, redact(provider), fetched, attempts, 200)


class Collector:
    """A run of the collector over a region's areas, in the archive every region shares."""

    def __init__(
        self,
        store,
        client,
        region,
        areas,
        *,
        follow_history=True,
        active_only=False,
        new_run=False,
        reopen=False,
        workers=4,
    ):
        self.store, self.db, self.client = store, store.db, client
        self.region, self.areas = region, list(areas)
        self.follow_history, self.active_only = follow_history, active_only
        self.workers = workers
        self.ad_ceiling = MAX_BATCH
        self.db.executescript(SCHEMA)
        self._add_band_columns()
        self.generation = store.current_generation() or store.new_generation(
            "graphql-search"
        )
        if not policy.enabled(store, self.generation):
            policy.setup(store, self.generation, min_listing_id=MIN_LISTING_ID)
        self.cutoff = policy.min_listing_id(store, self.generation)
        self.invoked = time.time()
        areas_json = json.dumps(self.areas)
        row = self.db.execute(
            f"""SELECT id, started, finished FROM graphql_search_runs WHERE generation=?
            AND region=?
            AND areas=? AND active_only=? {"" if reopen else "AND finished IS NULL"}
            ORDER BY id DESC LIMIT 1""",
            (self.generation, region, areas_json, int(active_only)),
        ).fetchone()
        with store._tx():
            # In an archive from before graphql_search_members, each ad joins the region of
            # the run that read it last.
            if not self.db.execute("SELECT 1 FROM graphql_search_members").fetchone():
                self.db.execute(
                    """INSERT OR IGNORE INTO graphql_search_members
                    SELECT a.generation, r.region, a.listing_id FROM graphql_search_ads a
                    JOIN graphql_search_runs r ON r.id=a.run"""
                )
            if row and not new_run:
                self.run, self.started = row["id"], row["started"]
                if row["finished"] is not None:
                    # A reopened run stays unfinished until this invocation finishes it.
                    self.db.execute(
                        "UPDATE graphql_search_runs SET finished=NULL WHERE id=?",
                        (self.run,),
                    )
            else:
                self.started = self.invoked
                self.run = self.db.execute(
                    """INSERT INTO graphql_search_runs(generation,region,areas,active_only,
                    follow_history,started) VALUES(?,?,?,?,?,?)""",
                    (
                        self.generation,
                        region,
                        areas_json,
                        int(active_only),
                        int(follow_history),
                        self.started,
                    ),
                ).lastrowid
            # Give unanswered counts and slices another try in this invocation.
            for table in ("graphql_search_counts", "graphql_search_slices"):
                self.db.execute(
                    f"DELETE FROM {table} WHERE run=? AND total IS NULL", (self.run,)
                )
        self.tries = Counter()
        self.failed_in_a_row = 0
        self.retry = deque()
        self._cached = (None, None, {})

    def _add_band_columns(self):
        """Rebuild band tables from before the area or box split, giving old bands each
        column's value for every area or the whole map."""
        with self.store._tx():
            for table, columns in BAND_TABLES.items():
                old = [r[1] for r in self.db.execute(f"PRAGMA table_info({table})")]
                added = {c: v for c, v in ADDED_BAND_COLUMNS.items() if c not in old}
                if not added:
                    continue
                self.db.execute(f"ALTER TABLE {table} RENAME TO {table}_old")
                self.db.execute(f"CREATE TABLE {table}({columns})")
                self.db.execute(
                    f"""INSERT INTO {table}({", ".join([*old, *added])})
                    SELECT {", ".join([*old, *map(str, added.values())])} FROM {table}_old"""
                )
                self.db.execute(f"DROP TABLE {table}_old")

    # Requests

    def _job(self, kind, items):
        fields, parts = {}, []
        if kind in ("count", "slice"):
            for i, item in enumerate(items):
                alias = f"{kind[0]}{i}"
                fields[alias] = [item]
                node, direction = (item, "ASCENDING") if kind == "count" else item
                parts.append(
                    search_field(
                        alias,
                        self.areas,
                        node,
                        ids=kind == "slice",
                        direction=direction,
                        active_only=self.active_only,
                    )
                )
            query = "query AreaSearch { " + " ".join(parts) + " }"
        else:
            per, root, prefix, spread, name, fragment = (
                (
                    IDS_PER_FIELD,
                    "rentalsByListingIds",
                    "a",
                    "R",
                    "ArchiveRentals",
                    FRAGMENT,
                )
                if kind == "ads"
                else (
                    BUILDINGS_PER_FIELD,
                    "buildingsByIds",
                    "b",
                    "B",
                    "ArchiveBuildings",
                    BUILDING_FRAGMENT,
                )
            )
            for n, start in enumerate(range(0, len(items), per)):
                chunk = items[start : start + per]
                fields[f"{prefix}{n}"] = chunk
                ids = " ".join(map(str, chunk))
                parts.append(f"{prefix}{n}: {root}(ids: [{ids}]) {{ ...{spread} }}")
            query = f"query {name} {{ " + " ".join(parts) + " } " + fragment
        url = API_HOST + "?" + urllib.parse.urlencode({"query": query})
        return Job(kind, list(items), fields, url)

    def _take(self, kind, queue, limit, size=None):
        """The next job from the queue, as large as `limit` and the URL length allow.

        With `size`, the ads an item's read can give, the job holds a single item or items
        of SLICE_IDS_PER_REQUEST ads or fewer between them.
        """
        n = min(limit, len(queue))
        if size is not None:
            ads = 0
            for i, item in enumerate(islice(queue, n)):
                ads += size(item)
                if i and ads > SLICE_IDS_PER_REQUEST:
                    n = i
                    break
        while True:
            job = self._job(kind, list(islice(queue, n)))
            if len(job.url) <= MAX_URL:
                break
            if n == 1:
                raise ValueError(f"a single {kind} item does not fit in a URL")
            n = min(n - 1, int(n * 0.9))
        for _ in range(n):
            queue.popleft()
        return job

    def _run(self, kind, items, limit, size=None):
        queue = deque(items)
        self.retry = deque()

        def next_job():
            if self.retry:
                return self.retry.popleft()
            if queue:
                n = limit() if callable(limit) else limit
                return self._take(kind, queue, n, size)
            return None

        self._drain(next_job)

    def _drain(self, next_job):
        stop = None
        running = {}
        with ThreadPoolExecutor(self.workers) as pool:
            while True:
                while stop is None and len(running) < self.workers:
                    job = next_job()
                    if job is None:
                        break
                    running[pool.submit(self.client.get, job.url)] = (job, time.time())
                if not running:
                    break
                done, _ = wait(running, return_when=FIRST_COMPLETED)
                for future in done:
                    job, started = running.pop(future)
                    try:
                        reply = future.result()
                    except (Stop, Budget) as exc:
                        stop = stop or exc
                        continue
                    answered = self._handle(job, reply)
                    self._log_call(job, reply, started)
                    self.failed_in_a_row = 0 if answered else self.failed_in_a_row + 1
                    if self.failed_in_a_row >= FAILURES_IN_A_ROW and stop is None:
                        stop = Stop(f"{FAILURES_IN_A_ROW} requests in a row failed")
        if stop is not None:
            raise stop

    def _log_call(self, job, reply, started):
        with self.store._tx():
            self.db.execute(
                "INSERT INTO graphql_search_calls VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    self.run,
                    job.kind,
                    started,
                    time.time() - started,
                    reply.api_status,
                    reply.status,
                    len(reply.body),
                    len(job.url),
                    reply.attempts,
                    reply.error,
                ),
            )

    def _retry(self, kind, items):
        """Retry failed items: each half of a group, or a single item up to its tries."""
        if len(items) > 1:
            half = len(items) // 2
            self.retry.append(self._job(kind, items[:half]))
            self.retry.append(self._job(kind, items[half:]))
            return
        (item,) = items
        self.tries[kind, item] += 1
        if self.tries[kind, item] < TRIES[kind]:
            self.retry.append(self._job(kind, [item]))
            return
        with self.store._tx():
            if kind == "count":
                self.db.execute(
                    f"""INSERT OR REPLACE INTO graphql_search_counts(run,{BAND},total)
                    VALUES(?,?,?,?,?,?,NULL)""",
                    (self.run, *item),
                )
            elif kind == "slice":
                node, direction = item
                self.db.execute(
                    f"""INSERT OR REPLACE INTO graphql_search_slices(run,{BAND},direction,
                    total,ids) VALUES(?,?,?,?,?,?,?,NULL,NULL)""",
                    (self.run, *node, direction),
                )
            elif kind == "ads":
                self._save_missing_ad(item, time.time())
            else:
                self._save_missing_building(item, time.time())

    def _handle(self, job, reply):
        """Save what the reply answered and retry the rest. False when it answered nothing."""
        doc = None
        if reply.ok:
            try:
                doc = json.loads(reply.body)
            except ValueError:
                doc = None
        data = doc.get("data") if isinstance(doc, dict) else None
        data = data if isinstance(data, dict) else {}
        shape = dict if job.kind in ("count", "slice") else list
        if not any(isinstance(data.get(alias), shape) for alias in job.fields):
            # A retry half of a read at the current size falls below three quarters of it,
            # and the ceiling stays put when the half times out.
            if job.kind == "ads" and _timed_out(doc):
                if len(job.items) > self._ad_batch() * 3 // 4:
                    cut = max(IDS_PER_FIELD, len(job.items) * 3 // 4)
                    self.ad_ceiling = min(self.ad_ceiling, cut)
            self._retry(job.kind, job.items)
            return False
        failed = getattr(self, "_save_" + job.kind)(job, data, reply)
        if failed:
            self._retry(job.kind, failed)
        return True

    def _save_count(self, job, data, reply):
        failed = []
        with self.store._tx():
            for alias, items in job.fields.items():
                value = data.get(alias)
                total = value.get("totalCount") if isinstance(value, dict) else None
                if not isinstance(total, int) or isinstance(total, bool):
                    failed.extend(items)
                    continue
                self.db.execute(
                    f"""INSERT OR REPLACE INTO graphql_search_counts(run,{BAND},total)
                    VALUES(?,?,?,?,?,?,?)""",
                    (self.run, *items[0], total),
                )
        return failed

    def _save_slice(self, job, data, reply):
        failed = []
        with self.store._tx():
            for alias, items in job.fields.items():
                value = data.get(alias)
                total = value.get("totalCount") if isinstance(value, dict) else None
                edges = value.get("edges") if isinstance(value, dict) else None
                if not isinstance(total, int) or not isinstance(edges, list):
                    failed.extend(items)
                    continue
                ids = {
                    int(edge["node"]["id"])
                    for edge in edges
                    if isinstance(edge, dict)
                    and isinstance(edge.get("node"), dict)
                    and _int_id(edge["node"].get("id")) is not None
                }
                self.db.executemany(
                    "INSERT OR IGNORE INTO graphql_search_hits VALUES(?,?)",
                    [(self.run, i) for i in ids],
                )
                node, direction = items[0]
                self.db.execute(
                    f"""INSERT OR REPLACE INTO graphql_search_slices(run,{BAND},direction,
                    total,ids) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (self.run, *node, direction, total, len(ids)),
                )
        return failed

    def _response(self, job, reply, entries):
        """Keep the reply's body and query, and add its row; the caller holds the transaction."""
        return self.db.execute(
            """INSERT INTO graphql_search_responses(sha256,run,query_sha256,kind,entries,bytes,
            fetched,capture) VALUES(?,?,?,?,?,?,?,?)""",
            (
                _sha256(reply.body),
                self.run,
                _sha256(job.url),
                job.kind,
                entries,
                len(reply.body),
                reply.fetched,
                json.dumps(reply.provider, sort_keys=True),
            ),
        ).lastrowid

    def _split(self, job, data):
        """The records by ID, the IDs the answer left out and the items of failed fields."""
        records, missing, failed = {}, [], []
        for alias, items in job.fields.items():
            value = data.get(alias)
            if not isinstance(value, list):
                failed.extend(items)
                continue
            got = {
                str(r["id"]): r
                for r in value
                if isinstance(r, dict) and r.get("id") is not None
            }
            for item in items:
                if str(item) in got:
                    records[item] = got[str(item)]
                else:
                    missing.append(item)
        return records, missing, failed

    def _save_ads(self, job, data, reply):
        records, missing, failed = self._split(job, data)
        self.store.put_body(reply.body)
        self.store.put_body(job.url.encode())
        with self.store._tx():
            response_id = self._response(job, reply, len(records))
            for listing_id, record in records.items():
                self._save_ad(listing_id, record, response_id, reply.fetched)
            for listing_id in missing:
                self._save_missing_ad(listing_id, reply.fetched)
        return failed

    def _join_region(self, listing_id):
        self.db.execute(
            "INSERT OR IGNORE INTO graphql_search_members VALUES(?,?,?)",
            (self.generation, self.region, listing_id),
        )

    def _save_ad(self, listing_id, record, response_id, fetched):
        self._join_region(listing_id)
        sha = _sha256(json.dumps(record, sort_keys=True))
        old = self.db.execute(
            """SELECT response_id, record_sha256, status FROM graphql_search_ads
            WHERE generation=? AND listing_id=?""",
            (self.generation, listing_id),
        ).fetchone()
        if old and old["response_id"] is not None and old["record_sha256"] == sha:
            if old["status"] in FINAL:
                # A final record that has not changed needs no new observation.
                self.db.execute(
                    "UPDATE graphql_search_ads SET read=?, run=? WHERE generation=? AND listing_id=?",
                    (fetched, self.run, self.generation, listing_id),
                )
                return
        latest = record.get("latestListing")
        history = record.get("propertyHistory")
        episodes = [
            _int_id(e.get("listingId")) for e in history or [] if isinstance(e, dict)
        ]
        self.db.execute(
            "INSERT OR REPLACE INTO graphql_search_ads VALUES(?,?,?,?,?,?,?,?,?,?,NULL,NULL)",
            (
                self.generation,
                listing_id,
                self.run,
                response_id,
                str(record["buildingId"])
                if record.get("buildingId") is not None
                else None,
                _int_id(latest.get("id")) if isinstance(latest, dict) else None,
                record.get("status"),
                json.dumps([e for e in dict.fromkeys(episodes) if e is not None]),
                sha,
                fetched,
            ),
        )

    def _save_missing_ad(self, listing_id, fetched):
        # Keep an earlier record when there is one; caller holds the transaction.
        self._join_region(listing_id)
        updated = self.db.execute(
            "UPDATE graphql_search_ads SET read=? WHERE generation=? AND listing_id=?",
            (fetched, self.generation, listing_id),
        ).rowcount
        if not updated:
            self.db.execute(
                """INSERT INTO graphql_search_ads(generation,listing_id,run,read)
                VALUES(?,?,?,?)""",
                (self.generation, listing_id, self.run, fetched),
            )

    def _save_buildings(self, job, data, reply):
        records, missing, failed = self._split(job, data)
        self.store.put_body(reply.body)
        self.store.put_body(job.url.encode())
        with self.store._tx():
            response_id = self._response(job, reply, len(records))
            for building_id, record in records.items():
                self.db.execute(
                    "INSERT OR REPLACE INTO graphql_search_buildings VALUES(?,?,?,?,?,?,NULL)",
                    (
                        self.generation,
                        building_id,
                        self.run,
                        response_id,
                        record.get("slug") or None,
                        reply.fetched,
                    ),
                )
            for building_id in missing:
                self._save_missing_building(building_id, reply.fetched)
        return failed

    def _save_missing_building(self, building_id, fetched):
        updated = self.db.execute(
            "UPDATE graphql_search_buildings SET read=? WHERE generation=? AND building_id=?",
            (fetched, self.generation, building_id),
        ).rowcount
        if not updated:
            self.db.execute(
                """INSERT INTO graphql_search_buildings(generation,building_id,run,read)
                VALUES(?,?,?,?)""",
                (self.generation, building_id, self.run, fetched),
            )

    # Steps

    def tree(self):
        """The band tree from this run's counts: leaves, pending bands, gaps and failures."""
        counts = {
            tuple(r[:5]): r["total"]
            for r in self.db.execute(
                f"SELECT {BAND}, total FROM graphql_search_counts WHERE run=?",
                (self.run,),
            )
        }
        out = {
            "pending": [],
            "unanswered": [],
            "leaves": [],
            "gaps": [],
            "truncated": [],
        }
        if FULL not in counts:
            # The first request counts the whole region and its price bands together.
            out["pending"] = [FULL, *children(FULL, self.areas)]
            return out
        stack = [FULL]
        while stack:
            node = stack.pop()
            if node not in counts:
                out["pending"].append(node)
                continue
            total = counts[node]
            if total is None:
                out["unanswered"].append(node)
                continue
            kids = children(node, self.areas)
            if kids and total > CAP:
                stack.extend(kids)
                if all(isinstance(counts.get(k), int) for k in kids):
                    gap = total - sum(counts[k] for k in kids)
                    if gap:
                        out["gaps"].append((node, gap))
            elif total > 0:
                out["leaves"].append((node, total))
                if total > CAP:
                    out["truncated"].append((node, total))
        out["total"] = counts[FULL]
        return out

    def enumerate(self):
        """Count the region's bands until each holds 1,000 ads or fewer, then read their IDs."""
        while pending := self.tree()["pending"]:
            self._run("count", pending, COUNTS_PER_REQUEST)
        done = {
            (tuple(r[:5]), r["direction"])
            for r in self.db.execute(
                f"""SELECT {BAND}, direction FROM graphql_search_slices WHERE run=?
                AND total IS NOT NULL""",
                (self.run,),
            )
        }
        leaves = self.tree()["leaves"]
        size = {node: min(total, CAP) for node, total in leaves}
        wanted = []
        # Requests take the reads in order, fullest band first, so bands of a similar size
        # share a request.
        for node, total in sorted(leaves, key=lambda leaf: -leaf[1]):
            wanted.append((node, "ASCENDING"))
            if total > CAP:
                wanted.append((node, "DESCENDING"))
        self._run(
            "slice",
            [w for w in wanted if w not in done],
            SLICES_PER_REQUEST,
            lambda item: size[item[0]],
        )

    def read_set(self):
        """The ad IDs to read next, all at or above the policy's cutoff.

        The collector reads this run's new hits, the latest ad of each unit, the units'
        older ads in a history region and the ads the API left out in an earlier
        invocation. It re-reads ads with a status other than final from before this run,
        only among this run's hits in a backfill. A top-up run also re-reads its own hits
        from before it, since a final ad can come back on the market.

        Apart from the run's hits, it looks only at its region's ads, so a run leaves other
        regions' units and histories to their own runs.
        """
        hits = "a.listing_id IN (SELECT listing_id FROM graphql_search_hits WHERE run=:run)"
        unread = (
            "NOT EXISTS (SELECT 1 FROM graphql_search_ads b WHERE b.generation=:g "
            "AND b.listing_id={})"
        )
        final = ", ".join(f"'{s}'" for s in sorted(FINAL))
        live = f"(a.status IS NULL OR a.status NOT IN ({final}))"
        parts = [
            f"SELECT h.listing_id FROM graphql_search_hits h WHERE h.run=:run "
            f"AND {unread.format('h.listing_id')}",
            f"SELECT a.latest_id FROM graphql_search_ads a WHERE a.generation=:g "
            f"AND a.latest_id IS NOT NULL AND {MINE} AND {unread.format('a.latest_id')}",
            f"""SELECT a.listing_id FROM graphql_search_ads a WHERE a.generation=:g
            AND a.response_id IS NULL AND a.read<:invoked
            AND {hits if self.active_only else MINE}""",
            f"""SELECT a.listing_id FROM graphql_search_ads a WHERE a.generation=:g
            AND a.response_id IS NOT NULL AND a.read<:started
            AND {f"(({live} AND {MINE}) OR {hits})" if self.active_only else f"{live} AND {hits}"}""",
        ]
        if self.follow_history:
            parts.append(
                f"""SELECT CAST(j.value AS INTEGER) FROM graphql_search_ads a,
                json_each(a.history) j WHERE a.generation=:g AND {MINE}
                AND {unread.format("CAST(j.value AS INTEGER)")}"""
            )
        query = " UNION ".join(f"SELECT * FROM ({p})" for p in parts)
        rows = self.db.execute(
            query,
            {
                "run": self.run,
                "g": self.generation,
                "region": self.region,
                "invoked": self.invoked,
                "started": self.started,
            },
        )
        return sorted({r[0] for r in rows if r[0] is not None and r[0] >= self.cutoff})

    def _ad_batch(self):
        """Ads per request, sized so a response holds about TARGET_BYTES."""
        size, entries = self.db.execute(
            "SELECT sum(bytes), sum(entries) FROM graphql_search_responses WHERE kind='ads'"
        ).fetchone()
        per_ad = size / entries if entries else FIRST_BYTES_PER_AD
        return max(1, min(self.ad_ceiling, int(TARGET_BYTES / per_ad)))

    def read(self):
        for _ in range(AD_ROUNDS):
            ids = self.read_set()
            if not ids:
                break
            self._run("ads", ids, self._ad_batch)

    def read_buildings(self):
        """Read the unread buildings of the region's ads."""
        ids = [
            r[0]
            for r in self.db.execute(
                f"""SELECT DISTINCT a.building_id FROM graphql_search_ads a
                WHERE a.generation=:g AND a.building_id IS NOT NULL AND {MINE}
                AND NOT EXISTS (SELECT 1 FROM graphql_search_buildings b
                    WHERE b.generation=a.generation AND b.building_id=a.building_id
                    AND (b.response_id IS NOT NULL OR b.read>=:invoked))
                ORDER BY CAST(a.building_id AS INTEGER)""",
                {"g": self.generation, "region": self.region, "invoked": self.invoked},
            )
        ]
        self._run("buildings", ids, BUILDINGS_PER_REQUEST)

    # Writing

    def _record(self, response_id, item_id):
        """The response row and the item's record in it; the latest response stays parsed."""
        if self._cached[0] != response_id:
            row = self.db.execute(
                "SELECT * FROM graphql_search_responses WHERE id=?", (response_id,)
            ).fetchone()
            doc = json.loads(self.store.get_body(row["sha256"]))
            items = {}
            for value in (doc.get("data") or {}).values():
                for item in value if isinstance(value, list) else []:
                    if isinstance(item, dict) and item.get("id") is not None:
                        items[str(item["id"])] = item
            self._cached = (response_id, row, items)
        _, row, items = self._cached
        return row, items.get(str(item_id))

    def _capture(self, response):
        return {
            "transport": "oxylabs",
            "provider": json.loads(response["capture"]),
            "graphql_search": {
                "run": response["run"],
                "response_id": response["id"],
                "response_sha256": response["sha256"],
                "query_url_sha256": response["query_sha256"],
                "entries": response["entries"],
            },
        }

    def _extracted(self, url, record, listing_id, building_id, response):
        return {
            "extraction_version": VERSION,
            "url": url,
            "links": history_links(record),
            "graphql_search": {
                "source": SOURCE,
                "listing_id": str(listing_id),
                "building_id": building_id,
                "response_id": response["id"],
                "run": self.run,
            },
        }

    def _scope(self, url, what):
        """Scope a URL for this region; the caller holds the transaction."""
        self.db.execute(
            "INSERT OR IGNORE INTO scope_urls VALUES(?,?,?)",
            (self.generation, url, f"{SEARCH_VERSION} {self.region} {what}"),
        )

    def _record_listing(self, url, listing_id, building, record, response):
        """Record an ad body at `url` in the steps a crawl takes for a listing page."""
        g = self.generation
        body = listing_body(listing_id, building, record)
        data = self._extracted(url, record, listing_id, building["id"], response)
        policy.annotate(self.store, g, data, body, url, persist=False)
        digest = self.store.record(
            g,
            url,
            200,
            {},
            body,
            "application/json",
            data,
            fetched=response["fetched"],
            capture=self._capture(response),
        )
        policy.annotate(self.store, g, data, body, url, body_hash=digest)

    @staticmethod
    def _building(building_id, slug):
        page = f"https://streeteasy.com/building/{slug}" if slug else None
        return {"id": building_id, "slug": slug, "page": page}

    def _write_buildings(self, counts):
        g = self.generation
        rows = self.db.execute(
            """SELECT * FROM graphql_search_buildings WHERE generation=?
            AND response_id IS NOT NULL AND written_run IS NULL ORDER BY response_id""",
            (g,),
        ).fetchall()
        for row in rows:
            self._tick()
            response, record = self._record(row["response_id"], row["building_id"])
            url = self._building(row["building_id"], row["slug"])["page"]
            if (
                record is None
                or not url
                or canonical_url(url) != url
                or kind_for(url) != "building"
            ):
                counts["buildings_without_page"] += 1
            else:
                body = building_body(row["building_id"], record)
                with self.store._tx():
                    self.store._enqueue(g, [{"url": url, "kind": "building"}])
                    self._scope(url, "building")
                    self.db.execute(
                        "INSERT OR IGNORE INTO scope_buildings VALUES(?,?)", (g, url)
                    )
                self.store.record(
                    g,
                    url,
                    200,
                    {},
                    body,
                    "application/json",
                    {
                        "extraction_version": VERSION,
                        "url": url,
                        "links": [],
                        "json": building_document(body),
                    },
                    fetched=response["fetched"],
                    capture=self._capture(response),
                )
                counts["buildings_written"] += 1
            with self.store._tx():
                self.db.execute(
                    "UPDATE graphql_search_buildings SET written_run=? WHERE generation=? AND building_id=?",
                    (self.run, g, row["building_id"]),
                )

    def _write_units(self, counts):
        """Record each unit from its latest ad, whose record its page shows."""
        g = self.generation
        rows = self.db.execute(
            """SELECT a.listing_id, a.building_id, a.response_id, b.slug,
            b.building_id IS NOT NULL AS building_read
            FROM graphql_search_ads a LEFT JOIN graphql_search_buildings b
            ON b.generation=a.generation AND b.building_id=a.building_id
            WHERE a.generation=? AND a.latest_id=a.listing_id AND a.response_id IS NOT NULL
            AND a.unit_written IS NULL ORDER BY a.response_id""",
            (g,),
        ).fetchall()
        for row in rows:
            self._tick()
            if row["building_id"] is not None and not row["building_read"]:
                counts["units_waiting_for_building"] += 1
                continue
            response, record = self._record(row["response_id"], row["listing_id"])
            building = self._building(row["building_id"], row["slug"])
            unit = _unit_route(canonical_link(building, record)) if record else None
            if unit is None:
                counts["units_without_page"] += 1
            else:
                with self.store._tx():
                    self.store._enqueue(g, [{"url": unit, "kind": "listing"}])
                    self._scope(unit, "unit")
                self._record_listing(
                    unit, row["listing_id"], building, record, response
                )
                counts["units_written"] += 1
            with self.store._tx():
                self.db.execute(
                    "UPDATE graphql_search_ads SET unit_written=? WHERE generation=? AND listing_id=?",
                    (self.run, g, row["listing_id"]),
                )

    def _write_ads(self, counts):
        """Record, supersede, exclude or mark as a gap each ad not yet written."""
        g = self.generation
        rows = self.db.execute(
            """SELECT a.listing_id, a.building_id, a.response_id, a.latest_id, b.slug,
            b.building_id IS NOT NULL AS building_read,
            l.listing_id AS latest_row, l.latest_id AS latest_latest,
            l.response_id AS latest_response, l.unit_written AS latest_unit_written
            FROM graphql_search_ads a
            LEFT JOIN graphql_search_buildings b
              ON b.generation=a.generation AND b.building_id=a.building_id
            LEFT JOIN graphql_search_ads l
              ON l.generation=a.generation AND l.listing_id=a.latest_id
            LEFT JOIN frontier f
              ON f.generation=a.generation AND f.url='https://streeteasy.com/rental/'||a.listing_id
            WHERE a.generation=? AND (a.written_run IS NULL OR f.state='pending')
            ORDER BY a.response_id, a.listing_id""",
            (g,),
        ).fetchall()
        for row in rows:
            self._tick()
            latest = row["latest_id"]
            if (
                latest is not None
                and latest >= self.cutoff
                and row["latest_row"] is None
            ):
                counts["ads_waiting_for_latest"] += 1
                continue
            if (
                row["latest_row"] is not None
                and row["latest_latest"] == row["latest_row"]
                and row["latest_response"] is not None
                and row["latest_unit_written"] is None
            ):
                counts["ads_waiting_for_unit"] += 1
                continue
            if row["response_id"] is not None and row["building_id"] is not None:
                if not row["building_read"]:
                    counts["ads_waiting_for_building"] += 1
                    continue
            url = f"https://streeteasy.com/rental/{row['listing_id']}"
            with self.store._tx():
                self.store._enqueue(g, [{"url": url, "kind": "listing"}])
                self._scope(url, "follow-up read")
                reason = policy.exclusion_reason(self.store, g, url)
                if reason:
                    policy.exclude(self.store, g, url, reason)
                    action = "excluded"
                elif row["response_id"] is None:
                    action = "gap"
                else:
                    frontier = self.db.execute(
                        "SELECT * FROM frontier WHERE generation=? AND url=?", (g, url)
                    ).fetchone()
                    superseded = policy.reuse_unit_capture(self.store, g, frontier)
                    action = "superseded" if superseded else "record"
            if action == "gap":
                self.store.record_gap(
                    g,
                    url,
                    None,
                    {},
                    "API gave no record",
                    capture={
                        "transport": "oxylabs",
                        "graphql_search": {"run": self.run},
                    },
                )
            elif action == "record":
                response, record = self._record(row["response_id"], row["listing_id"])
                building = self._building(row["building_id"], row["slug"])
                self._record_listing(url, row["listing_id"], building, record, response)
            counts["ads_" + action] += 1
            with self.store._tx():
                self.db.execute(
                    "UPDATE graphql_search_ads SET written_run=? WHERE generation=? AND listing_id=?",
                    (self.run, g, row["listing_id"]),
                )

    def _close_scope(self, counts):
        """Exclude scoped ads below the cutoff and count the rest the run has not read."""
        g = self.generation
        rows = self.db.execute(
            """SELECT s.url FROM scope_urls s LEFT JOIN frontier f USING(generation,url)
            WHERE s.generation=? AND f.url IS NULL
            AND s.url LIKE 'https://streeteasy.com/rental/%'""",
            (g,),
        ).fetchall()
        for (url,) in rows:
            self._tick()
            key = listing_key(url)
            ad = int(key.split(":")[1]) if key else None
            if ad is not None and ad < self.cutoff:
                with self.store._tx():
                    self.store._enqueue(g, [{"url": url, "kind": "listing"}])
                    policy.exclude(self.store, g, url, "before_min_listing_id")
                counts["scoped_ads_before_cutoff"] += 1
            else:
                counts["scoped_ads_unread"] += 1

    @contextmanager
    def _batched(self):
        """Hold a transaction open over the write phase, and commit it every WRITE_BATCH rows.

        While the batch is open, each store._tx block runs as a savepoint. When a step fails,
        its savepoint undoes that step alone. When an error leaves the phase, the open batch
        rolls back, and the next run writes its rows again.
        """
        db = self.db

        @contextmanager
        def savepoint():
            db.execute("SAVEPOINT step")
            try:
                yield
            except BaseException:
                # After a full disk or an I/O error, SQLite rolls back the whole transaction
                # itself, and the savepoint is gone.
                if db.in_transaction:
                    db.execute("ROLLBACK TO step")
                    db.execute("RELEASE step")
                raise
            db.execute("RELEASE step")

        db.execute("BEGIN IMMEDIATE")
        self.store._tx, self._rows = savepoint, 0
        try:
            yield
        except BaseException:
            db.rollback()
            raise
        else:
            db.commit()
        finally:
            del self.store._tx

    def _tick(self):
        """Count a row of the write phase, and commit the batch at every WRITE_BATCH rows."""
        self._rows += 1
        if self._rows % WRITE_BATCH == 0:
            self.db.commit()
            self.db.execute("BEGIN IMMEDIATE")

    def write(self):
        """Write what the run has read into the archive, with no requests."""
        counts = Counter()
        with self._batched():
            self._write_buildings(counts)
            with self.store._tx():
                self.db.execute(
                    """INSERT OR IGNORE INTO scope_urls SELECT ?, 'https://streeteasy.com/rental/'
                    || listing_id, ? FROM graphql_search_hits WHERE run=?""",
                    (
                        self.generation,
                        f"{SEARCH_VERSION} {self.region} area search",
                        self.run,
                    ),
                )
            self._write_units(counts)
            self._write_ads(counts)
            self._close_scope(counts)
        self._cached = (None, None, {})
        return dict(sorted(counts.items()))

    # Current listings

    # The whole run

    def report(self, writes, stopped):
        g, run = self.generation, self.run
        tree = self.tree()
        calls = dict(
            self.db.execute(
                "SELECT kind, sum(attempt) FROM graphql_search_calls WHERE run=? GROUP BY kind",
                (run,),
            ).fetchall()
        )
        statuses = dict(
            self.db.execute(
                """SELECT coalesce(status, 'no record'), count(*) FROM graphql_search_ads
                WHERE generation=? AND run=? GROUP BY 1""",
                (g, run),
            ).fetchall()
        )
        hits = self.db.execute(
            "SELECT count(*) FROM graphql_search_hits WHERE run=?", (run,)
        ).fetchone()[0]
        short = self.db.execute(
            """SELECT coalesce(sum(min(total, ?) - ids), 0) FROM graphql_search_slices
            WHERE run=? AND total IS NOT NULL AND direction='ASCENDING'""",
            (CAP, run),
        ).fetchone()[0]
        buildings = self.db.execute(
            """SELECT count(*), coalesce(sum(response_id IS NULL), 0)
            FROM graphql_search_buildings WHERE generation=?""",
            (g,),
        ).fetchone()
        return {
            "version": SEARCH_VERSION,
            "run": run,
            "generation": g,
            "region": self.region,
            "areas": self.areas,
            "active_only": self.active_only,
            "follow_history": self.follow_history,
            "invocation": {
                "started": _iso(self.invoked),
                "finished": _iso(time.time()),
                "requests": self.client.calls,
                "dollars": round(self.client.calls * PRICE, 2),
                "stopped": str(stopped) if stopped else None,
            },
            "run_requests": calls,
            "run_dollars": round(sum(calls.values()) * PRICE, 2),
            "enumeration": {
                "total": tree.get("total"),
                "leaves": len(tree["leaves"]),
                "leaf_sum": sum(t for _, t in tree["leaves"]),
                "hits": hits,
                "slice_shortfall": short,
                "gaps": tree["gaps"],
                "truncated": tree["truncated"],
                "unanswered": tree["unanswered"],
                "pending": len(tree["pending"]),
            },
            "ads_read_this_run": statuses,
            "buildings": {"known": buildings[0], "no_record": buildings[1]},
            "write": writes,
        }

    def collect(self):
        stopped = None
        try:
            self.enumerate()
            self.read()
            self.read_buildings()
        except (Stop, Budget) as exc:
            stopped = exc
        writes = self.write()
        report = self.report(writes, stopped)
        with self.store._tx():
            self.db.execute(
                "UPDATE graphql_search_runs SET report=?, finished=? WHERE id=?",
                (
                    json.dumps(report, sort_keys=True),
                    time.time() if stopped is None else None,
                    self.run,
                ),
            )
        path = self.store.root / "graphql-search" / f"run-{self.run}.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
        return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--region", required=True)
    parser.add_argument(
        "--area", type=int, action="append", help="area IDs in place of the region's"
    )
    parser.add_argument("--data", type=Path, help=f"archive folder (default {ARCHIVE})")
    parser.add_argument("--active-only", action="store_true")
    parser.add_argument("--max-requests", type=int, required=True)
    parser.add_argument("--rate", type=float, default=30, help="requests a minute")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--new-run", action="store_true")
    parser.add_argument(
        "--reopen",
        action="store_true",
        help="resume the latest run, even a finished one",
    )
    args = parser.parse_args(argv)
    if args.area:
        areas, follow_history = args.area, True
    elif args.region in REGIONS:
        areas, follow_history = REGIONS[args.region]
    else:
        parser.error(f"unknown region {args.region}; give --area")
    if args.new_run and args.reopen:
        parser.error("--new-run and --reopen exclude each other")
    data = args.data or ARCHIVE
    data.mkdir(parents=True, exist_ok=True)
    with (data / "collector.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error(f"another collector holds {data / 'collector.lock'}")
        client = Client(args.max_requests, args.rate)
        store = ArchiveStore(data)
        try:
            collector = Collector(
                store,
                client,
                args.region,
                areas,
                follow_history=follow_history,
                active_only=args.active_only,
                new_run=args.new_run,
                reopen=args.reopen,
                workers=args.workers,
            )
            report = collector.collect()
        finally:
            store.close()
    print(json.dumps(report, sort_keys=True))
    return 2 if report["invocation"]["stopped"] else 0


if __name__ == "__main__":
    sys.exit(main())
