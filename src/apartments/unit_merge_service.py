"""Manual rental-listing identity resolution and canonical unit histories."""

from __future__ import annotations

import hashlib
import fcntl
import json
import re
import uuid
from collections import defaultdict
from itertools import combinations

from .corrections import canonical
from .review_ledger import GENESIS, ReviewConflict, listing_exclusions
from .unit_identity import (
    UnitIdentityLedger,
    expand_ids,
    identity_map,
    listing_ids,
    active_decisions,
    merge_decisions,
    active_separations,
    separation_conflicts,
    separated_pairs,
)


def records(cursor):
    keys = [c[0] for c in cursor.description]
    return [dict(zip(keys, row)) for row in cursor.fetchall()]


def search_text(value):
    value = re.sub(r"(?<=\d)(?:st|nd|rd|th)\b", "", value.casefold())
    return " ".join(re.findall(r"[a-z0-9]+", value))


class UnitMergeService:
    def __init__(self, service):
        self.s = service
        self.ledger = UnitIdentityLedger(
            service.state / "unit-identities.jsonl", service.dataset
        )
        self._cache = None
        self._assessments = None
        self._source = None

    def catalog(self, review_events, identity_events):
        revision = review_events[-1]["hash"] if review_events else GENESIS
        key = (revision, self.ledger.revision(identity_events))
        if self._cache and self._cache[0] == key:
            return self._cache[1]
        rows = records(
            self.s.db.execute(
                "SELECT snapshot_id,listing_id,building_slug,unit_label FROM rental ORDER BY snapshot_id"
            )
        )
        by_sid = {row["snapshot_id"]: row for row in rows}
        retracted = {
            e["correction_id"] for e in review_events if e["action"] == "retract"
        }
        corrected_ids = {
            sid
            for e in review_events
            if e["action"] == "correct"
            and e["id"] not in retracted
            and any(p["path"] in {"/building_slug", "/unit_label"} for p in e["patch"])
            for sid in e["snapshot_ids"]
            if sid in by_sid
        }
        if corrected_ids:
            for row, raw in self.s.raw_batch(sorted(corrected_ids)):
                corrected, _ = self.s.ledger.apply(
                    raw, row["snapshot_id"], events=review_events
                )
                by_sid[row["snapshot_id"]].update(
                    building_slug=corrected.get("building_slug"),
                    unit_label=corrected.get("unit_label"),
                )
        mapping = identity_map(identity_events)
        listings = {}
        for row in rows:
            lid = row["listing_id"]
            if not lid:
                continue
            item = listings.setdefault(
                lid,
                {
                    "listing_id": lid,
                    "unit_id": mapping.get(lid, f"streeteasy:rental:{lid}"),
                    "captures": [],
                },
            )
            item["captures"].append(row)
        self._cache = (key, listings)
        return listings

    def assessments(self, catalog, review_events, identity_events):
        from .unit_source import SourceEvidence

        if self._source is None:
            self._source = SourceEvidence(self.s)
        key = self._cache[0]
        if self._assessments and self._assessments[0] == key:
            return self._assessments[1]
        excluded = listing_exclusions(review_events)
        catalog = {lid: row for lid, row in catalog.items() if lid not in excluded}
        labels = defaultdict(set)
        canonical_members = defaultdict(set)
        history_members = defaultdict(set)
        latest_members = defaultdict(set)
        latest_labels = defaultdict(set)
        for lid, listing in catalog.items():
            for c in listing["captures"]:
                sid = c["snapshot_id"]
                building, label = c["building_slug"], c["unit_label"]
                if (
                    building
                    and label
                    and label.strip()
                    and not re.search(
                        r"bedroom|studio|[0-9] *br|layout|floorplan", label, re.I
                    )
                ):
                    labels[(building, label)].add(lid)
                target = self._source.latest.get(sid)
                if target:
                    latest_members[target].add(lid)
                    latest_labels[target].add((building, label))
                    latest_labels[target].add(
                        getattr(self._source, "source_labels", {}).get(
                            sid, (building, label)
                        )
                    )
                page = self._source.pages.get(sid, {}).get("canonical_url")
                if page:
                    canonical_members[page].add(lid)
                for target in self._source.history.get(sid, set()):
                    history_members[target].add(lid)
        retracted = {
            e["correction_id"] for e in review_events if e["action"] == "retract"
        }
        corrected = {
            sid
            for e in review_events
            if e["action"] == "correct"
            and e["id"] not in retracted
            and any(
                p["path"] in {"/building_slug", "/unit_label", "/archive_listing"}
                or p["path"].startswith(
                    (
                        "/archive_listing/latestListing",
                        "/archive_listing/propertyDetails/address",
                    )
                )
                for p in e["patch"]
            )
            for sid in e["snapshot_ids"]
        }
        reserved = {
            lid for e in merge_decisions(identity_events) for lid in e["listing_ids"]
        }
        reserved.update(
            lid for e in active_separations(identity_events) for lid in e["listing_ids"]
        )
        units = defaultdict(set)
        for lid, listing in catalog.items():
            units[listing["unit_id"]].add(lid)
        latest_groups = []
        for target, members in latest_members.items():
            group = set(members)
            if target in catalog:
                group.add(target)
                for c in catalog[target]["captures"]:
                    latest_labels[target].add((c["building_slug"], c["unit_label"]))
                    latest_labels[target].add(
                        getattr(self._source, "source_labels", {}).get(
                            c["snapshot_id"], (c["building_slug"], c["unit_label"])
                        )
                    )
            latest_groups.append(group)

        def components(available, suggestions):
            parent = {lid: lid for lid in available}

            def find(lid):
                while parent[lid] != lid:
                    parent[lid] = parent[parent[lid]]
                    lid = parent[lid]
                return lid

            for members in suggestions:
                members = members & available
                if len(members) > 1:
                    first = next(iter(members))
                    for lid in members:
                        parent[find(lid)] = find(first)
            result = defaultdict(set)
            for lid in available:
                result[find(lid)].add(lid)
            return {tuple(sorted(ids)): ids for ids in result.values() if len(ids) > 1}

        def assess(ids):
            return self._source.assess(
                ids,
                catalog,
                canonical_members,
                history_members,
                corrected,
                reserved,
                latest_members,
                latest_labels,
            )

        # Qualifying shared-latest groups take precedence over weaker label/URL
        # suggestions. Exceptions still form disjoint, reviewable groups.
        primary = components(set(catalog), [*latest_groups, *units.values()])
        assessments = {ids: assess(members) for ids, members in primary.items()}
        supported = {
            ids: primary[ids] for ids, value in assessments.items() if value["eligible"]
        }
        assigned = {lid for ids in supported for lid in ids}
        remaining = components(
            set(catalog) - assigned,
            [
                *latest_groups,
                *units.values(),
                *labels.values(),
                *canonical_members.values(),
            ],
        )
        groups = {**supported, **remaining}
        assessments = {ids: assess(members) for ids, members in groups.items()}
        self._candidate_groups = groups
        self._assessments = (key, assessments)
        return assessments

    def candidates(self, args, *, all_rows=False):
        review_events, identity_events = self.s.ledger.events(), self.ledger.events()
        catalog = self.catalog(review_events, identity_events)
        assessments = self.assessments(catalog, review_events, identity_events)
        queue = args.get("queue", "all")
        if queue not in {"all", "supported", "review", "label_conflicts"}:
            raise ValueError("Unknown identity queue")
        basis = {e["unit_id"]: e["basis"] for e in active_decisions(identity_events)}
        search = str(args.get("search", "")).strip().casefold()
        if len(search) > 200:
            raise ValueError("Search is too long")
        building = str(args.get("building") or "")
        mode = args.get("mode", "candidates")
        if mode not in {"candidates", "merged", "separated"}:
            raise ValueError("Unknown unit list")
        sort = args.get("sort", "listing_count")
        direction = args.get("direction", "desc")
        if sort not in {"building", "listing_count"} or direction not in {
            "asc",
            "desc",
        }:
            raise ValueError("Unknown sort order")
        groups = defaultdict(set)
        if mode == "candidates":
            groups = self._candidate_groups
        elif mode == "separated":
            groups = {
                e["id"]: set(e["listing_ids"]) & set(catalog)
                for e in active_separations(identity_events)
            }
        else:
            for lid, unit_id in identity_map(identity_events).items():
                if lid in catalog:
                    groups[unit_id].add(lid)
        result = []
        counts = {"supported": 0, "review": 0, "label_conflicts": 0}
        separate = separated_pairs(identity_events, identity_map(identity_events))
        for key, ids in groups.items():
            if not ids:
                continue
            units = {catalog[lid]["unit_id"] for lid in ids}
            if mode == "candidates" and len(units) < 2:
                continue
            if mode == "candidates" and all(
                tuple(sorted(pair)) in separate for pair in combinations(units, 2)
            ):
                continue
            if args.get("exclude_unit_id") in units:
                continue
            captures = [c for lid in ids for c in catalog[lid]["captures"]]
            labels = sorted(
                {(c["building_slug"] or "", c["unit_label"] or "") for c in captures}
            )
            text = (
                " ".join(b + " " + u for b, u in labels) + " " + " ".join(sorted(ids))
            )
            if building and not any(b == building for b, _ in labels):
                continue
            if search and not all(
                word in search_text(text) for word in search_text(search).split()
            ):
                continue
            assessment = assessments.get(key) if mode == "candidates" else None
            category = (
                "supported" if assessment and assessment["eligible"] else "review"
            )
            if mode == "candidates":
                counts[category] += 1
                has_label_conflict = bool(
                    assessment and assessment.get("latest_label_conflicts")
                )
                if has_label_conflict:
                    counts["label_conflicts"] += 1
                if queue == "label_conflicts":
                    if not has_label_conflict:
                        continue
                elif queue != "all" and queue != category:
                    continue
            result.append(
                {
                    "assessment": assessment,
                    "basis": "separate" if mode == "separated" else basis.get(key),
                    "building": labels[0][0],
                    "unit_label": labels[0][1],
                    "unit_id": key if mode == "merged" else None,
                    "listing_ids": sorted(ids),
                    "listing_count": len(ids),
                    "capture_count": len(captures),
                    "identities": len(units),
                }
            )
        result.sort(key=lambda r: (r["building"], r["unit_label"], r["listing_ids"]))
        if sort == "listing_count":
            # Stable tie order, applied to all matches before selecting a page.
            result.sort(key=lambda r: r["listing_count"], reverse=direction == "desc")
        elif direction == "desc":
            result.reverse()
        limit = (
            max(1, len(result))
            if all_rows
            else min(100, max(1, int(args.get("limit", 25))))
        )
        offset = max(0, int(args.get("offset", 0)))
        offset = min(offset, max(0, ((len(result) - 1) // limit) * limit))
        return {
            "rows": result[offset : offset + limit],
            "total": len(result),
            "offset": offset,
            "limit": limit,
            "sort": sort,
            "direction": direction,
            "identity_revision": self.ledger.revision(identity_events),
            "review_revision": review_events[-1]["hash"] if review_events else GENESIS,
            "counts": counts,
            "source_ready": self._source.error is None,
        }

    def inspect(self, args):
        identity_events, review_events = self.ledger.events(), self.s.ledger.events()
        catalog = self.catalog(review_events, identity_events)
        if args.get("unit_id"):
            ids = sorted(
                lid for lid, row in catalog.items() if row["unit_id"] == args["unit_id"]
            )
            if not ids:
                raise ValueError("Unit not found")
        else:
            supplied = args.get("listing_ids")
            ids = listing_ids(
                supplied.split(",") if isinstance(supplied, str) else supplied
            )
        ids = expand_ids(ids, identity_events)
        if len(ids) > 200:
            raise ValueError("Compare at most 200 listing IDs at a time")
        if any(lid not in catalog for lid in ids):
            raise ValueError("Selection contains an unknown rental listing ID")
        capture_ids = sorted(
            {c["snapshot_id"] for lid in ids for c in catalog[lid]["captures"]}
        )
        if len(capture_ids) > 1000:
            raise ValueError("Selection exceeds 1,000 captures; narrow the comparison")
        excluded = listing_exclusions(review_events)
        documents, observations = {}, []
        fields = (
            "building_slug",
            "unit_label",
            "bedrooms",
            "bathrooms",
            "square_feet",
            "room_count",
            "asking_price",
        )
        for row, raw in self.s.raw_batch(capture_ids):
            corrected, evidence = self.s.ledger.apply(
                raw, row["snapshot_id"], events=review_events
            )
            documents[row["snapshot_id"]] = (raw, corrected)
            observations.append(
                {
                    **row,
                    "exclusion": excluded.get(row["listing_id"]),
                    "attributes": {
                        k: v for k, v in corrected.items() if k != "archive_listing"
                    },
                    "raw_attributes": {
                        k: v for k, v in raw.items() if k != "archive_listing"
                    },
                    "correction_ids": [e["id"] for e in evidence],
                }
            )
        history = records(
            self.s.db.execute(
                "SELECT snapshot_id,episode_index,event_index,event_listing_id,event_date,price,status,event_json "
                "FROM event_mentions WHERE snapshot_id IN (SELECT unnest(?)) AND event_category='rental' "
                "ORDER BY event_date, snapshot_id,episode_index,event_index LIMIT 100001",
                [capture_ids],
            )
        )
        if len(history) > 100000:
            raise ValueError(
                "History comparison exceeds 100,000 mentions; narrow the selection"
            )
        combined, versions = {}, defaultdict(set)
        source_listings = {o["snapshot_id"]: o["listing_id"] for o in observations}
        for event in history:
            sid = event["snapshot_id"]
            self.s._event_price(event, *documents[sid])
            event["excluded"] = (
                source_listings[sid] in excluded
                or event["event_listing_id"] in excluded
            )
            source = json.loads(event["event_json"])
            # Exact source event equality plus effective price; no date-only deduplication.
            key = canonical(
                [
                    event["event_listing_id"] or ["unknown", sid],
                    source,
                    event["price"],
                    event.get("price_edit_error"),
                ]
            )
            item = combined.setdefault(
                key,
                {
                    k: event[k]
                    for k in (
                        "event_listing_id",
                        "event_date",
                        "price",
                        "raw_price",
                        "status",
                    )
                },
            )
            item["event_id"] = hashlib.sha256(key.encode()).hexdigest()
            item.setdefault("occurrences", []).append(
                {
                    k: event[k]
                    for k in (
                        "snapshot_id",
                        "episode_index",
                        "event_index",
                        "price",
                        "raw_price",
                        "excluded",
                    )
                }
            )
            item["source_event"] = source
            if event.get("price_edit_error"):
                item["overlay_warning"] = event["price_edit_error"]
            versions[
                (event["event_listing_id"], event["event_date"], event["status"])
            ].add(key)
        for key, item in combined.items():
            item["excluded"] = all(o["excluded"] for o in item["occurrences"])
            item["conflicting_version"] = (
                len(
                    versions[
                        (item["event_listing_id"], item["event_date"], item["status"])
                    ]
                )
                > 1
            )
        conflicts = {
            field: sorted(
                {
                    canonical(o["attributes"][field])
                    for o in observations
                    if o["attributes"][field] is not None
                }
            )
            for field in fields
            if field != "asking_price"
        }
        conflicts = {
            k: [json.loads(v) for v in values]
            for k, values in conflicts.items()
            if len(values) > 1
        }
        units = sorted({catalog[lid]["unit_id"] for lid in ids})
        merge = next(
            (
                e
                for e in reversed(active_decisions(identity_events))
                if len(units) == 1 and e["unit_id"] == units[0]
            ),
            None,
        )
        assessments = self.assessments(catalog, review_events, identity_events)
        assessment = assessments.get(tuple(sorted(ids)))
        for observation in observations:
            sid = observation["snapshot_id"]
            observation["identity_evidence"] = {
                **self._source.pages.get(sid, {}),
                "latest_listing_id": self._source.latest.get(sid),
                "history_listing_ids": sorted(
                    x for x in self._source.history.get(sid, set()) if x
                ),
            }
        separate = separated_pairs(identity_events, identity_map(identity_events))
        return {
            "dataset": self.s.dataset,
            "listing_ids": ids,
            "unit_ids": units,
            "unit_id": units[0] if len(units) == 1 else None,
            "listings": [
                {
                    "listing_id": lid,
                    "exclusion": excluded.get(lid),
                    "unit_id": catalog[lid]["unit_id"],
                    "capture_count": len(catalog[lid]["captures"]),
                }
                for lid in ids
            ],
            "observations": observations,
            "attribute_disagreements": conflicts,
            "history": list(combined.values()),
            "history_mentions": len(history),
            "history_events": len(combined),
            "capture_count": len(capture_ids),
            "identity_revision": self.ledger.revision(identity_events),
            "review_revision": review_events[-1]["hash"] if review_events else GENESIS,
            "latest_merge": merge,
            "association_basis": merge["basis"] if merge else None,
            "separations": separation_conflicts(ids, identity_events),
            "kept_separate": len(units) > 1
            and all(tuple(sorted(pair)) in separate for pair in combinations(units, 2)),
            "source_assessment": assessment,
            "source_evidence": merge.get("evidence") if merge else None,
        }

    def merge(self, args):
        return self._identity_decision("merge", args)

    def separate(self, args):
        return self._identity_decision("separate", args)

    def _identity_decision(self, action, args):
        ids = listing_ids(args.get("listing_ids"))
        identity_events = self.ledger.events()
        prior = next(
            (e for e in identity_events if e["request_id"] == args.get("request_id")),
            None,
        )
        if prior is None:
            review_events = self.s.ledger.events()
            if (review_events[-1]["hash"] if review_events else GENESIS) != args.get(
                "review_revision"
            ):
                raise ReviewConflict(
                    "Reviewed attributes changed; compare the listings again"
                )
            catalog = self.catalog(review_events, identity_events)
            if action == "merge" and set(ids) & set(listing_exclusions(review_events)):
                raise ValueError(
                    "Excluded listings cannot be merged; restore the listing first"
                )
            if any(lid not in catalog for lid in ids):
                raise ValueError("Selection contains an unknown rental listing ID")
        return self.ledger.write(
            action,
            listing_ids=ids,
            review_revision=args.get("review_revision"),
            expected_revision=args.get("identity_revision"),
            author=args.get("author"),
            reason=args.get("reason"),
            request_id=args.get("request_id"),
        )

    def mapping(self, args):
        events = self.ledger.events()
        return {
            "dataset": self.s.dataset,
            "source": "streeteasy",
            "listing_type": "rental",
            "identity_revision": self.ledger.revision(events),
            "listing_to_unit": identity_map(events),
            **{
                k: v
                for k, v in self.s.exclusions().items()
                if k in {"excluded_listing_ids", "exclusions", "ledger_revision"}
            },
            "unit_basis": {e["unit_id"]: e["basis"] for e in active_decisions(events)},
            "unmerged_unit_id_format": "streeteasy:rental:<listing_id>",
        }

    def undo(self, args):
        return self.ledger.write(
            "undo",
            merge_id=args.get("merge_id"),
            expected_revision=args.get("identity_revision"),
            author=args.get("author"),
            reason=args.get("reason"),
            request_id=args.get("request_id"),
        )

    def undo_separate(self, args):
        return self.ledger.write(
            "undo_separate",
            separation_id=args.get("separation_id"),
            expected_revision=args.get("identity_revision"),
            author=args.get("author"),
            reason=args.get("reason"),
            request_id=args.get("request_id"),
        )

    def association_preview(self, args):
        data = self.candidates(
            {"queue": "supported", "search": args.get("search", "")}, all_rows=True
        )
        if not data["rows"]:
            raise ValueError("No source-supported groups match this search")
        proposals = [
            {"listing_ids": r["listing_ids"], "evidence": r["assessment"]}
            for r in data["rows"]
        ]
        token = uuid.uuid4().hex
        record = {
            "dataset": self.s.dataset,
            "identity_revision": data["identity_revision"],
            "review_revision": data["review_revision"],
            "source_digest": self._source.digest,
            "proposals": proposals,
            "search": args.get("search", ""),
            "reason": "Accepted shared latest-listing references with matching building/unit labels; durable unit IDs are independent of those references",
        }
        directory = self.s.state / "unit-proposals"
        directory.mkdir(exist_ok=True)
        (directory / (token + ".json")).write_text(canonical(record))
        return {
            "token": token,
            "group_count": len(proposals),
            "listing_count": sum(len(p["listing_ids"]) for p in proposals),
            "capture_count": sum(len(p["evidence"]["snapshot_ids"]) for p in proposals),
            "examples": data["rows"][:10],
            "search": record["search"],
        }

    def proposal(self, args):
        token = str(args.get("token", ""))
        if not re.fullmatch("[a-f0-9]{32}", token):
            raise ValueError("Invalid proposal token")
        try:
            return json.loads(
                (self.s.state / "unit-proposals" / (token + ".json")).read_text()
            )
        except FileNotFoundError as exc:
            raise ValueError("Proposal not found; preview again") from exc

    def association_apply(self, args):
        # Hold the review revision stable through validation and the identity write.
        with self.s.ledger.path.open("a+", encoding="utf-8") as stream:
            fcntl.flock(stream, fcntl.LOCK_SH)
            return self._association_apply(args)

    def _association_apply(self, args):
        record = self.proposal(args)
        token = args["token"]
        events = self.ledger.events()
        prior = next((e for e in events if e["request_id"] == token), None)
        if prior is None:
            review = self.s.ledger.events()
            if (
                record["dataset"] != self.s.dataset
                or record["review_revision"]
                != (review[-1]["hash"] if review else GENESIS)
                or record["identity_revision"] != self.ledger.revision(events)
            ):
                raise ReviewConflict(
                    "Review data or unit identities changed; preview again"
                )
            catalog = self.catalog(review, events)
            assessments = self.assessments(catalog, review, events)
            allowed = {
                tuple(v["listing_ids"]): v
                for v in assessments.values()
                if v["eligible"]
            }
            if record["source_digest"] != self._source.digest or any(
                allowed.get(tuple(p["listing_ids"])) != p["evidence"]
                for p in record["proposals"]
            ):
                raise ReviewConflict("Source evidence changed; preview again")
        event = self.ledger.write(
            "associate_batch",
            proposals=record["proposals"],
            review_revision=record["review_revision"],
            expected_revision=record["identity_revision"],
            author=args.get("author"),
            reason=record.get(
                "reason",
                "Accepted consistent StreetEasy unit-page and listing-history associations",
            ),
            request_id=token,
        )
        return {
            "batch_id": event["id"],
            "group_count": len(event["proposals"]),
            "listing_count": sum(len(p["listing_ids"]) for p in event["proposals"]),
        }

    def batches(self, args):
        events = self.ledger.events()
        active = {e["id"] for e in active_decisions(events)}
        return {
            "identity_revision": self.ledger.revision(events),
            "rows": [
                {
                    "batch_id": e["id"],
                    "recorded_at": e["recorded_at"],
                    "author": e["author"],
                    "group_count": len(e["units"]),
                    "active_groups": sum(u["id"] in active for u in e["units"]),
                }
                for e in reversed(events)
                if e["action"] == "associate_batch"
            ],
        }

    def association_undo(self, args):
        event = self.ledger.write(
            "undo_batch",
            batch_id=args.get("batch_id"),
            expected_revision=args.get("identity_revision"),
            author=args.get("author"),
            reason=args.get("reason"),
            request_id=args.get("request_id"),
        )
        return {"id": event["id"], "batch_id": event["batch_id"]}
