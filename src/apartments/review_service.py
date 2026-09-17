"""Cloud-side rental review queries and explicit, capture-scoped human overlays."""

from __future__ import annotations

import hashlib
import json
import math
import time
import uuid
from copy import deepcopy
from pathlib import Path

import duckdb
import jsonpatch
from jsonpointer import JsonPointer, JsonPointerException

from .corrections import validate_edit
from .review_ledger import GENESIS, ReviewConflict, ReviewLedger, _ids

STAGES = [
    {
        "id": "identity",
        "label": "1 · Identity",
        "description": "Check building and unit labels before joining observations.",
        "issues": ["unit_missing", "unit_generic", "all"],
    },
    {
        "id": "prices",
        "label": "2 · Prices & dates",
        "description": "Inspect asking prices and source history. These are not signed leases.",
        "issues": ["bad_history_price", "asking_missing", "all"],
    },
    {
        "id": "layout",
        "label": "3 · Bedrooms & bathrooms",
        "description": "Check impossible values and disagreements across captures.",
        "issues": [
            "bad_bedrooms",
            "bad_bathrooms",
            "bad_rooms",
            "layout_disagreement",
            "all",
        ],
    },
    {
        "id": "size",
        "label": "4 · Square footage",
        "description": "Separate missing source values from parsing errors and genuine disagreements.",
        "issues": ["size_missing", "size_disagreement", "all"],
    },
    {
        "id": "amenities",
        "label": "5 · Other attributes",
        "description": "Review features, amenities, views and floor information in the source payload.",
        "issues": ["features_missing", "amenities_missing", "all"],
    },
]
ISSUES = {
    "all": ("All rental observations", "TRUE"),
    "unit_missing": (
        "Missing unit label",
        "r.unit_label IS NULL OR trim(r.unit_label)=''",
    ),
    "unit_generic": (
        "Possibly generic unit label",
        "regexp_matches(lower(coalesce(r.unit_label,'')), 'bedroom|studio|[0-9] *br|layout|floorplan')",
    ),
    "bad_history_price": (
        "History has missing/nonpositive price",
        "EXISTS(SELECT 1 FROM bad_prices b WHERE b.snapshot_id=r.snapshot_id)",
    ),
    "asking_missing": (
        "Missing/nonpositive advertised price",
        "r.asking_price IS NULL OR r.asking_price<=0",
    ),
    "bad_bedrooms": (
        "Bedroom count outside review range",
        "r.bedrooms IS NULL OR r.bedrooms<0 OR r.bedrooms>20",
    ),
    "bad_bathrooms": (
        "Bathroom count outside review range",
        "r.bathrooms IS NULL OR r.bathrooms<=0 OR r.bathrooms>20",
    ),
    "bad_rooms": (
        "Room count outside review range",
        "r.room_count IS NULL OR r.room_count<=0 OR r.room_count>20",
    ),
    "layout_disagreement": (
        "Layout differs across source-label captures",
        "EXISTS(SELECT 1 FROM label_groups g WHERE g.building_slug=r.building_slug AND g.unit_label=r.unit_label AND (g.bed_values>1 OR g.bath_values>1))",
    ),
    "size_missing": ("Missing square footage", "r.square_feet IS NULL"),
    "size_disagreement": (
        "Size differs across source-label captures",
        "EXISTS(SELECT 1 FROM label_groups g WHERE g.building_slug=r.building_slug AND g.unit_label=r.unit_label AND g.size_values>1)",
    ),
    "features_missing": (
        "Missing feature metadata",
        "r.features_json IS NULL OR r.features_json IN ('null','[]','{}')",
    ),
    "amenities_missing": (
        "Missing amenity metadata",
        "r.amenities_json IS NULL OR r.amenities_json IN ('null','[]','{}')",
    ),
}
FIELDS = {
    "building_slug",
    "unit_label",
    "bedrooms",
    "bathrooms",
    "square_feet",
    "room_count",
    "asking_price",
    "features",
    "amenities",
}
SUMMARY = "snapshot_id,url,listing_id,building_slug,unit_label,bedrooms,bathrooms,square_feet,room_count,collected_at,asking_price"


