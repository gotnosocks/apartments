"""Alias table for canonical units whose URLs differ only in spelling.

StreetEasy sometimes gives one apartment several self-canonical unit URLs that
differ only in case, punctuation or leading zeros (`/5v` and `/005v`, `/4b` and
`/4-b`). The `canonical-url-v1` transform keeps them as separate units. This
module leaves that dataset unchanged and writes a separate alias table that
models can opt into.

Normalization can also join labels that are genuinely different (`1-2` and
`12`), so each group records `history_confirmed`: whether a crawled unit page's
own rental history lists an advertisement that the transform assigned to
another member of the group. Prefer confirmed groups.

`unit-spelling-alias-v2` also folds labels that only name a floor (`2nd-floor`,
`thirdfl`, `fl-10`, `6flr` and `6` alike) and a leading apt/unit/suite/residence
word (`unit-3c` and `3c`). Greenwich Village's crawl turned away such ads because
the unit page that vouched for them spells the unit another way.

uv run --locked --no-sync python -m apartments.unit_spelling_aliases --help
"""

import argparse
import hashlib
import json
import re
import sqlite3
import time
import uuid
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit

import pyarrow as pa
import pyarrow.parquet as pq

RULE = "unit-spelling-alias-v1"
RULES = ("unit-spelling-alias-v1", "unit-spelling-alias-v2")
ORDINALS = {
    word: str(n)
    for n, word in enumerate(
        "first second third fourth fifth sixth seventh eighth ninth tenth".split(), 1
    )
}
FLOOR = "(?:fl|flr|floor)"
SOURCE_RULE = "canonical-url-v1"
SCHEMA = pa.schema(
    [
        ("alias_group_id", pa.string()),
        ("unit_id", pa.string()),
        ("canonical_unit_url", pa.string()),
        ("representative_unit_id", pa.string()),
        ("representative_url", pa.string()),
        ("listing_count", pa.int64()),
        ("group_size", pa.int64()),
        ("history_confirmed", pa.bool_()),
        ("rule", pa.string()),
    ]
)


def normalize_label(label, rule=RULE):
    """Lowercase, drop punctuation and strip leading zeros from each number; v2
    also reduces a floor-only label to its number and drops a leading apt, unit,
    suite or residence word."""
    text = re.sub(r"[^a-z0-9]+", "", label.lower())
    text = re.sub(r"\d+", lambda m: m.group().lstrip("0") or "0", text)
    if rule == "unit-spelling-alias-v1":
        return text
    text = re.sub(r"^(?:apt|apartment|unit|suite|residence)(?=\d)", "", text)
    if m := re.fullmatch(rf"(\d+)(?:st|nd|rd|th)?{FLOOR}?", text):
        return m[1]
    if m := re.fullmatch(rf"{FLOOR}(\d+)", text):
        return m[1]
    if m := re.fullmatch(rf"({'|'.join(ORDINALS)}){FLOOR}?", text):
        return ORDINALS[m[1]]
    return text


def unit_key(url, rule=RULE):
    """(building slug, normalized label) for a StreetEasy unit page, else None."""
    match = re.fullmatch(r"/building/([^/]+)/([^/]+)", urlsplit(url).path)
    if not match or not normalize_label(match[2], rule):
        return None
    return match[1], normalize_label(match[2], rule)


