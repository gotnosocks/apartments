"""Rental inventories from StreetEasy's GraphQL history instead of a rendered modal.

A building's past rentals were read by rendering its page in Oxylabs' browser, clicking
"View unavailable units", then "For rent", and waiting for the table: slow, and about 9% of
jobs were resubmitted (Brooklyn, Oct 2026). StreetEasy's own front end reads the same list
from `rentalsHistoryByBuildingId` on api-v6.streeteasy.com. One plain Oxylabs GET carries
that query for about 24 buildings as aliased fields; the `apollo-require-preflight` header is
required (data/probes/no-render-20261013/, Oct 13 2026: in 30 pilot buildings the history
held every ad the modal showed, and more). Ben, Oct 13 2026: "Use rentalsHistoryByBuildingId
via a plain Oxylabs GET with the apollo-require-preflight header, 20–25 buildings per
request, and keep the browser path as fallback."

The frontier keeps the `?archive_view=unavailable-rentals` URL and each building gets its own
observation: the body is that building's history as JSON, and the extracted `inventory` has
the shape the modal parser gives (links, records, rows), so scope expansion and the
inventory-label unit probes run unchanged. A building whose history is missing, errored,
empty or smaller than its page's rental summary is marked for fallback and goes back to the
queue, where the next claim fetches it through the browser as before. crawler.py,
oxylabs.py, extract.py and store.py are hashed by saved datasets, so this lives in its own
module: cli.py selects the spider and handler subclasses below with --graphql-inventory.

With --graphql-unit-paths the query also asks for each ad's `urlPath`. For an ad with its
own unit page, StreetEasy gives that page's path there, for example
`/building/330-1-avenue-new_york/05e` for ad 3822968, the page `/rental/3822968` redirects
to. The crawl queues that path as the ad's unit probe and leaves the ad's label out of the
row, so the crawl skips a guessed route such as `/5e`, which returns 404 for that ad. For
an ad that opens on its own page, the API gives `/rental/ID`, and the crawl keeps guessing
its unit route from the label. Membership still comes only from the probed page's own
rental history, under the same rule. In 30 Manhattan pilot buildings 2,743 ads had a unit
path, each a different page, and 32 of those paths had hyphens (`6-h`, `7th-floor`) that
the label guess drops (Ben, Oct 13 2026).

StreetEasy also keeps some units under two spellings, each page canonical to itself. In the
pilot, `/4c` and `/04c` at 240 1st Ave list the same seven ads (Oct 13 2026), and 109 API
paths had another spelling the crawl had already captured. Fetching both would tie each ad
to two units, and the policy would exclude it as conflicting. So the crawl compares
spellings with letters and digits only, lowercased and without leading zeros:
  1. A label guess is dropped when an API path in the same building has its spelling.
  2. An API path is dropped when the frontier holds another spelling of it that was
     captured, is in flight, or came from StreetEasy's own links.
  3. A pending label guess with the API path's spelling is retired as superseded by it.
A guess that returned 404 counts for nothing.
"""

import asyncio
import html
import json
import re
import time
import urllib.parse

import requests
from scrapy.http import HtmlResponse
import scrapy

from .capture import capture_metadata
from .crawler import ArchiveSpider, is_challenge, retry_after
from .extract import VERSION, canonical_url, extract, is_unavailable_url, kind_for
from .oxylabs import (
    API_URL,
    MAX_BODY,
    OxylabsDownloadHandler,
    RetryableOxylabsError,
    _credentials,
    _result_item,
    _safe_envelope,
)
from .scope import building_root, objects, summary_counts

API_HOST = "https://api-v6.streeteasy.com/"
SOURCE = "rentalsHistoryByBuildingId"
FIELDS = (
    "id status availableAt createdAt offMarketAt displayUnit price bedroomCount "
    "fullBathroomCount halfBathroomCount livingAreaSize monthsFree leaseTermMonths noFee"
)
# Oxylabs refuses a target URL over 8,192 characters.
MAX_URL = 8000
DEFAULT_BATCH = 24
# Whole batches failing in a row before the run stops using GraphQL.
MAX_FAILED_BATCHES = 3
# Target statuses Oxylabs should return rather than retry: the API's own refusals.
REFUSALS = [400, 403, 405, 413, 414]
UNIT_PATH_FIELD = " urlPath"


def is_graphql_url(url):
    return isinstance(url, str) and url.startswith(API_HOST)


