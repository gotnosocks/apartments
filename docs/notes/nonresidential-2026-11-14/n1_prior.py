"""N1: the earlier work on nonresidential ads, counted against L1's dataset.

I gather four earlier sets of listings and count each against L1's rows:

1. The corrections ledger's excludes with the reason `nonresidential`, from every file under
   `pipeline/ledger/`, grouped by file and by the `source` each entry gives. For each listing I
   also read the pipeline build's ads file (L1's `build.ads`), which records whether the build
   kept the ad as a row (`in_rows`) and which ledger entries it applied (`ledger_entries`).
   Entries decided after L1's build (2026-10-23) apply to later builds only, so a listing
   among L1's rows may still carry one.
2. The outlier sprint's commercial screen (`/data1/apartments/tmp/outlier-sprint/nonres/
   screen2.py`, its narrowed `COMM` pattern), as its `matches2.parquet` lists it.
3. S16's `nonresidential` pattern (`blind-spots-2026-11-14/b5_patterns.py`), as its
   `patterns.json` counts it, and S16's 7 reads with the subtype `nonresidential`.
4. S17's 3 commercial reads among studio-coded rows on 5 or more rooms.

The result goes to `prior.json` and the listing ids of each set to `prior_ids.parquet`.
"""

import glob
import json

import numpy as np
import pandas as pd

OUT = "/data1/apartments/tmp/nonresidential-2026-11-14/"
REPO = "/home/ben/code/apartments/.claude/worktrees/agent-a98fb06ad2569da99/"
RUN = "/data1/apartments/frontier/runs/drift-building-phase-b0-latest-9a7830fb-l1/"
DATASET = (
    "/data1/apartments/frontier/datasets/"
    "b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise/"
)
S16 = "/data1/apartments/tmp/blind-spots-2026-11-14/"
SPRINT = "/data1/apartments/tmp/outlier-sprint/nonres/matches2.parquet"
S17_IDS = ["2481598", "1618982", "1372561"]

manifest = json.load(open(DATASET + "manifest.json"))
ADS = manifest["build"]["ads"]["path"]

d = pd.read_parquet(DATASET + "rows.parquet", columns=["listing_id", "building"])
d["listing_id"] = d.listing_id.astype(str)
a = np.load(RUN + "pred_scores.npz", allow_pickle=True)
d["held"] = a["heldout"]
drawn = set(pd.read_parquet(S16 + "draw.parquet").listing_id.astype(str))
d["drawn"] = d.listing_id.isin(drawn)
rows = d.set_index("listing_id")


def scope(ids):
    ids = pd.Index(sorted(set(map(str, ids))))
    inr = ids[ids.isin(rows.index)]
    return {
        "listings": len(ids),
        "in_l1_rows": len(inr),
        "training": int((~rows.held.loc[inr]).sum()),
        "heldout": int(rows.held.loc[inr].sum()),
        "heldout_outside_s16_draw": int(
            (rows.held.loc[inr] & ~rows.drawn.loc[inr]).sum()
        ),
    }


# 1. The ledger's nonresidential excludes.
entries = []
for path in sorted(glob.glob(REPO + "pipeline/ledger/*.ndjson")):
    for line in open(path):
        if not line.strip():
            continue
        e = json.loads(line)
        if e.get("change") == "exclude" and e.get("reason") == "nonresidential":
            entries.append(
                {
                    "file": path.rsplit("/", 1)[1],
                    "listing_id": str(e["listing_id"]),
                    "decided": e.get("decided"),
                    "source": e.get("source", ""),
                    "kinds": ",".join(
                        sorted({v.get("kind", "") for v in e["evidence"]})
                    ),
                }
            )
led = pd.DataFrame(entries)
ads = pd.read_parquet(ADS, columns=["listing_id", "in_rows", "ledger_entries"])
ads["listing_id"] = ads.listing_id.astype(str)
ads = ads[ads.listing_id.isin(set(led.listing_id))].set_index("listing_id")
led["in_build_rows"] = led.listing_id.map(ads.in_rows)
led["applied_in_build"] = led.listing_id.map(
    ads.ledger_entries.map(lambda v: len(v) > 0 if v is not None else False)
)
led["in_l1_rows"] = led.listing_id.isin(rows.index)
res = {
    "ledger": {
        "entries": len(led),
        "listings": int(led.listing_id.nunique()),
        "by_file": led.groupby("file").size().to_dict(),
        "by_file_in_l1_rows": led.groupby("file")
        .in_l1_rows.sum()
        .astype(int)
        .to_dict(),
        "decided_after_l1_build": int((led.decided > "2026-10-23").sum()),
        "evidence_kinds": led.kinds.value_counts().to_dict(),
        **{k: v for k, v in scope(led.listing_id).items() if k != "listings"},
    }
}

# 2. The outlier sprint's commercial screen.
sp = pd.read_parquet(SPRINT)
sp = sp[sp.comm.notna()]
res["sprint_screen"] = scope(sp.listing_id) | {
    "also_ledger": int(sp.listing_id.astype(str).isin(set(led.listing_id)).sum())
}

# 3. S16's pattern and its reads.
pat = json.load(open(S16 + "patterns.json"))["nonresidential"]
res["s16_pattern"] = {k: pat[k] for k in ("rows", "train", "heldout", "units")} | {
    "held_outside_draw": pat["held"]
}
lab = (
    pd.read_parquet(S16 + "labels.parquet")
    .merge(pd.read_parquet(S16 + "key.parquet"), on="read_id")
    .merge(pd.read_parquet(S16 + "draw.parquet")[["listing_id", "group", "gap"]])
)
s16 = lab[lab.subtype == "nonresidential"]
res["s16_reads"] = {
    "reads": len(s16),
    "groups": s16.group.value_counts().to_dict(),
    "in_ledger": int(s16.listing_id.astype(str).isin(set(led.listing_id)).sum()),
}
res["s17_reads"] = scope(S17_IDS) | {
    "in_ledger": int(pd.Series(S17_IDS).isin(set(led.listing_id)).sum())
}

ids = pd.concat(
    [
        pd.DataFrame({"set": "ledger", "listing_id": led.listing_id.unique()}),
        pd.DataFrame({"set": "sprint_screen", "listing_id": sp.listing_id.astype(str)}),
        pd.DataFrame({"set": "s16_reads", "listing_id": s16.listing_id.astype(str)}),
        pd.DataFrame({"set": "s17_reads", "listing_id": S17_IDS}),
    ]
)
ids.to_parquet(OUT + "prior_ids.parquet", index=False)
led.to_parquet(OUT + "ledger_nonres.parquet", index=False)
json.dump(res, open(OUT + "prior.json", "w"), indent=1, default=int)
print(json.dumps(res, indent=1, default=int))
