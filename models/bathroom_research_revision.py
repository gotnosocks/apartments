"""Apply named, source-reviewed bathroom research decisions to an immutable projection.

No raw record, price, or ambiguous bathroom count is corrected. This is a separate
research projection and does not replace the serving model or original dataset.
"""

from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
from pathlib import Path
import re

from apartments.corrections import canonical, instant
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from .interior_feature_audit import json_rows

VERSION = "reviewed-bathroom-counts-projection-v1"
DECISION_VERSION = "source-reviewed-bathroom-decisions-v1"
MULTIPLE_FLAG = "multiple_reported_half_bathrooms_review_required"
SHARED_FLAG = "reviewed_external_shared_bathroom_or_toilet_access"
SHARED_BUILDING_ADS = frozenset(
    {
        "1536491",
        "2533438",
        "2204760",
        "1530908",
        "2635017",
        "2420686",
        "2379476",
        "2584659",
        "2582396",
        "1540253",
        "2555696",
        "2627433",
        "1646782",
        "2201202",
        "2571848",
        "1700760",
    }
)
SHARED_ADS = SHARED_BUILDING_ADS | {"2430461"}
CORROBORATED = {"1945700": (1, 2), "2762077": (2, 2)}
OFFICE_AD = "3303145"
REVIEW_FIELDS = (
    "reported_full_bathrooms",
    "reported_half_bathrooms",
    "bathroom_count_evidence",
)
SOURCE_ID_FIELDS = ("audit_id", "source_listing_id", "unit_id", "canonical_unit_url")