def is_rental_inventory(url):
    return is_unavailable_url(url) and "archive_view=unavailable-rentals" in url


def query_url(batch, fields=FIELDS):
    """One GET with each building's history as an aliased field h0, h1, ..."""
    parts = [
        f"h{i}: {SOURCE}(id: {json.dumps(entry['building_id'])}) {{ ...H }}"
        for i, entry in enumerate(batch)
    ]
    query = (
        "query ArchiveRentalHistory { "
        + " ".join(parts)
        + " } fragment H on RentalListingDigest { "
        + fields
        + " }"
    )
    return API_HOST + "?" + urllib.parse.urlencode({"query": query})


def build_payload(url):
    return {
        "source": "universal",
        "url": url,
        "context": [
            {"key": "force_headers", "value": True},
            {"key": "headers", "value": {"apollo-require-preflight": "true"}},
            {"key": "successful_status_codes", "value": REFUSALS},
        ],
    }


def building_info(store, inventory_url):
    """The building's GraphQL ID and rental-summary counts from its archived page."""
    root = building_root(inventory_url)
    row = store.latest_response(root) if root else None
    if not row:
        return None
    data = extract(store.get_body(row["body_hash"]), root, row["content_type"] or "")
    slug = root.rsplit("/", 1)[1]
    ids = {
        o["id"]
        for o in objects(data)
        if o.get("slug") == slug
        and isinstance(o.get("id"), str)
        and o["id"].isdigit()
        and "rentalSummary" in o
    }
    if len(ids) != 1:
        return None
    return {
        "url": inventory_url,
        "building_id": ids.pop(),
        "expected_counts": summary_counts(data, "rentalSummary"),
    }


def split(body, batch):
    """Each building's history list (None when absent) and the response's errors."""
    doc = json.loads(body)
    if not isinstance(doc, dict):
        raise ValueError("GraphQL response is not an object")
    data = doc.get("data") if isinstance(doc.get("data"), dict) else {}
    errors = doc.get("errors") if isinstance(doc.get("errors"), list) else []
    return {entry["url"]: data.get(f"h{i}") for i, entry in enumerate(batch)}, errors


def building_body(entry, history, request_url):
    return json.dumps(
        {
            "source": SOURCE,
            "building_id": entry["building_id"],
            "expected_counts": entry["expected_counts"],
            "request_url": request_url,
            "history": history,
        },
        sort_keys=True,
    ).encode()


def inventory_from_history(doc, url):
    """The `inventory` the modal parser gives, from one building's history."""
    if not is_rental_inventory(url):
        raise ValueError("GraphQL history is only for rental inventories")
    history = doc.get("history") if isinstance(doc, dict) else None
    if doc.get("source") != SOURCE or not isinstance(history, list):
        raise ValueError("not a rental history document")
    root = building_root(url)
    links, records, rows, seen, unit_paths = [], [], [], set(), {}
    api_spellings = {
        spelling(page)
        for page in (
            unit_path(e.get("urlPath"), root) for e in history if isinstance(e, dict)
        )
        if page
    }
    for entry in history:
        ad = entry.get("id") if isinstance(entry, dict) else None
        if not isinstance(ad, str) or not ad.isdigit():
            raise ValueError("history entry without an advertisement ID")
        if ad in seen:
            continue
        seen.add(ad)
        listing = f"https://streeteasy.com/rental/{ad}"
        links.append({"url": listing, "kind": "listing"})
        records.append({"url": listing, "kind": "listing", "digest": entry})
        unit_page = unit_path(entry.get("urlPath"), root)
        unit = entry.get("displayUnit")
        label = (
            html.escape(unit if unit.startswith("#") else "#" + unit)
            if isinstance(unit, str)
            and unit.strip()
            and not unit_page
            and spelling(unit) not in api_spellings
            else ""
        )
        if unit_page:
            # The archived row then has no unit label; displayUnit stays in the digest.
            unit_paths.setdefault(unit_page, listing)
        # The modal's row shape: inventory_unit_probes reads the second cell as the
        # unit label and the first link as the source advertisement.
        rows.append(f'<tr><td><a href="{listing}">{ad}</a></td><td>{label}</td></tr>')
    # Scope schedules an inventory only for a building whose rental summary is positive,
    # so an empty history is a failed read, as an empty modal table is.
    if not records:
        raise ValueError("rental history is empty")
    expected = [n for n in doc.get("expected_counts") or [] if isinstance(n, int)]
    if expected and max(expected) > len(records):
        raise ValueError("rental history smaller than building summary")
    return {
        "count": len(records),
        "links": links,
        "records": records,
        "rows": rows,
        "expected_counts": expected,
        "source": SOURCE,
        "unit_paths": unit_paths,
    }