def rows(cursor):
    names = [c[0] for c in cursor.description]
    return [dict(zip(names, r)) for r in cursor.fetchall()]


def decode(value):
    return json.loads(value) if value else None


class ReviewService:
    def __init__(self, root, state):
        self.root = Path(root)
        self.state = Path(state)
        self.state.mkdir(parents=True, exist_ok=True)
        if not (self.root / "complete.json").exists():
            raise ValueError("Dataset has not finished validation")
        self.dataset = self.root.name
        self.ledger = ReviewLedger(self.state / "review-ledger.jsonl", self.dataset)
        self.db = duckdb.connect(config={"memory_limit": "768MB", "threads": "2"})
        for table in ("listing_observations", "event_mentions"):
            paths = [str(p) for p in sorted((self.root / table).glob("*.parquet"))]
            self.db.read_parquet(paths).create_view(table)
        self.db.execute(
            """CREATE TEMP TABLE rental AS SELECT snapshot_id,url,listing_id,building_slug,unit_label,bedrooms,bathrooms,square_feet,room_count,collected_at,features_json,amenities_json,try_cast(json_extract_string(pricing_json,'$.price') AS DOUBLE) asking_price FROM listing_observations WHERE listing_type='rental' AND url NOT LIKE '%/media_gallery%'"""
        )
        self.db.execute(
            "CREATE TEMP TABLE label_groups AS SELECT building_slug,unit_label,count(DISTINCT bedrooms) bed_values,count(DISTINCT bathrooms) bath_values,count(DISTINCT square_feet) size_values FROM rental WHERE unit_label IS NOT NULL GROUP BY building_slug,unit_label"
        )
        self.db.execute(
            "CREATE TEMP TABLE bad_prices AS SELECT DISTINCT snapshot_id FROM event_mentions WHERE event_category='rental' AND (price IS NULL OR price<=0)"
        )
        self._overview = None

    def close(self):
        self.db.close()

    def selection(self, args, events=None):
        issue = args.get("issue", "all")
        if issue not in ISSUES:
            raise ValueError("Unknown issue")
        sql = "(" + ISSUES[issue][1] + ")"
        params = []
        building = str(args.get("building") or "")
        search = str(args.get("search") or "")
        if len(search) > 200:
            raise ValueError("Search is too long")
        if building:
            sql += " AND r.building_slug=?"
            params.append(building)
        if search:
            sql += " AND concat_ws(' ',r.building_slug,r.unit_label,r.listing_id,r.url) ILIKE ?"
            params.append("%" + search + "%")
        stage = args.get("stage", "identity")
        status = args.get("review_status", "all")
        if stage not in {x["id"] for x in STAGES}:
            raise ValueError("Unknown review stage")
        if status not in ("all", "unreviewed", "confirmed", "needs_attention"):
            raise ValueError("Unknown review status")
        if status != "all":
            latest = self.latest_reviews(events)
            ids = [
                sid
                for (sid, st), event in latest.items()
                if st == stage
                and (status == "unreviewed" or event["decision"] == status)
            ]
            sql += (
                " AND r.snapshot_id NOT IN (SELECT unnest(?))"
                if status == "unreviewed"
                else " AND r.snapshot_id IN (SELECT unnest(?))"
            )
            params.append(ids)
        return sql, params

    def latest_reviews(self, events=None):
        return {
            (e["snapshot_id"], e["stage"]): e
            for e in (self.ledger.events() if events is None else events)
            if e["action"] == "review"
        }

    def ids(self, args, maximum=5000):
        where, params = self.selection(args)
        result = [
            x[0]
            for x in self.db.execute(
                f"SELECT r.snapshot_id FROM rental r WHERE {where} ORDER BY r.snapshot_id LIMIT ?",
                [*params, maximum + 1],
            ).fetchall()
        ]
        if len(result) > maximum:
            raise ValueError(
                f"This selection exceeds {maximum:,} observations. Narrow the building/search filter; file a parser issue for a wider class."
            )
        if not result:
            raise ValueError("No matching rental observations")
        return result

    def overview(self, args=None):
        if self._overview is None:
            counts = {
                key: self.db.execute(
                    "SELECT count(*) FROM rental r WHERE " + predicate
                ).fetchone()[0]
                for key, (_, predicate) in ISSUES.items()
            }
            stages = [
                dict(
                    stage,
                    issues=[
                        {"id": k, "label": ISSUES[k][0], "count": counts[k]}
                        for k in stage["issues"]
                    ],
                )
                for stage in STAGES
            ]
            self._overview = {
                "dataset": self.dataset,
                "stages": stages,
                "buildings": rows(
                    self.db.execute(
                        "SELECT building_slug AS slug,count(*) AS count FROM rental GROUP BY building_slug ORDER BY building_slug"
                    )
                ),
                "rental_observations": counts["all"],
                "source_based_counts": True,
            }
        result = deepcopy(self._overview)
        events = self.ledger.events()
        latest = self.latest_reviews(events)
        result["review_counts"] = {
            k: sum(e["action"] == v for e in events)
            for k, v in [
                ("reviews", "review"),
                ("parser_issues", "parser_issue"),
                ("corrections", "correct"),
            ]
        }
        for decision in ("confirmed", "needs_attention"):
            result["review_counts"][decision] = sum(
                e["decision"] == decision for e in latest.values()
            )
        for stage in result["stages"]:
            selected = [e for (_, st), e in latest.items() if st == stage["id"]]
            stage["progress"] = {
                key: sum(e["decision"] == key for e in selected)
                for key in ("confirmed", "needs_attention")
            }
            stage["progress"]["unreviewed"] = result["rental_observations"] - len(
                selected
            )
        result["ledger_revision"] = events[-1]["hash"] if events else GENESIS
        return result

    def observations(self, args):
        ledger_events = self.ledger.events()
        where, params = self.selection(args, ledger_events)
        # Each issue chip describes that issue under the other active filters.
        scope, scope_params = self.selection({**args, "issue": "all"}, ledger_events)
        stage = next(s for s in STAGES if s["id"] == args.get("stage", "identity"))
        counts = self.db.execute(
            "SELECT " + ",".join(
                f"count(*) FILTER (WHERE {ISSUES[key][1]})" for key in stage["issues"]
            ) + f" FROM rental r WHERE {scope}", scope_params
        ).fetchone()
        issue_counts = dict(zip(stage["issues"], counts))
        limit = max(1, min(100, int(args.get("limit", 25))))
        offset = max(0, int(args.get("offset", 0)))
        total = self.db.execute(
            f"SELECT count(*) FROM rental r WHERE {where}", params
        ).fetchone()[0]
        offset = min(offset, max(0, ((total - 1) // limit) * limit))
        data = rows(
            self.db.execute(
                f"SELECT {SUMMARY} FROM rental r WHERE {where} ORDER BY building_slug,unit_label,snapshot_id LIMIT ? OFFSET ?",
                [*params, limit, offset],
            )
        )
        latest = self.latest_reviews(ledger_events)
        from .unit_identity import UnitIdentityLedger, identity_map
        identities = identity_map(UnitIdentityLedger(self.state / 'unit-identities.jsonl', self.dataset).events())
        for row in data:
            row['unit_id'] = identities.get(row['listing_id'], f"streeteasy:rental:{row['listing_id']}")
            row["review"] = latest.get(
                (row["snapshot_id"], args.get("stage", "identity"))
            )
            row["review_status"] = (
                row["review"]["decision"] if row["review"] else "unreviewed"
            )
            row["correction_count"] = sum(
                e["action"] == "correct"
                and row["snapshot_id"] in e["snapshot_ids"]
                and not any(
                    x["action"] == "retract" and x["correction_id"] == e["id"]
                    for x in ledger_events
                )
                for e in ledger_events
            )
        return {
            "rows": data,
            "total": total,
            "offset": offset,
            "limit": limit,
            "source_based": True,
            "issue_counts": issue_counts,
            "ledger_revision": ledger_events[-1]["hash"] if ledger_events else GENESIS,
        }

    def raw_batch(self, ids):
        # One parquet scan per preview, rather than one scan per affected observation.
        if self.db.execute(
            "SELECT count(*) FROM rental WHERE snapshot_id IN (SELECT unnest(?))", [ids]
        ).fetchone()[0] != len(ids):
            raise ValueError("Rental observation not found")
        cursor = self.db.execute(
            f"SELECT {','.join('r.' + k for k in SUMMARY.split(','))},r.features_json,r.amenities_json,l.raw_listing_json FROM rental r JOIN listing_observations l USING(snapshot_id) WHERE r.snapshot_id IN (SELECT unnest(?)) ORDER BY r.snapshot_id",
            [ids],
        )
        names = [c[0] for c in cursor.description]
        while (values := cursor.fetchone()) is not None:
            row = dict(zip(names, values))
            raw = {k: row[k] for k in FIELDS if k not in ("features", "amenities")}
            raw["features"] = decode(row.pop("features_json"))
            raw["amenities"] = decode(row.pop("amenities_json"))
            raw["archive_listing"] = decode(row.pop("raw_listing_json"))
            yield row, raw

    def raw(self, sid):
        record = rows(
            self.db.execute(
                f"SELECT {SUMMARY},features_json,amenities_json FROM rental WHERE snapshot_id=?",
                [int(sid)],
            )
        )
        if not record:
            raise ValueError("Rental observation not found")
        row = record[0]
        raw = {k: row[k] for k in FIELDS if k not in ("features", "amenities")}
        raw["features"] = decode(row.pop("features_json"))
        raw["amenities"] = decode(row.pop("amenities_json"))
        raw["archive_listing"] = decode(
            self.db.execute(
                "SELECT raw_listing_json FROM listing_observations WHERE snapshot_id=?",
                [int(sid)],
            ).fetchone()[0]
        )
        return row, raw

    def observation(self, args):
        sid = int(args["snapshot_id"])
        row, raw = self.raw(sid)
        corrected, evidence = self.ledger.apply(raw, sid)
        comparisons = []
        if row["unit_label"]:
            comparisons = rows(
                self.db.execute(
                    f"SELECT {SUMMARY} FROM rental WHERE building_slug=? AND unit_label=? ORDER BY collected_at,snapshot_id LIMIT 100",
                    [row["building_slug"], row["unit_label"]],
                )
            )
        history = self.events({"snapshot_id": sid})
        from .unit_identity import UnitIdentityLedger, resolve_unit
        unit_id = resolve_unit(row['listing_id'], UnitIdentityLedger(
            self.state / 'unit-identities.jsonl', self.dataset).events())
        return {
            "dataset": self.dataset,
            "unit_id": unit_id,
            "row": row,
            "raw": raw,
            "corrected": corrected,
            "evidence": evidence,
            "events": history["events"],
            "event_total": history["total"],
            "comparisons": comparisons,
            "comparison_limit": 100,
            "reviews": [
                e
                for e in self.ledger.events()
                if e["action"] == "review" and e["snapshot_id"] == sid
            ],
            "ledger_revision": self.ledger.revision(),
        }

    def events(self, args):
        sid = int(args["snapshot_id"])
        self._exists(sid)
        offset = max(0, int(args.get("offset", 0)))
        limit = max(1, min(200, int(args.get("limit", 100))))
        total = self.db.execute(
            "SELECT count(*) FROM event_mentions WHERE snapshot_id=? AND event_category='rental'",
            [sid],
        ).fetchone()[0]
        events = rows(
            self.db.execute(
                "SELECT episode_index,event_index,event_listing_id,event_date,price,status,event_json FROM event_mentions WHERE snapshot_id=? AND event_category='rental' ORDER BY episode_index,event_index LIMIT ? OFFSET ?",
                [sid, limit, offset],
            )
        )
        _, raw = self.raw(sid)
        ledger_events = self.ledger.events()
        corrected, _ = self.ledger.apply(raw, sid, events=ledger_events)
        for event in events:
            self._event_price(event, raw, corrected)
        return {"events": events, "total": total, "offset": offset, "limit": limit,
                "ledger_revision": ledger_events[-1]["hash"] if ledger_events else GENESIS}

    @staticmethod
    def _event_price(event, raw, corrected):
        """Resolve a price overlay only when the archived occurrence still matches."""
        path = (f"/archive_listing/propertyHistory/{event['episode_index']}"
                f"/rentalEventsOfInterest/{event['event_index']}")
        event["raw_price"] = event["price"]
        event["price_editable"] = False
        event["price_corrected"] = False
        try:
            original = JsonPointer(path).resolve(raw)
            current = JsonPointer(path).resolve(corrected)
            episode_path = f"/archive_listing/propertyHistory/{event['episode_index']}/listingId"
            if original != decode(event["event_json"]):
                raise ValueError("Archived occurrence does not match its source history")
            if (not isinstance(current, dict)
                or {k: v for k, v in current.items() if k != "price"}
                   != {k: v for k, v in original.items() if k != "price"}
                or JsonPointer(episode_path).resolve(raw)
                   != JsonPointer(episode_path).resolve(corrected)):
                raise ValueError("History structure changed; inspect the existing corrections")
            price = current.get("price")
            if price is not None:
                if isinstance(price, bool):
                    raise ValueError("History price is not numeric")
                price = float(price)
                if not math.isfinite(price):
                    raise ValueError("History price is not finite")
            event["price"] = price
            event["price_corrected"] = price != event["raw_price"]
            event["price_editable"] = True
            event["price_path"] = path + "/price"
        except (JsonPointerException, ValueError, TypeError) as error:
            event["price_edit_error"] = str(error)

    def event_price_preview(self, args):
        sid = args.get("snapshot_id")
        episode = args.get("episode_index")
        index = args.get("event_index")
        if any(type(value) is not int or value < 0 for value in (sid, episode, index)):
            raise ValueError("Choose a specific history occurrence")
        price = args.get("price")
        if "price" not in args or (price is not None and (
            isinstance(price, bool) or not isinstance(price, (int, float))
            or not math.isfinite(price) or price <= 0
        )):
            raise ValueError("Price must be a positive number, or null for unknown")
        self._exists(sid)
        found = rows(self.db.execute(
            "SELECT episode_index,event_index,event_listing_id,event_date,price,status,event_json "
            "FROM event_mentions WHERE snapshot_id=? AND event_category='rental' "
            "AND episode_index=? AND event_index=?", [sid, episode, index]
        ))
        if len(found) != 1:
            raise ValueError("History occurrence not found or ambiguous")
        _, raw = self.raw(sid)
        ledger_events = self.ledger.events()
        revision = ledger_events[-1]["hash"] if ledger_events else GENESIS
        corrected, _ = self.ledger.apply(raw, sid, events=ledger_events)
        event = found[0]
        self._event_price(event, raw, corrected)
        if not event["price_editable"]:
            raise ValueError(event["price_edit_error"])
        if "expected_price" not in args or args["expected_price"] != event["price"]:
            raise ReviewConflict("History price changed; reopen this observation")
        if price == event["price"]:
            raise ValueError("Enter a different price")
        result = self.preview({"snapshot_id": sid, "ledger_revision": revision,
                               "patch": [{"op": "add", "path": event["price_path"], "value": price}]})
        result["event"] = {"snapshot_id": sid, "episode_index": episode, "event_index": index,
                           "event_date": event["event_date"], "status": event["status"],
                           "event_listing_id": event["event_listing_id"],
                           "raw_price": event["raw_price"], "before": event["price"], "after": price}
        return result

    def _exists(self, sid):
        if not self.db.execute(
            "SELECT 1 FROM rental WHERE snapshot_id=?", [sid]
        ).fetchone():
            raise ValueError("Rental observation not found")

    def preview(self, args, cohort=False):
        if cohort:
            field = args.get("field")
            if field not in FIELDS:
                raise ValueError("Choose a supported attribute for a class correction")
            patch = [{"op": "replace", "path": "/" + field, "value": args.get("value")}]
            ids = self.ids(args)
        else:
            ids = [int(args["snapshot_id"])]
            patch = args.get("patch")
        validate_edit(
            {
                "target": {"source": "streeteasy", "capture_id": "review"},
                "validity": {"all_time": True},
                "patch": patch,
            }
        )
        if len(json.dumps(patch)) > 65536:
            raise ValueError("Patch exceeds 64 KiB")
        events = self.ledger.events()
        revision = events[-1]["hash"] if events else GENESIS
        if args.get("ledger_revision", revision) != revision:
            raise ReviewConflict("Reviews changed; preview the correction again")
        examples = []
        for row, raw in self.raw_batch(ids):
            sid = row["snapshot_id"]
            current, _ = self.ledger.apply(raw, sid, events=events)
            try:
                proposed = jsonpatch.apply_patch(current, patch, in_place=False)
            except (
                jsonpatch.JsonPatchException,
                JsonPointerException,
                KeyError,
                TypeError,
            ) as e:
                raise ValueError("Patch cannot apply: " + str(e)) from e
            self.validate_document(proposed)
            if len(examples) < 8:
                examples.append(
                    {
                        "row": row,
                        "raw": raw,
                        "before": current,
                        "corrected": proposed,
                        "diff": jsonpatch.make_patch(current, proposed).patch,
                    }
                )
        token = uuid.uuid4().hex
        record = {
            "dataset": self.dataset,
            "ids": ids,
            "patch": patch,
            "revision": revision,
            "created_at": time.time(),
            "selection": {
                k: args.get(k)
                for k in ("issue", "building", "search", "stage", "review_status")
            },
            "selection_hash": hashlib.sha256(json.dumps(ids).encode()).hexdigest(),
        }
        directory = self.state / "previews"
        directory.mkdir(exist_ok=True)
        (directory / (token + ".json")).write_text(json.dumps(record))
        first = examples[0]
        return {
            "token": token,
            "count": len(ids),
            "affected_count": len(ids),
            "examples": [
                dict(
                    e["row"],
                    before=e["before"],
                    corrected=e["corrected"],
                    diff=e["diff"],
                )
                for e in examples
            ],
            "raw": first["raw"],
            "corrected": first["corrected"],
            "diff": first["diff"],
            "description": f"{len(ids):,} frozen capture observations; source records remain unchanged.",
            "ledger_revision": revision,
        }

    @staticmethod
    def validate_document(doc):
        if not isinstance(doc, dict):
            raise ValueError("Correction must preserve the observation document")  # noqa: TRY004
        for field in (
            "bedrooms",
            "bathrooms",
            "square_feet",
            "room_count",
            "asking_price",
        ):
            val = doc.get(field)
            if val is not None and (
                isinstance(val, bool)
                or not isinstance(val, (int, float))
                or not math.isfinite(val)
            ):
                raise ValueError(field + " must be a number or null")
        for field in ("building_slug", "unit_label"):
            if doc.get(field) is not None and not isinstance(doc[field], str):
                raise ValueError(field + " must be text or null")

    def apply_preview(self, args):
        token = str(args.get("token", ""))
        if len(token) != 32 or any(c not in "0123456789abcdef" for c in token):
            raise ValueError("Invalid preview token")
        path = self.state / "previews" / (token + ".json")
        if not path.exists():
            raise ValueError("Preview not found; preview the edit again")
        record = json.loads(path.read_text())
        if record["dataset"] != self.dataset:
            raise ValueError("Dataset mismatch")
        if time.time() - record["created_at"] > 3600 and not any(
            e.get("request_id") == token for e in self.ledger.events()
        ):
            raise ValueError("Preview expired; preview again")
        return self.ledger.correct(
            record["ids"],
            record["patch"],
            author=args.get("author", ""),
            reason=args.get("reason", ""),
            expected_revision=record["revision"],
            request_id=token,
        )

    def identity_confirm(self, args):
        ids = _ids(args.get("snapshot_ids"))
        if args.get("stage") != "identity":
            raise ValueError("Bulk confirmation is available in the Identity stage")
        count = self.db.execute(
            "SELECT count(*) FROM rental WHERE snapshot_id IN (SELECT unnest(?))", [ids]
        ).fetchone()[0]
        if count != len(ids):
            raise ValueError("Selection contains an unknown rental observation")
        return self.ledger.confirm_identity_batch(
            ids, args.get("author", ""), "", {"mode": "selected_rows"},
            args.get("ledger_revision"), args.get("request_id"),
        )

    def review(self, args):
        sid = int(args["snapshot_id"])
        self._exists(sid)
        return self.ledger.record_review(
            sid,
            args.get("stage", ""),
            args.get("decision", ""),
            args.get("note", ""),
            args.get("author", ""),
        )

    def parser_issue(self, args):
        return self.ledger.record_parser_issue(
            {
                k: args.get(k)
                for k in ("issue", "building", "search", "stage", "review_status")
            },
            args.get("field", ""),
            args.get("note", ""),
            args.get("author", ""),
            self.ids(args, 100000),
        )

    def retract(self, args):
        events = self.ledger.events()
        revision = events[-1]["hash"] if events else GENESIS
        correction = next(
            (
                e
                for e in events
                if e["action"] == "correct" and e["id"] == args.get("id")
            ),
            None,
        )
        if correction is None:
            raise ValueError("Unknown correction")
        proposed = [*events, {"action": "retract", "correction_id": correction["id"]}]
        for row, raw in self.raw_batch(correction["snapshot_ids"]):
            try:
                doc, _ = self.ledger.apply(raw, row["snapshot_id"], events=proposed)
                self.validate_document(doc)
            except ValueError as e:
                raise ValueError(
                    "Undo would break a later correction; undo dependent corrections first. "
                    + str(e)
                ) from e
        return self.ledger.retract(
            args.get("id", ""),
            args.get("author", ""),
            args.get("reason", ""),
            expected_revision=revision,
        )

    def dispatch(self, action, args=None):
        args = args or {}
        if action in {'unit_candidates', 'unit_inspect', 'unit_merge', 'unit_undo', 'unit_mapping'}:
            from .unit_merge_service import UnitMergeService
            if not hasattr(self, '_unit_service'):
                self._unit_service = UnitMergeService(self)
            return getattr(self._unit_service, action.removeprefix('unit_'))(args)
        routes = {
            "overview": self.overview,
            "observations": self.observations,
            "observation": self.observation,
            "events": self.events,
            "event_price_preview": self.event_price_preview,
            "preview": self.preview,
            "cohort_preview": lambda x: self.preview(x, True),
            "apply": self.apply_preview,
            "review": self.review,
            "identity_confirm": self.identity_confirm,
            "parser_issue": self.parser_issue,
            "retract": self.retract,
            "activity": lambda x: self.ledger.activity(),
        }
        if action not in routes:
            raise ValueError("Unknown review operation")
        return routes[action](args)
