"""Publish reviewed photo-floor corrections and broader own-label floor proxies.

The five corrections use the append-only ledger; other changes are explicitly
inferred labels. Neither operation rewrites raw captures or frozen fits.
"""

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from apartments import (
    corrections,
    expanded_floor_projection as contract,
    floor_label_projection as original,
)
from apartments.bayesian_evidence import load_evidence
from apartments.corrections import canonical, instant
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from apartments.reviewed_cohort_quarantine import sha

SOURCE = "5c307d4c39abef27926a3af146145d040c7d979fddfb111255f03326deacd605"
MASKS = {
    "4501831": "06381bffaacb85ed26f26603318d00273106bd367e9f1e7ea6261e49f4529a92",
    "4592739": "72ced490f34c06496b916397924abf5a02db44e6bf0fbe6362c4ea5a141c5f82",
    "4637006": "f9131d927c018ec4e5e1ad72b45dbddf8c6e6dd2b2f9bafe15b58c28e8d18596",
    "4668696": "faf561a2241f1cb22a12991be957f2dc9aea1e99b4d6557aba0afa45695af6ac",
    "4758888": "377625736e1e1af47e5d261efb352cbc520fe34c4480cbd569b372b746e9f4a2",
}
CONFLICT_AD = "3219430"
CONFLICT_HASH = "e8b9dff46095c6f0dd275f9c24c03c3e4794525bca7857c28363e71f1fbf9291"
PHRASE = "Photos are of the same unit on the 3rd floor."
REASON = (
    "The floor-3 assertion describes reference photography of a different apartment, "
    "not the advertised residence. Withhold this exact source-version description claim; "
    "retain its literal evidence and evaluate the unit label separately."
)
REVIEW_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs/analysis/chelsea-expanded-label-rule-conflicts-2026-09-19.md"
)


def records(data):
    return [json.loads(line) for line in data.decode().split("\n") if line.strip()]


def mask_evidence(row, captures, reviewed_at):
    if (
        sha(row) != MASKS[row["source_listing_id"]]
        or row.get("advertised_floor") != 3
        or row.get("listed_floor") is not None
    ):
        raise ValueError("Reviewed photo-floor source version differs")
    if instant(reviewed_at) < instant(row["known_at"]):
        raise ValueError("Review precedes source knowledge")
    result = []
    for capture in captures:
        text = capture.get("description")
        if (
            not isinstance(text, str)
            or text.count(PHRASE) != 1
            or hashlib.sha256(text.encode()).hexdigest()
            != capture["description_sha256"]
            or capture.get("source_path") != "/description"
            or instant(capture["known_at"]) > instant(reviewed_at)
        ):
            raise ValueError("Reviewed literal photo scope differs")
        start = text.index(PHRASE)
        result.append(
            {
                **deepcopy(capture),
                "spans": [
                    {"start": start, "end": start + len(PHRASE), "literal": PHRASE}
                ],
            }
        )
    if not result:
        raise ValueError("Missing own-advertisement photo evidence")
    return result