def unit_path(path, root):
    """StreetEasy's unit page for an ad, when the API gives one in this building."""
    from .listing_identity import listing_key

    if not isinstance(path, str) or not path.startswith("/building/") or not root:
        return None
    url = canonical_url(path)
    if (
        not url
        or building_root(url) != root
        or kind_for(url) != "listing"
        or listing_key(url)
    ):
        return None
    return url


def spelling(unit):
    """A unit's route or label, reduced to compare StreetEasy's spellings of it."""
    text = re.sub(r"[^a-z0-9]", "", unit.rsplit("/", 1)[-1].lower())
    return text.lstrip("0") or text


def unit_path_probes(store, generation, data, source_url, include_unavailable):
    """Queue the API's unit pages as probes, under the conditions scope.expand uses."""
    from .scope import _enroll

    probes, retired = _probes(store, generation, data, source_url, include_unavailable)
    if probes:
        with store._tx():
            _enroll(store, generation, probes)
            _retire(store, generation, retired)
    return len(probes)


def _retire(store, generation, retired):
    for old, new in retired.items():
        store._remember_alias(
            generation, old, new, "label guess superseded by StreetEasy's unit path"
        )
        store.db.execute(
            "UPDATE frontier SET state='superseded' WHERE generation=? AND url=?",
            (generation, old),
        )


def _probes(store, generation, data, source_url, include_unavailable, roots=None):
    from .collection_policy import PROBE_RULE, enabled
    from .listing_identity import listing_key

    paths = data.get("inventory", {}).get("unit_paths") or {}
    if not (paths and include_unavailable and enabled(store, generation)):
        return {}, {}
    if roots is None:
        roots = _roots(store, generation)
    if building_root(source_url) not in roots:
        return {}, {}
    root = building_root(source_url)
    # Other spellings already in the frontier: those that block an API path, and pending
    # label guesses that give way to it.
    blocking, guesses = {}, {}
    for row in store.db.execute(
        """SELECT f.url, f.state, s.reason,
            (SELECT o.status FROM observations o WHERE o.generation=f.generation
             AND o.url=f.url ORDER BY o.id DESC LIMIT 1) AS status
        FROM frontier f LEFT JOIN scope_urls s ON s.generation=f.generation AND s.url=f.url
        WHERE f.generation=? AND f.url>=? AND f.url<?""",
        (generation, root + "/", root + "0"),
    ):
        url = row["url"]
        if kind_for(url) != "listing" or listing_key(url):
            continue
        key = spelling(url)
        if row["state"] in ("pending", "deferred") and (row["reason"] or "").startswith(
            PROBE_RULE
        ):
            guesses.setdefault(key, set()).add(url)
        elif row["state"] in ("pending", "deferred", "inflight") or (
            row["state"] == "done"
            and row["status"] is not None
            and (200 <= row["status"] < 300 or row["status"] == 304)
        ):
            blocking.setdefault(key, set()).add(url)
    probes, retired = {}, {}
    for unit, ad in paths.items():
        key = spelling(unit)
        if blocking.get(key, set()) - {unit}:
            continue
        blocking.setdefault(key, set()).add(unit)
        probes[unit] = f"{PROBE_RULE} from {ad}"
        for old in guesses.pop(key, set()) - {unit}:
            retired[old] = unit
    return probes, retired


def _roots(store, generation):
    return {
        r[0]
        for r in store.db.execute(
            "SELECT url FROM scope_buildings WHERE generation=?", (generation,)
        )
    }


