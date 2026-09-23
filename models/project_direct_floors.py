"""Apply the reviewed 24 own-ad floor additions with an exact parent inverse."""

import argparse
import hashlib
import json
from pathlib import Path

from apartments import direct_floor_projection as contract
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from apartments.reviewed_source_lineage import source_lineage


def run(dataset, policy, output, reviewed_at):
    dataset, policy, output = map(Path, (dataset, policy, output))
    source_hash, policy_bundle_hash = (
        digest(dataset / "complete.json"),
        digest(policy / "complete.json"),
    )
    if (
        policy_bundle_hash
        != "b447545431c5ab427c2995d30fbe0bdd50b6c5d491b41fb5acd8d870c29057d2"
    ):
        raise ValueError("Expected the exact prepared and reviewed floor policy")
    pm = json.loads((dataset / "complete.json").read_text())
    parent, files = _verified_bundle(dataset, retain=set(pm["files"]))
    _, pf = _verified_bundle(policy, retain={"policy.json"})
    decision = json.loads(pf["policy.json"])
    if decision["source_manifest_sha256"] != source_hash:
        raise ValueError("Floor policy binds another source")
    records = lambda data: [json.loads(s) for s in data.decode().split("\n") if s]
    before = records(files["observations.jsonl"])
    source_lineage(
        parent,
        before,
        residual_scope_changes=records(files["residual-scope-quarantine.jsonl"]),
        quarantined=records(files["quarantined.jsonl"]),
        elevator_changes=records(files["elevator-corrections.jsonl"]),
        floor_label_changes=records(files["floor-label-projection.jsonl"]),
        expanded_floor_changes=records(files["expanded-floor-projection.jsonl"]),
    )
    cases = {c["audit_id"]: c for c in decision["cases"]}
    assert len(cases) == len(decision["cases"]) == 24
    policy_hash = hashlib.sha256(pf["policy.json"]).hexdigest()
    after, changes = [], []
    for index, row in enumerate(before):
        case = cases.pop(row["audit_id"], None)
        if case is None:
            after.append(row)
        else:
            after.append(contract.apply_case(row, case, reviewed_at, policy_hash))
            changes.append({"source_index": index, "before": row, "case": case})
    assert not cases and len(changes) == 24
    # Canonical floor alias: a raw listed_floor-only count misses existing aliases.
    known = lambda rows: sum(
        r.get("listed_floor") is not None or r.get("advertised_floor") is not None
        for r in rows
    )
    summary = {
        "source_rows": len(before),
        "rows": len(after),
        "floor_additions": len(changes),
        "known_floor_before": known(before),
        "known_floor_after": known(after),
        "other_fields_unchanged": True,
        "measurement": "advertised floor, not physical height",
    }
    products = {
        name: value.decode()
        for name, value in files.items()
        if name not in {"observations.jsonl", "summary.json"}
    }
    if {
        contract.SIDECAR,
        "direct-floor-parent-summary.json",
        "direct-floor-policy.json",
    } & products.keys():
        raise ValueError("Cannot overwrite ancestor floor artifacts")
    products.update(
        {
            "observations.jsonl": "".join(canonical(r) + "\n" for r in after),
            contract.SIDECAR: "".join(canonical(r) + "\n" for r in changes),
            "direct-floor-policy.json": pf["policy.json"].decode(),
            "direct-floor-parent-summary.json": files["summary.json"].decode(),
            "summary.json": canonical(summary) + "\n",
            Path(__file__).name: Path(__file__).read_text(),
            Path(contract.__file__).name: Path(contract.__file__).read_text(),
        }
    )
    metadata = {
        "version": contract.VERSION,
        "source_manifest": parent,
        "source_manifest_sha256": source_hash,
        "policy": decision,
        "policy_sha256": policy_hash,
        "policy_bundle_manifest_sha256": policy_bundle_hash,
        "source_rows": len(before),
        "reviewed_at": reviewed_at,
        "summary": summary,
    }
    prospective = {
        **metadata,
        "files": {
            name: hashlib.sha256(value.encode()).hexdigest()
            for name, value in products.items()
        },
    }
    if contract.parent_rows(prospective, after, changes) != (parent, before):
        raise ValueError("Direct floor revision does not restore exact parent")
    if (
        digest(dataset / "complete.json") != source_hash
        or digest(policy / "complete.json") != policy_bundle_hash
    ):
        raise ValueError("Source changed during projection")
    publish_bundle(output, products, metadata)
    _verified_bundle(output)
    return {**summary, "manifest_sha256": digest(output / "complete.json")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("dataset", "policy", "output", "reviewed_at"):
        parser.add_argument("--" + name.replace("_", "-"), required=True)
    print(canonical(run(**vars(parser.parse_args()))))