def run(dataset, evidence, ledger, reviewed_at, output):
    dataset, evidence, ledger, output = map(Path, (dataset, evidence, ledger, output))
    if instant(reviewed_at) > corrections.now():
        raise ValueError("Review clock is in the future")
    if digest(dataset / "complete.json") != SOURCE:
        raise ValueError("This reviewed policy binds the exact selected Chelsea source")
    retained = {
        "observations.jsonl",
        original.SIDECAR,
        "elevator-corrections.jsonl",
        "quarantined.jsonl",
        "current-source-evidence.jsonl",
    }
    parent, files = _verified_bundle(dataset, retain=retained)
    rows, old_changes = (
        records(files["observations.jsonl"]),
        records(files[original.SIDECAR]),
    )
    original.parent_rows(parent, rows, old_changes)
    mapping = load_evidence(dataset, evidence)
    selected = {
        r["source_listing_id"]: r for r in rows if r["source_listing_id"] in MASKS
    }
    if selected.keys() != MASKS.keys():
        raise ValueError("Reviewed correction membership differs")
    prepared = {
        ad: mask_evidence(row, mapping[row["audit_id"]], reviewed_at)
        for ad, row in selected.items()
    }
    conflict = [r for r in rows if r["source_listing_id"] == CONFLICT_AD]
    if len(conflict) != 1 or sha(conflict[0]) != CONFLICT_HASH:
        raise ValueError("Reviewed label/prose conflict source differs")
    review_hash = digest(REVIEW_PATH)
    # Validate every source/evidence binding before appending any correction.
    existing = corrections.Overlay(ledger).active if ledger.exists() else []
    expected = set(MASKS.values())
    if any(e["target"].get("version_id") not in expected for e in existing) or len(
        {e["target"]["version_id"] for e in existing}
    ) != len(existing):
        raise ValueError(
            "Correction ledger contains unrelated or repeated active versions"
        )
    for ad, row in sorted(selected.items()):
        edit = {
            "target": {
                "source": "streeteasy",
                "source_listing_id": ad,
                "version_id": sha(row),
            },
            "validity": {"all_time": True},
            "patch": [
                {"op": "test", "path": "/advertised_floor", "value": 3},
                {"op": "replace", "path": "/advertised_floor", "value": None},
            ],
        }
        previous = next(
            (e for e in existing if e["target"].get("version_id") == sha(row)), None
        )
        if previous:
            if any(previous[k] != edit[k] for k in edit):
                raise ValueError(
                    "Existing floor correction differs from reviewed patch"
                )
        else:
            if (output / "complete.json").exists():
                raise ValueError("Published output cannot add new correction records")
            corrections.append(
                ledger,
                author="codex",
                reason=REASON,
                edit=edit,
                evidence=[
                    str(REVIEW_PATH),
                    "review_document_sha256:" + review_hash,
                    "source_manifest_sha256:" + SOURCE,
                    PHRASE,
                ],
            )
    prior = (
        json.loads((output / "complete.json").read_text())
        if (output / "complete.json").exists()
        else None
    )
    as_of = prior["interpreted_at"] if prior else corrections.now().isoformat()
    overlay = corrections.Overlay(ledger, as_of=as_of)
    if len(overlay.active) != len(MASKS):
        raise ValueError("Exactly five visible reviewed correction records required")
    active = {e["target"]["version_id"]: e for e in overlay.active}
    masks = []
    for ad, row in sorted(selected.items()):
        updated, applied = overlay.apply(
            row,
            {"source": "streeteasy", "source_listing_id": ad, "version_id": sha(row)},
        )
        expected_row = deepcopy(row)
        expected_row["advertised_floor"] = None
        if updated != expected_row or len(applied) != 1:
            raise ValueError("Correction overlay changed an unreviewed field")
        masks.append(
            {
                "audit_id": row["audit_id"],
                "source_row_sha256": sha(row),
                "reason": REASON,
                "reviewed_at": reviewed_at,
                "before_advertised_floor": 3,
                "correction_record": active[sha(row)],
                "captures": prepared[ad],
            }
        )
    policy = {
        "excluded_buildings": parent["excluded_buildings"],
        "building_floor_evidence": parent["building_floor_evidence"],
        "parent_interpreted_at": parent["interpreted_at"],
        "excluded_units": [conflict[0]["unit_id"]],
        "floor_masks": masks,
    }
    revised, changes = [], []
    for index, (row, old_change) in enumerate(zip(rows, old_changes, strict=True)):
        revised.append(contract.project_row(row, old_change, policy, as_of))
        changes.append(contract.make_change(index, row, old_change))

    def floor(row):
        return (
            row.get("listed_floor")
            if row.get("listed_floor") is not None
            else row.get("advertised_floor")
        )

    allowed = {"listed_floor", "advertised_floor", "expanded_floor_provenance"}
    if any(
        {k: v for k, v in a.items() if k not in allowed}
        != {k: v for k, v in b.items() if k not in allowed}
        for a, b in zip(rows, revised, strict=True)
    ):
        raise ValueError(
            "Expanded projection changed prices, identity or unrelated fields"
        )
    new = [
        b
        for a, b in zip(rows, revised, strict=True)
        if floor(a) is None and floor(b) is not None
    ]
    summary = {
        "rows": len(rows),
        "units": len({r["unit_id"] for r in rows}),
        "buildings": len({r["building"] for r in rows}),
        "known_before": sum(floor(r) is not None for r in rows),
        "known_after": sum(floor(r) is not None for r in revised),
        "newly_known_rows": len(new),
        "known_after_percent": 100
        * sum(floor(r) is not None for r in revised)
        / len(revised),
        "known_units_after": len(
            {r["unit_id"] for r in revised if floor(r) is not None}
        ),
        "current_rows": sum(
            r["analysis_price_basis"] == "current_capture_gross_ask" for r in rows
        ),
        "current_known_after": sum(
            r["analysis_price_basis"] == "current_capture_gross_ask"
            and floor(r) is not None
            for r in revised
        ),
        "corrected_advertisements": sorted(MASKS),
        "changed_floor_values": sum(
            floor(a) != floor(b) for a, b in zip(rows, revised, strict=True)
        ),
        "newly_known_by_rule": dict(
            Counter(r["expanded_floor_provenance"]["rule"] for r in new)
        ),
        "statuses": dict(
            Counter(r["expanded_floor_provenance"]["status"] for r in revised)
        ),
        "nonfloor_fields_unchanged": True,
        "policy": "Own-capture label proxies with explicit format and building-count guards; preserve known floors except five ledger-bound photo-reference masks. No physical-height inference, cross-advertisement floor propagation or price change.",
    }
    outputs = {
        name: content.decode()
        for name, content in files.items()
        if name != "observations.jsonl"
    }
    outputs.update(
        {
            "observations.jsonl": "".join(canonical(r) + "\n" for r in revised),
            contract.SIDECAR: "".join(canonical(c) + "\n" for c in changes),
            "expanded-floor-policy.json": canonical(policy) + "\n",
            "expanded-floor-corrections.jsonl": "".join(
                canonical(c) + "\n" for c in overlay.records
            ),
            "summary.json": canonical(summary) + "\n",
            Path(__file__).name: Path(__file__).read_text(),
            "expanded_floor_projection.py": Path(contract.__file__).read_text(),
            "expanded-floor-source-review.md": REVIEW_PATH.read_text(),
        }
    )
    metadata = {
        "version": contract.VERSION,
        "source_manifest": parent,
        "source_manifest_sha256": SOURCE,
        "source_rows": len(rows),
        "interpreted_at": as_of,
        "policy": policy,
        "policy_sha256": sha(policy),
        "overlay": overlay.manifest,
        "evidence_manifest_sha256": digest(evidence / "complete.json"),
        "review_document_sha256": review_hash,
        "summary": summary,
    }
    # Validate before publishing; readers verify the same forward/inverse contract.
    preview = {
        **metadata,
        "files": {
            name: hashlib.sha256(text.encode()).hexdigest()
            for name, text in outputs.items()
        },
    }
    contract.parent_rows(preview, revised, changes)
    result = publish_bundle(output, outputs, metadata)
    print(canonical(summary), flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("dataset", "evidence", "ledger", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--reviewed-at", required=True)
    run(**vars(parser.parse_args()))