def replay_unit_paths(store, generation, include_unavailable, building=None):
    """Queue unit paths from GraphQL inventories already archived, offline.

    collection_policy.setup replays label probes from archived inventories, and this does
    the same for unit paths, so a resumed generation keeps its probes. With a building,
    only that building's probes are queued, as scope.expand does.
    """
    from .scope import _enroll

    roots = _roots(store, generation)
    if building:
        roots &= {building}
    ids = store.db.execute(
        """SELECT id, url FROM snapshots WHERE generation=?
        AND url LIKE '%archive_view=unavailable-rentals%' ORDER BY id""",
        (generation,),
    ).fetchall()
    probes, retired = {}, {}
    for row in ids:
        if building_root(row["url"]) not in roots:
            continue
        extracted = store.db.execute(
            "SELECT extracted FROM snapshots WHERE id=?", (row["id"],)
        ).fetchone()[0]
        if '"unit_paths"' not in (extracted or ""):
            continue
        try:
            data = json.loads(extracted)
        except (TypeError, ValueError):
            continue
        found, gone = _probes(
            store, generation, data, row["url"], include_unavailable, roots
        )
        for unit, reason in found.items():
            probes.setdefault(unit, reason)
        retired.update(gone)
    if probes:
        with store._tx():
            _enroll(store, generation, probes)
            _retire(store, generation, retired)
    return len(probes)


def extract_history(body, url):
    doc = json.loads(body)
    return {
        "extraction_version": VERSION,
        "url": url,
        "links": [],
        "json": doc,
        "inventory": inventory_from_history(doc, url),
    }


def _ensure_table(store):
    store.db.execute(
        "CREATE TABLE IF NOT EXISTS graphql_inventory_fallback(generation INTEGER NOT NULL, "
        "url TEXT NOT NULL, reason TEXT NOT NULL, created REAL NOT NULL, "
        "PRIMARY KEY(generation,url))"
    )
    store.db.commit()


def fallen_back(store, generation, url):
    return bool(
        store.db.execute(
            "SELECT 1 FROM graphql_inventory_fallback WHERE generation=? AND url=?",
            (generation, url),
        ).fetchone()
    )


def fall_back(store, generation, url, reason):
    """Send a claimed building back to the queue for the browser path."""
    with store._tx():
        store.db.execute(
            "INSERT OR IGNORE INTO graphql_inventory_fallback VALUES(?,?,?,?)",
            (generation, url, reason[:500], time.time()),
        )
        store.db.execute(
            "UPDATE frontier SET state='pending',next_attempt=0,"
            "attempts=max(0,attempts-1) WHERE generation=? AND url=? AND state='inflight'",
            (generation, url),
        )


def release(store, generation, url):
    """Return a claimed building to the queue unfetched, for a later batch."""
    with store._tx():
        store.db.execute(
            "UPDATE frontier SET state='pending',attempts=max(0,attempts-1) "
            "WHERE generation=? AND url=? AND state='inflight'",
            (generation, url),
        )


def claim_more(store, generation, limit, scoped, now=None):
    """Claim up to `limit` more pending rental inventories not marked for fallback."""
    from .collection_policy import exclude, exclusion_reason

    now = time.time() if now is None else now
    claimed = []
    with store._tx():
        rows = store.db.execute(
            """SELECT f.* FROM frontier f JOIN generations g ON g.id=f.generation
            WHERE f.generation=? AND f.state='pending' AND f.next_attempt<=?
            AND f.kind='inventory' AND f.url LIKE '%archive_view=unavailable-rentals'
            AND (g.cooldown IS NULL OR g.cooldown<=?)
            AND (?=0 OR EXISTS(SELECT 1 FROM scope_urls scope
                WHERE scope.generation=f.generation AND scope.url=f.url))
            AND NOT EXISTS(SELECT 1 FROM graphql_inventory_fallback fb
                WHERE fb.generation=f.generation AND fb.url=f.url)
            ORDER BY f.rowid LIMIT ?""",
            (generation, now, now, int(scoped), limit),
        ).fetchall()
        for row in rows:
            reason = exclusion_reason(store, generation, row["url"])
            if reason:
                exclude(store, generation, row["url"], reason)
                continue
            store.db.execute(
                "UPDATE frontier SET state='inflight',attempts=attempts+1 "
                "WHERE generation=? AND url=?",
                (generation, row["url"]),
            )
            claimed.append(row)
    return claimed


