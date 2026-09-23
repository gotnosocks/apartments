"""Inventory explicitly labeled floor-plan references; never fetch or inspect images."""

from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import gzip, hashlib, json, re
from pathlib import Path
from urllib.parse import urlsplit

from apartments import granular_parse
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from streeteasy_archive import extract, flight
from .interior_feature_audit import json_rows

VERSION = "ensuite-floorplan-reference-audit-v1"
PREFERRED_ADS = (
    "1639871",
    "4068484",
    "3059501",
    "3080726",
    "3213567",
    "4799624",
    "4320516",
    "5064467",
)
SOURCE_FIELDS = (
    "audit_id",
    "unit_id",
    "source_listing_id",
    "canonical_unit_url",
    "capture_id",
    "body_sha256",
    "raw_listing_sha256",
    "description_sha256",
    "source_collected_at",
    "known_at",
    "analysis_price_basis",
)


def floorplan_metadata(payload):
    media = payload.get("media")
    if not isinstance(media, dict):
        return {"status": "media_missing_or_unresolved", "references": []}
    if "floorPlans" not in media:
        return {"status": "floorPlans_field_missing", "references": []}
    plans = media["floorPlans"]
    if not isinstance(plans, list):
        return {"status": "floorPlans_field_not_list", "references": []}
    refs = []
    for i, item in enumerate(plans):
        if isinstance(item, dict) and isinstance(item.get("key"), str) and item["key"]:
            refs.append(
                {
                    "asset_id": item["key"],
                    "source_path": f"/media/floorPlans/{i}/key",
                    "explicit_floorplan_label": "media.floorPlans",
                    "raw_metadata": item,
                }
            )
    status = (
        "explicit_floorplan_references"
        if refs
        else ("empty_floorPlans_list" if not plans else "unresolved_floorPlans_items")
    )
    return {"status": status, "references": refs}


def matching_key(url, keys):
    if not isinstance(url, str):
        return None
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme not in ("http", "https"):
        return None
    return next(
        (
            key
            for key in keys
            if re.search(r"/" + re.escape(key) + r"(?:[-./]|$)", parts.path)
        ),
        None,
    )


def walk(value, path=""):
    if isinstance(value, dict):
        yield path, value
        for k, v in value.items():
            yield from walk(v, path + "/" + str(k))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from walk(v, path + "/" + str(i))


def body_references(body, keys):
    """Match exact URLs actually present in explicitly labeled archived metadata."""
    keys = sorted(set(keys))
    sel = extract._selector(body)
    result = []
    for i, node in enumerate(sel.xpath("//img")):
        label = node.attrib.get("alt", "")
        url = node.attrib.get("src")
        key = matching_key(url, keys)
        if key and re.fullmatch(r"\s*floor[ -]?plan(?:\s+\d+)?\s*", label, re.I):
            result.append(
                {
                    "asset_id": key,
                    "image_url": url,
                    "source_kind": "html_img",
                    "source_path": f"//img[{i + 1}]/@src",
                    "explicit_floorplan_label": label,
                    "variant": "html_src",
                }
            )
    records = flight.decode_records(extract.flight_text(extract._scripts(sel)))
    for record_id, record in records.items():
        for path, obj in walk(record, f"/flight_records/{record_id}"):
            if obj.get("mediaType") != "floor_plan":
                continue
            sources = obj.get("mediaSrc")
            if not isinstance(sources, dict):
                continue
            for variant, url in sorted(sources.items()):
                key = matching_key(url, keys)
                if key:
                    result.append(
                        {
                            "asset_id": key,
                            "image_url": url,
                            "source_kind": "flight_gallery",
                            "source_path": path + "/mediaSrc/" + variant,
                            "explicit_floorplan_label": "mediaType=floor_plan",
                            "gallery_description": obj.get("description"),
                            "gallery_media_id": obj.get("id"),
                            "variant": variant,
                        }
                    )
    return sorted(
        result, key=lambda r: (r["asset_id"], r["image_url"], r["source_path"])
    )


def checked_body(body_root, sha):
    if not isinstance(sha, str) or not re.fullmatch("[a-f0-9]{64}", sha):
        raise ValueError("Invalid body hash")
    body = gzip.decompress((Path(body_root) / sha[:2] / (sha + ".gz")).read_bytes())
    if hashlib.sha256(body).hexdigest() != sha:
        raise ValueError("Archived body hash mismatch")
    return body