def alias_rows(units, memberships=(), evidence=(), rule=RULE):
    """Alias rows for every unit in a group of two or more spellings.

    `units`: dicts with unit_id, canonical_unit_url and listing_count.
    `memberships`: (listing_id, unit_id) pairs from the transform.
    `evidence`: (listing_id, unit_url) pairs from crawled unit-page histories.
    """
    groups = defaultdict(list)
    for unit in units:
        key = unit_key(unit["canonical_unit_url"], rule)
        if key:
            groups[key].append(unit)
    unit_of_listing = dict(memberships)
    listed_on = defaultdict(set)
    for listing_id, unit_url in evidence:
        listed_on[listing_id].add(unit_url)
    rows = []
    for members in groups.values():
        if len(members) < 2:
            continue
        members.sort(key=lambda u: u["canonical_unit_url"])
        representative = max(
            members,
            key=lambda u: (u["listing_count"], -len(u["canonical_unit_url"])),
        )
        urls = {u["canonical_unit_url"] for u in members}
        ids = {u["unit_id"]: u["canonical_unit_url"] for u in members}
        confirmed = any(
            (listed_on[lid] & urls) - {ids[uid]}
            for lid, uid in unit_of_listing.items()
            if uid in ids
        )
        group_id = "alias:" + str(
            uuid.uuid5(uuid.NAMESPACE_URL, rule + ":" + "\n".join(sorted(urls)))
        )
        rows.extend(
            {
                "alias_group_id": group_id,
                "unit_id": u["unit_id"],
                "canonical_unit_url": u["canonical_unit_url"],
                "representative_unit_id": representative["unit_id"],
                "representative_url": representative["canonical_unit_url"],
                "listing_count": u["listing_count"],
                "group_size": len(members),
                "history_confirmed": confirmed,
                "rule": rule,
            }
            for u in members
        )
    return rows


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def build(dataset, output, snapshot=None, rule=RULE):
    """Write `unit_spelling_aliases.parquet` and `manifest.json` to a new directory."""
    dataset, output = Path(dataset), Path(output)
    complete = json.loads((dataset / "complete.json").read_text())
    if complete.get("unit_association_rule") != SOURCE_RULE:
        raise ValueError(f"A completed {SOURCE_RULE} transform is required")
    units_path = dataset / "rental_units" / "derived.parquet"
    members_path = dataset / "rental_unit_memberships" / "derived.parquet"
    expected = json.loads((dataset / "canonical-units.json").read_text())[
        "output_sha256"
    ]
    for name, path in (
        ("rental_units", units_path),
        ("rental_unit_memberships", members_path),
    ):
        if _sha256(path) != expected[name]:
            raise ValueError(f"{name} does not match canonical-units.json")
    if output.exists():
        raise ValueError("Output already exists; choose a new directory")
    units = pq.read_table(units_path).to_pylist()
    memberships = [
        (m["listing_id"], m["unit_id"])
        for m in pq.read_table(members_path).to_pylist()
        if m["status"] == "associated"
    ]
    evidence = []
    if snapshot:
        db = sqlite3.connect(Path(snapshot).resolve().as_uri() + "?mode=ro", uri=True)
        try:
            for key, unit_url in db.execute(
                "SELECT listing_key, unit_url FROM collection_memberships"
            ):
                match = re.fullmatch(r"rental:(\d+):detail", key or "")
                if match:
                    evidence.append((match[1], unit_url))
        finally:
            db.close()
    rows = alias_rows(units, memberships, evidence, rule)
    output.mkdir(parents=True)
    table_path = output / "unit_spelling_aliases.parquet"
    pq.write_table(
        pa.Table.from_pylist(rows, schema=SCHEMA), table_path, compression="zstd"
    )
    groups = {r["alias_group_id"]: r for r in rows}
    manifest = {
        "rule": rule,
        "created_at": time.time(),
        "source_dataset": str(dataset),
        "source_rule": SOURCE_RULE,
        "source_output_sha256": {
            "rental_units": expected["rental_units"],
            "rental_unit_memberships": expected["rental_unit_memberships"],
        },
        "evidence_snapshot": str(snapshot) if snapshot else None,
        "evidence_pairs": len(evidence),
        "implementation_sha256": _sha256(Path(__file__)),
        "counts": {
            "groups": len(groups),
            "history_confirmed_groups": sum(
                r["history_confirmed"] for r in groups.values()
            ),
            "units_in_groups": len(rows),
            "listings_in_groups": sum(r["listing_count"] for r in rows),
        },
        "output_sha256": {"unit_spelling_aliases": _sha256(table_path)},
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--snapshot", type=Path, help="archive snapshot for history evidence"
    )
    parser.add_argument("--rule", choices=RULES, default=RULE)
    args = parser.parse_args(argv)
    counts = build(args.dataset, args.output, args.snapshot, args.rule)["counts"]
    print(json.dumps(counts))


if __name__ == "__main__":
    main()