class GraphQLOxylabsHandler(OxylabsDownloadHandler):
    """OxylabsDownloadHandler that also sends api-v6 GraphQL GETs as plain jobs."""

    async def download_request(self, request, spider=None):
        if not is_graphql_url(request.url):
            return await super().download_request(request, spider)
        if len(request.url) > 8192:
            raise ValueError("GraphQL URL exceeds Oxylabs' 8,192-character limit")
        username, password = _credentials()
        payload = build_payload(request.url)
        started_at = time.time()
        result = None
        for attempt in range(3):
            result = None
            try:
                await self._submission_slot()
                result = await asyncio.to_thread(
                    requests.post,
                    API_URL,
                    json=payload,
                    auth=(username, password),
                    timeout=180,
                    allow_redirects=False,
                )
                if result.status_code in (401, 402, 403):
                    result.raise_for_status()
                if result.status_code == 429 or result.status_code >= 500:
                    result.raise_for_status()
                results, item, status, content = _result_item(result.json())
                break
            except requests.RequestException as exc:
                api_status = (
                    exc.response.status_code if exc.response is not None else None
                )
                if api_status in (401, 402, 403):
                    raise RuntimeError(
                        f"Oxylabs request failed (HTTP {api_status})"
                    ) from None
                detail = (
                    f"HTTP {api_status}"
                    if api_status is not None
                    else type(exc).__name__
                )
                failure = f"Oxylabs request failed ({detail})"
            except (ValueError, TypeError):
                failure = "Oxylabs returned invalid JSON"
            except RetryableOxylabsError as exc:
                failure = str(exc)
            retry_headers = getattr(result, "headers", {}) if result is not None else {}
            if attempt == 2 or not self._defer_submissions(
                retry_headers.get("Retry-After"), attempt
            ):
                raise RetryableOxylabsError(failure) from None
        body = content.encode("utf-8") if isinstance(content, str) else content
        if len(body) > MAX_BODY:
            raise RuntimeError("Oxylabs response exceeds 32 MiB")
        response = HtmlResponse(
            url=request.url, status=status, body=body, request=request, encoding="utf-8"
        )
        response.meta["archive_provider"] = {
            "provider": "oxylabs",
            "api_endpoint": API_URL,
            "api_status": result.status_code,
            "started_at": started_at,
            "completed_at": time.time(),
            "source": payload["source"],
            "render": None,
            "target_url": payload["url"],
            "browser_instructions": [],
            "results": _safe_envelope(results),
            "api_headers": {
                k: v
                for k, v in getattr(result, "headers", {}).items()
                if k.lower().startswith("x-ratelimit-")
                or k.lower() == "x-oxylabs-job-id"
            },
            "submission_attempts": attempt + 1,
        }
        response.meta["archive_response_headers"] = {}
        return response