def sha(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def summary(rows):
    return {
        "rows": len(rows),
        "known_full_rows": sum(r["reported_full_bathrooms"] is not None for r in rows),
        "known_half_rows": sum(r["reported_half_bathrooms"] is not None for r in rows),
        "complete_unflagged_count_rows": sum(
            r["reported_full_bathrooms"] is not None
            and r["reported_half_bathrooms"] is not None
            and not r["bathroom_count_evidence"]["flags"]
            for r in rows
        ),
        "flagged_rows": sum(bool(r["bathroom_count_evidence"]["flags"]) for r in rows),
        "flag_counts": dict(
            sorted(
                Counter(
                    f for r in rows for f in r["bathroom_count_evidence"]["flags"]
                ).items()
            )
        ),
    }


def source_excerpt(capture, action):
    text = capture["description"]
    if (
        not isinstance(text, str)
        or hashlib.sha256(text.encode()).hexdigest() != capture["description_sha256"]
    ):
        raise ValueError("Decision source description hash mismatch")
    ad = capture["source_listing_id"]
    if action == "quarantine_nonresidential":
        expression = re.escape("NON RESIDENTIAL - ONLY FOR OFICE USE")
    elif action == "mark_shared_composition_unknown":
        expression = r"\bshared\s+(?:bath(?:room)?s?|toilets)\b"
    elif ad == "1945700":
        expression = re.escape("(1 Full, 2 Half Baths)")
    elif ad == "2762077":
        expression = re.escape("3 bed, 2 baths, with 2 powder rooms")
    else:
        raise ValueError("Unrecognized reviewed decision source")
    match = re.search(expression, text, re.I)
    if match is None:
        raise ValueError("Reviewed source wording missing")
    if action == "accept_corroborated_multiple_half":
        fields = capture["bathroom_fields"]
        actual = (
            fields["fullBathroomCount"]["value"],
            fields["halfBathroomCount"]["value"],
        )
        if actual != CORROBORATED[ad]:
            raise ValueError("Corroborated counts differ from raw capture")
    return {
        k: capture[k]
        for k in (
            *SOURCE_ID_FIELDS,
            "capture_id",
            "body_sha256",
            "raw_listing_sha256",
            "description_sha256",
            "source_collected_at",
            "description_interpreted_at",
            "known_at",
        )
    } | {
        "source_path": "/description",
        "start": match.start(),
        "end": match.end(),
        "literal": match.group(),
        "description": text,
        "bathroom_fields": capture["bathroom_fields"],
    }


def bind_review_capture(review_capture, audit_capture):
    for key in (
        "capture_id",
        "body_sha256",
        "raw_listing_sha256",
        "description_sha256",
        "description",
    ):
        if review_capture.get(key) != audit_capture.get(key):
            raise ValueError("Review capture source binding mismatch")


def prepare(projection, audit, bathroom_review, group_review, interpreted_at, output):
    pm, pf = _verified_bundle(projection, retain={"observations.jsonl"})
    am, af = _verified_bundle(audit, retain={"captures.jsonl"})
    bm, bf = _verified_bundle(bathroom_review, retain={"source-issues.jsonl"})
    gm, gf = _verified_bundle(group_review, retain={"building-scope-evidence.jsonl"})
    if (
        pm.get("audit_manifest") != am
        or bm.get("audit_manifest") != am
        or bm.get("projection_manifest") != pm
        or gm.get("description_manifest") != am.get("description_manifest")
    ):
        raise ValueError("Source review/projection lineage mismatch")
    clock = instant(interpreted_at).isoformat()
    rows = json_rows(pf["observations.jsonl"])
    by_ad = defaultdict(list)
    for row in rows:
        by_ad[str(row["source_listing_id"])].append(row)
    captures = json_rows(af["captures.jsonl"])
    by_id = defaultdict(list)
    cap_by_key = {}
    for c in captures:
        key = (c["audit_id"], c["capture_id"])
        if key in cap_by_key:
            raise ValueError("Duplicate source capture")
        cap_by_key[key] = c
        by_id[c["audit_id"]].append(c)
    issues = {
        str(r["source_listing_id"]): r for r in json_rows(bf["source-issues.jsonl"])
    }
    group_captures = [
        r
        for r in json_rows(gf["building-scope-evidence.jsonl"])
        if r["building_id"] == "333-west-29-street-new_york"
    ]
    if {str(r["source_listing_id"]) for r in group_captures} != SHARED_BUILDING_ADS:
        raise ValueError("Named shared-access review membership mismatch")
    for c in group_captures:
        original = cap_by_key.get((c["audit_id"], c["capture_id"]))
        if original is None:
            raise ValueError("Unknown reviewed capture")
        bind_review_capture(c, original)
    group_keys = {(c["audit_id"], c["capture_id"]) for c in group_captures}
    actions = {ad: "mark_shared_composition_unknown" for ad in SHARED_ADS}
    actions.update({ad: "accept_corroborated_multiple_half" for ad in CORROBORATED})
    actions[OFFICE_AD] = "quarantine_nonresidential"
    decisions = []
    for ad, action in sorted(actions.items()):
        if len(by_ad.get(ad, [])) != 1:
            raise ValueError(
                "Reviewed advertisement must identify exactly one analytical row"
            )
        row = by_ad[ad][0]
        cs = by_id[row["audit_id"]]
        if set(row["bathroom_count_evidence"]["capture_ids"]) != {
            c["capture_id"] for c in cs
        }:
            raise ValueError("Projection capture membership mismatch")
        if ad in SHARED_BUILDING_ADS:
            if {(c["audit_id"], c["capture_id"]) for c in cs} != {
                k for k in group_keys if k[0] == row["audit_id"]
            }:
                raise ValueError("Not every advertisement capture was reviewed")
        else:
            issue = issues.get(ad)
            category = {
                "mark_shared_composition_unknown": "shared_external_bathrooms",
                "accept_corroborated_multiple_half": "multiple_half_baths_corroborated",
                "quarantine_nonresidential": "nonresidential_scope",
            }[action]
            if (
                issue is None
                or issue["category"] != category
                or issue["audit_id"] != row["audit_id"]
            ):
                raise ValueError("Named bathroom review decision mismatch")
            reviewed = {c["capture_id"]: c for c in issue["evidence"]}
            if set(reviewed) != {c["capture_id"] for c in cs}:
                raise ValueError("Not every advertisement capture was reviewed")
            for c in cs:
                bind_review_capture(reviewed[c["capture_id"]], c)
        if instant(clock) < instant(row["known_at"]):
            raise ValueError("Interpretation precedes observation knowledge")
        for c in cs:
            if any(str(c[k]) != str(row[k]) for k in SOURCE_ID_FIELDS):
                raise ValueError("Decision row/source identity mismatch")
            if instant(clock) < instant(c["known_at"]):
                raise ValueError("Interpretation precedes source knowledge")
        evidence = [
            source_excerpt(c, action)
            for c in sorted(cs, key=lambda c: str(c["capture_id"]))
        ]
        reason = {
            "quarantine_nonresidential": "Explicit office-only advertisement is outside residential rental analysis; price and attributes are preserved in quarantine.",
            "mark_shared_composition_unknown": "Explicitly shared bathroom or toilet access does not identify private unit bathroom composition. Preserve original counts; do not assert zero private fixtures.",
            "accept_corroborated_multiple_half": "Exact same-advertisement text corroborates multiple half baths. Remove only the generic multiple-half review flag; keep all counts and other flags.",
        }[action]
        decision = {k: row[k] for k in SOURCE_ID_FIELDS} | {
            "action": action,
            "reason": reason,
            "interpreted_at": clock,
            "source_projection_row_sha256": sha(row),
            "evidence": evidence,
        }
        decision["decision_id"] = sha(decision)
        decisions.append(decision)
    decisions.sort(key=lambda d: d["audit_id"])
    info = {
        "decisions": len(decisions),
        "action_counts": dict(sorted(Counter(d["action"] for d in decisions).items())),
        "interpreted_at": clock,
        "policy": "Named reviewed advertisements only. No propagation by building, unit, or date. No ambiguous count corrections.",
    }
    return publish_bundle(
        output,
        {
            "decisions.jsonl": "".join(canonical(d) + "\n" for d in decisions),
            "summary.json": canonical(info) + "\n",
            "revision.py": Path(__file__).read_text(),
        },
        {
            "version": DECISION_VERSION,
            "projection_manifest": pm,
            "audit_manifest": am,
            "bathroom_review_manifest": bm,
            "group_review_manifest": gm,
            "summary": info,
            "implementation_sha256": {Path(__file__).name: digest(Path(__file__))},
        },
    )


def apply_decision(row, decision):
    if decision["source_projection_row_sha256"] != sha(row):
        raise ValueError("Decision source row hash mismatch")
    if any(str(decision[k]) != str(row[k]) for k in SOURCE_ID_FIELDS):
        raise ValueError("Decision identity mismatch")
    if (
        sha({k: v for k, v in decision.items() if k != "decision_id"})
        != decision["decision_id"]
    ):
        raise ValueError("Decision ID mismatch")
    if not decision["evidence"]:
        raise ValueError("Missing decision evidence")
    if {e["capture_id"] for e in decision["evidence"]} != set(
        row["bathroom_count_evidence"]["capture_ids"]
    ):
        raise ValueError("Decision evidence capture membership mismatch")
    for e in decision["evidence"]:
        if any(str(e[k]) != str(row[k]) for k in SOURCE_ID_FIELDS):
            raise ValueError("Evidence identity mismatch")
        text = e["description"]
        if (
            hashlib.sha256(text.encode()).hexdigest() != e["description_sha256"]
            or text[e["start"] : e["end"]] != e["literal"]
        ):
            raise ValueError("Evidence text span or hash mismatch")
    action = decision["action"]
    if action == "quarantine_nonresidential":
        return None
    result = deepcopy(row)
    if "bathroom_count_before_review" in result or "bathroom_review" in result:
        raise ValueError("Already reviewed observation")
    result["bathroom_count_before_review"] = {
        k: deepcopy(row[k]) for k in REVIEW_FIELDS
    }
    result["bathroom_review"] = {
        "decision_id": decision["decision_id"],
        "action": action,
        "interpreted_at": decision["interpreted_at"],
        "source_projection_row_sha256": decision["source_projection_row_sha256"],
    }
    if action == "mark_shared_composition_unknown":
        result["bathroom_count_evidence"]["composition_status"] = (
            "reviewed_external_shared_access_composition_unknown"
        )
        result["bathroom_count_evidence"]["flags"] = list(
            dict.fromkeys([*row["bathroom_count_evidence"]["flags"], SHARED_FLAG])
        )
    elif action == "accept_corroborated_multiple_half":
        if MULTIPLE_FLAG not in row["bathroom_count_evidence"]["flags"]:
            raise ValueError("Missing generic multiple-half flag")
        result["bathroom_count_evidence"]["flags"] = [
            f for f in row["bathroom_count_evidence"]["flags"] if f != MULTIPLE_FLAG
        ]
    else:
        raise ValueError("Unknown research decision action")
    return result


def project(projection, decisions, output):
    pm, pf = _verified_bundle(projection, retain={"observations.jsonl"})
    dm, df = _verified_bundle(decisions, retain={"decisions.jsonl"})
    if dm.get("version") != DECISION_VERSION or dm.get("projection_manifest") != pm:
        raise ValueError("Decision projection lineage mismatch")
    # Frozen code is part of the interpreted policy, including the evidence checks.
    if dm["implementation_sha256"] != {Path(__file__).name: digest(Path(__file__))}:
        raise ValueError("Decision implementation changed; create a new policy version")
    rows = json_rows(pf["observations.jsonl"])
    ds = json_rows(df["decisions.jsonl"])
    by_id = {d["audit_id"]: d for d in ds}
    if len(by_id) != len(ds) or not set(by_id) <= {r["audit_id"] for r in rows}:
        raise ValueError("Duplicate or unknown decision identity")
    if len({r["audit_id"] for r in rows}) != len(rows):
        raise ValueError("Duplicate projection identity")
    result = []
    quarantined = []
    changes = []
    for row in rows:
        d = by_id.get(row["audit_id"])
        if d is None:
            result.append(row)
            continue
        changed = apply_decision(row, d)
        if changed is None:
            quarantined.append(
                {
                    "observation": row,
                    "decision_id": d["decision_id"],
                    "reason": d["reason"],
                    "interpreted_at": d["interpreted_at"],
                }
            )
        else:
            if any(changed[k] != v for k, v in row.items() if k not in REVIEW_FIELDS):
                raise ValueError("Original analytical field altered")
            result.append(changed)
        changes.append(
            {
                "audit_id": row["audit_id"],
                "source_listing_id": row["source_listing_id"],
                "decision_id": d["decision_id"],
                "action": d["action"],
                "before": {k: row[k] for k in REVIEW_FIELDS},
                "after": {k: changed[k] for k in REVIEW_FIELDS}
                if changed is not None
                else None,
            }
        )
    info = {
        "before": summary(rows),
        "after": summary(result),
        "quarantined_rows": len(quarantined),
        "action_counts": dict(sorted(Counter(d["action"] for d in ds).items())),
        "interpreted_at": dm["summary"]["interpreted_at"],
        "original_analytical_fields_unchanged": True,
        "policy": "Research-only revision; original projection and main model remain unchanged. Raw counts retained. No ambiguous count repair.",
    }
    return publish_bundle(
        output,
        {
            "observations.jsonl": "".join(canonical(r) + "\n" for r in result),
            "quarantined.jsonl": "".join(canonical(r) + "\n" for r in quarantined),
            "changes.jsonl": "".join(canonical(r) + "\n" for r in changes),
            "summary.json": canonical(info) + "\n",
            "revision.py": Path(__file__).read_text(),
        },
        {
            "version": VERSION,
            "projection_manifest": pm,
            "decision_manifest": dm,
            "summary": info,
            "implementation_sha256": {Path(__file__).name: digest(Path(__file__))},
        },
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    for name in ("projection", "audit", "bathroom-review", "group-review", "output"):
        prep.add_argument("--" + name, type=Path, required=True)
    prep.add_argument("--interpreted-at", required=True)
    build = sub.add_parser("project")
    for name in ("projection", "decisions", "output"):
        build.add_argument("--" + name, type=Path, required=True)
    args = vars(p.parse_args())
    command = args.pop("command")
    print(canonical((prepare if command == "prepare" else project)(**args)["summary"]))