def run(
    candidates, review, bathroom_audit, archive, historical, body_root, refresh, output
):
    cm, cf = _verified_bundle(candidates, retain={"candidates.jsonl"})
    rm, rf = _verified_bundle(review, retain={"review.jsonl"})
    bm, _ = _verified_bundle(bathroom_audit)
    hm, hf = _verified_bundle(historical, retain={"source-files.json"})
    if (
        cm.get("bathroom_audit_manifest") != bm
        or rm.get("candidate_manifest") != cm
        or bm.get("historical_manifest") != hm
    ):
        raise ValueError("Floor-plan source lineage mismatch")
    cs = json_rows(cf["candidates.jsonl"])
    by_capture = {c["capture_id"]: c for c in cs}
    if len(by_capture) != len(cs):
        raise ValueError("Duplicate source capture")
    reviews = json_rows(rf["review.jsonl"])
    by_ad = {r["source_listing_id"]: r for r in reviews}
    if not set(PREFERRED_ADS) <= set(by_ad):
        raise ValueError("Missing named comparison review")
    inv = json.loads(hf["source-files.json"])
    archive = Path(archive)
    paths = [
        archive / p
        for p in inv
        if p.startswith("listing_observations/") and p.endswith(".parquet")
    ]
    if not paths:
        raise ValueError("Missing listing source table")
    for p in paths:
        if (
            not p.resolve().is_relative_to(archive.resolve())
            or digest(p) != inv[str(p.relative_to(archive))]
        ):
            raise ValueError("Source shard hash mismatch")
    inventory = []
    seen = set()

    def consume(capture, ad, url, raw):
        c = by_capture[capture]
        if (
            capture in seen
            or str(ad) != c["source_listing_id"]
            or url != c["canonical_unit_url"]
            or hashlib.sha256(raw.encode()).hexdigest() != c["raw_listing_sha256"]
        ):
            raise ValueError("Raw capture identity/hash mismatch")
        seen.add(capture)
        metadata = floorplan_metadata(json.loads(raw))
        inventory.append(
            {k: c[k] for k in SOURCE_FIELDS}
            | {
                "reported_count_consensus": c["reported_count_consensus"],
                "floorplan_metadata": metadata,
                "same_advertisement_scope_confirmed": True,
                "physical_floorplan_correspondence_verified": False,
            }
        )

    import duckdb

    old_ids = [
        c["capture_id"]
        for c in cs
        if c["analysis_price_basis"] == "historical_initial_own_advertisement_ask"
    ]
    with duckdb.connect(config={"threads": "2", "memory_limit": "1GB"}) as db:
        db.read_parquet([str(p) for p in paths]).create_view("source")
        cur = db.execute(
            "SELECT snapshot_id,listing_id,canonical_unit_url,raw_listing_json FROM source WHERE snapshot_id IN (SELECT unnest(?)) ORDER BY snapshot_id",
            [old_ids],
        )
        while batch := cur.fetchmany(128):
            for values in batch:
                consume(*values)
    # The verified upstream dataset provides current capture provenance, if needed.
    current = [
        c for c in cs if c["analysis_price_basis"] == "current_capture_gross_ask"
    ]
    if current:
        dm, df = _verified_bundle(
            Path(refresh) / "snapshot", retain={"candidates.jsonl"}
        )
        if bm["description_manifest"]["refresh_manifest"] != dm:
            raise ValueError("Current source lineage mismatch")
        fresh = {r["capture_id"]: r for r in json_rows(df["candidates.jsonl"])}
        for c in current:
            r = fresh[c["capture_id"]]
            body = checked_body(Path(refresh) / "archive/bodies", c["body_sha256"])
            parsed, _ = granular_parse.parse_listing(
                body, r["refresh_provenance"]["requested_url"]
            )
            consume(
                c["capture_id"],
                parsed["listing_id"],
                parsed["canonical_unit_url"],
                parsed["raw_listing_json"],
            )
    if seen != set(by_capture):
        raise ValueError("Missing candidate raw captures")
    inventory.sort(key=lambda c: (c["audit_id"], str(c["capture_id"])))
    by_key = {(r["audit_id"], r["capture_id"]): r for r in inventory}
    selected = []
    for ad in PREFERRED_ADS:
        review_row = by_ad[ad]
        c = by_key[(review_row["audit_id"], review_row["capture_id"])]
        if any(c[k] != review_row[k] for k in SOURCE_FIELDS):
            raise ValueError("Reviewed comparison source mismatch")
        counts = c["reported_count_consensus"]
        if (
            counts["bedrooms"],
            counts["reported_full_bathrooms"],
            counts["reported_half_bathrooms"],
        ) != (2, 2, 0):
            raise ValueError("Named comparison leaves2BR/2full/0half cell")
        refs = c["floorplan_metadata"]["references"]
        keys = [r["asset_id"] for r in refs]
        source_body_root = (
            Path(refresh) / "archive/bodies"
            if c["analysis_price_basis"] == "current_capture_gross_ask"
            else Path(body_root)
        )
        body = checked_body(source_body_root, c["body_sha256"])
        urls = body_references(body, keys)
        selected.append(
            {
                **c,
                "ensuite_text_review": review_row["interpretation"],
                "exact_archived_url_references": urls,
                "inspection_status": "metadata_only_image_not_downloaded_or_seen",
                "recommended_images": [
                    next(
                        (
                            r
                            for r in urls
                            if r["asset_id"] == key and r["variant"] == "full"
                        ),
                        next((r for r in urls if r["asset_id"] == key), None),
                    )
                    for key in keys
                ],
            }
        )
    rows_with_refs = {
        r["audit_id"] for r in inventory if r["floorplan_metadata"]["references"]
    }
    cases = defaultdict(list)
    for r in inventory:
        cases[r["audit_id"]].append(r)
    changes = [
        audit
        for audit, rs in cases.items()
        if len(
            {
                tuple(
                    sorted(x["asset_id"] for x in r["floorplan_metadata"]["references"])
                )
                for r in rs
            }
        )
        > 1
    ]
    count_cell_ids = {
        r["audit_id"]
        for r in inventory
        if (
            r["reported_count_consensus"]["bedrooms"],
            r["reported_count_consensus"]["reported_full_bathrooms"],
            r["reported_count_consensus"]["reported_half_bathrooms"],
        )
        == (2, 2, 0)
    }
    info = {
        "candidate_rows": len(cases),
        "candidate_captures": len(inventory),
        "rows_with_explicit_floorplan_ids": len(rows_with_refs),
        "units_with_explicit_floorplan_ids": len(
            {r["unit_id"] for r in inventory if r["floorplan_metadata"]["references"]}
        ),
        "distinct_floorplan_asset_ids": len(
            {
                x["asset_id"]
                for r in inventory
                for x in r["floorplan_metadata"]["references"]
            }
        ),
        "capture_metadata_statuses": dict(
            sorted(
                Counter(r["floorplan_metadata"]["status"] for r in inventory).items()
            )
        ),
        "same_ad_rows_with_changing_asset_sets": len(changes),
        "target_2br_2full_0half_candidate_rows": len(count_cell_ids),
        "target_cell_rows_with_explicit_floorplan_ids": len(
            count_cell_ids & rows_with_refs
        ),
        "selected_cases": len(selected),
        "selected_cases_with_exact_image_urls": sum(
            bool(r["exact_archived_url_references"]) for r in selected
        ),
        "selected_distinct_assets": len(
            {
                r["asset_id"]
                for c in selected
                for r in c["exact_archived_url_references"]
            }
        ),
        "images_downloaded": 0,
        "images_visually_inspected": 0,
        "policy": "Floorplan labels come from media.floorPlans and explicit HTML/gallery metadata. URLs are copied from hash-verified archived bodies, never synthesized. Same-ad reference binding does not prove image depicts the unit or its historical/current layout.",
    }
    code = [
        Path(__file__),
        Path(extract.__file__),
        Path(flight.__file__),
        Path(granular_parse.__file__),
    ]
    return publish_bundle(
        output,
        {
            "inventory.jsonl": "".join(canonical(r) + "\n" for r in inventory),
            "selected-comparisons.jsonl": "".join(
                canonical(r) + "\n" for r in selected
            ),
            "changing-asset-sets.json": canonical(sorted(changes)) + "\n",
            "summary.json": canonical(info) + "\n",
            "audit.py": Path(__file__).read_text(),
        },
        {
            "version": VERSION,
            "candidate_manifest": cm,
            "review_manifest": rm,
            "bathroom_audit_manifest": bm,
            "historical_manifest": hm,
            "summary": info,
            "implementation_sha256": {p.name: digest(p) for p in code},
        },
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in (
        "candidates",
        "review",
        "bathroom-audit",
        "archive",
        "historical",
        "body-root",
        "refresh",
        "output",
    ):
        p.add_argument("--" + name, type=Path, required=True)
    print(canonical(run(**vars(p.parse_args()))["summary"]))