class GraphQLInventorySpider(ArchiveSpider):
    """ArchiveSpider that reads rental inventories in GraphQL batches."""

    def __init__(
        self, *args, graphql_batch=DEFAULT_BATCH, graphql_unit_paths=False, **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.graphql_batch = max(1, int(graphql_batch))
        self.unit_paths = bool(graphql_unit_paths)
        self.fields = FIELDS + (UNIT_PATH_FIELD if self.unit_paths else "")
        if self.unit_paths and (self.neighborhood or self.building):
            replay_unit_paths(
                self.store,
                self.generation,
                self.include_unavailable,
                building=self.building,
            )
        self.graphql_active = True
        self.graphql_failed_batches = 0
        _ensure_table(self.store)

    def _building_info(self, url):
        # An unreadable building page sends that building to the browser path rather
        # than raising out of _request with rows inflight.
        try:
            return building_info(self.store, url)
        except Exception:
            self.logger.exception("building ID lookup failed for %s", url)
            return None

    def _request(self):
        request = super()._request()
        if (
            request is None
            or not self.graphql_active
            or self.building
            or request.meta.get("archive_kind") != "inventory"
            or not is_rental_inventory(request.meta["archive_url"])
        ):
            return request
        url = request.meta["archive_url"]
        if fallen_back(self.store, self.generation, url):
            return request
        first = self._building_info(url)
        if not first:
            fall_back(
                self.store,
                self.generation,
                url,
                "no building ID on the archived building page",
            )
            # The row is pending again; this request slot goes to the browser path.
            self.sent -= 1
            self.outstanding -= 1
            return self._request()
        batch = [first]
        for row in claim_more(
            self.store,
            self.generation,
            self.graphql_batch - 1,
            bool(self.neighborhood or self.building),
        ):
            info = self._building_info(row["url"])
            if not info:
                fall_back(
                    self.store,
                    self.generation,
                    row["url"],
                    "no building ID on the archived building page",
                )
            elif len(query_url(batch + [info], self.fields)) > MAX_URL:
                release(self.store, self.generation, row["url"])
            else:
                batch.append(info)
        return scrapy.Request(
            query_url(batch, self.fields),
            callback=self.parse,
            errback=self.errback,
            dont_filter=True,
            meta={
                "archive_url": url,
                "archive_kind": "inventory",
                "archive_graphql_batch": batch,
                "dont_redirect": True,
                "handle_httpstatus_all": True,
            },
        )

    def parse(self, response):
        batch = response.meta.get("archive_graphql_batch")
        if not batch:
            yield from super().parse(response)
            return
        self.outstanding = max(0, self.outstanding - 1)
        self.store.note_response(self.delay / 2)
        status = response.status
        body = bytes(response.body)
        capture = capture_metadata(response.meta, self.transport)
        if status in (401, 403, 408, 429) or status >= 500 or is_challenge(body):
            # Blocked, challenged or pushed back: the same stop as any other page.
            for entry in batch:
                self.store.record_gap(
                    self.generation,
                    entry["url"],
                    status,
                    {},
                    f"GraphQL blocked/challenge or transient HTTP {status}",
                    complete=False,
                    pause_seconds=retry_after(dict(response.headers.to_unicode_dict())),
                    capture=capture,
                )
            self.stopped = True
            return
        histories, errors = {}, []
        if status == 200:
            try:
                histories, errors = split(body, batch)
            except ValueError:
                pass
        if any(isinstance(h, list) for h in histories.values()):
            self.graphql_failed_batches = 0
        else:
            self.graphql_failed_batches += 1
            if self.graphql_failed_batches >= MAX_FAILED_BATCHES:
                self.graphql_active = False
                self.logger.error(
                    "GraphQL inventory failed for %d batches in a row (last HTTP %s); "
                    "browser path for the rest of this run",
                    self.graphql_failed_batches,
                    status,
                )
        from .collection_policy import annotate
        from .compact import without_page_copy
        from .scope import discovery_links, expand

        provider = response.meta.get("archive_provider")
        for entry in batch:
            url = entry["url"]
            history = histories.get(url)
            if not isinstance(history, list):
                note = "; ".join(
                    str(e.get("message", e))[:200]
                    for e in errors[:2]
                    if isinstance(e, dict)
                )
                fall_back(
                    self.store,
                    self.generation,
                    url,
                    f"GraphQL HTTP {status}: {note or 'no history'}",
                )
                continue
            doc_body = building_body(entry, history, response.url)
            try:
                data = extract_history(doc_body, url)
                annotate(
                    self.store, self.generation, data, doc_body, url, persist=False
                )
                if provider:
                    data["provider_capture"] = without_page_copy(provider, body)
                links = discovery_links(data, url, self.include_unavailable)
            except Exception as exc:
                fall_back(
                    self.store,
                    self.generation,
                    url,
                    f"GraphQL {type(exc).__name__}: {exc}",
                )
                continue
            self.store.record(
                self.generation,
                url,
                200,
                {},
                doc_body,
                "application/json",
                data,
                discovered=links,
                capture=capture,
            )
            try:
                annotate(self.store, self.generation, data, doc_body, url)
                if self.neighborhood or self.building:
                    expand(
                        self.store,
                        self.generation,
                        data,
                        url,
                        self.include_unavailable,
                        building=self.building,
                        neighborhood=self.neighborhood,
                    )
                    if self.unit_paths:
                        unit_path_probes(
                            self.store,
                            self.generation,
                            data,
                            url,
                            self.include_unavailable,
                        )
            except Exception:
                # The inventory is recorded; finish the rest of the batch.
                self.logger.exception("annotating GraphQL inventory %s failed", url)
        yield from self.start_requests()

    def errback(self, failure):
        batch = failure.request.meta.get("archive_graphql_batch")
        if not batch:
            yield from super().errback(failure)
            return
        self.outstanding = max(0, self.outstanding - 1)
        self.store.note_response(self.delay / 2)
        retryable = isinstance(failure.value, RetryableOxylabsError)
        for entry in batch:
            self.store.record_gap(
                self.generation,
                entry["url"],
                None,
                {},
                (
                    "transient provider job failure after retries: "
                    if retryable
                    else "transient failure: "
                )
                + str(failure.value),
                complete=False,
                retry_seconds=300 if retryable else None,
                pause_seconds=None if retryable else 300,
            )
        if retryable:
            yield from self.start_requests()
        else:
            self.stopped = True
