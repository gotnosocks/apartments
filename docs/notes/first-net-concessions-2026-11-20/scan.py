import json, sys, collections, pickle
import numpy as np, pandas as pd, pyarrow.parquet as pq
from pathlib import Path
from rentfrontier import drift_deals

R = Path("/data1/apartments/frontier/runs")
runs = {
    "j": R / "drift-building-bedtext-layout-range-b0-market-d9028c57-range-j",
    "m3": R / "drift-building-bedtext-layout-range-b0-market-6cd1f12b-range-m3",
}
ids = {}
for k, r in runs.items():
    _, h, _ = drift_deals._held_frame(r)
    ids[k] = set(h.listing_id.astype(int))
    print(k, len(ids[k]))
want = ids["j"] | ids["m3"]
f = pq.ParquetFile(
    "/data1/apartments/pipeline/datasets/records-941f4a6588cbd8cc.parquet"
)
out = []
keys = collections.Counter()
pk = collections.Counter()
nrec = collections.Counter()
yr = collections.defaultdict(collections.Counter)
rng = np.random.default_rng(0)
for g in range(f.metadata.num_row_groups):
    lid = f.read_row_group(
        g, columns=["listing_id", "collected_at", "last_collected_at", "listing_type"]
    ).to_pandas()
    nrec.update(lid.listing_id.tolist())
    m = lid.listing_id.isin(want).to_numpy()
    samp = rng.random(len(lid)) < 0.01
    sel = np.flatnonzero(m | samp)
    if not len(sel):
        continue
    js = (
        f.read_row_group(g, columns=["raw_listing_json"])
        .column(0)
        .take(sel)
        .to_pylist()
    )
    for i, s in zip(sel, js):
        d = json.loads(s)
        p = d.get("pricing") or {}
        pc = p.get("priceChanges") or []
        if samp[i]:
            pk.update(p.keys())
            for c in pc:
                keys.update(c.keys())
            y = (d.get("onMarketAt") or d.get("createdAt") or "????")[:4]
            yr[y]["n"] += 1
            yr[y]["mf"] += (p.get("monthsFree") or 0) > 0
            yr[y]["ner"] += p.get("netEffectiveRent") is not None
            yr[y]["pc"] += len(pc) > 0
            yr[y]["type_" + str(lid.listing_type.iat[i])] += 1
        if m[i]:
            out.append(
                dict(
                    listing_id=int(lid.listing_id.iat[i]),
                    collected_at=lid.collected_at.iat[i],
                    last_collected_at=lid.last_collected_at.iat[i],
                    price=p.get("price"),
                    mf=p.get("monthsFree"),
                    ner=p.get("netEffectiveRent"),
                    lease=p.get("leaseTermMonths"),
                    pc=json.dumps(pc),
                    status=d.get("status"),
                    on=d.get("onMarketAt"),
                    sc=json.dumps(d.get("statusChanges")),
                    topkeys=",".join(sorted(d.keys())),
                )
            )
print("priceChange keys", keys)
print("pricing keys", pk)
for y in sorted(yr):
    print(y, dict(yr[y]))
c = collections.Counter(nrec.values())
print("records per listing", sorted(c.items())[:10])
pd.DataFrame(out).to_parquet("/data1/apartments/tmp/po-firstnet/recs.parquet")
pickle.dump(ids, open("/data1/apartments/tmp/po-firstnet/ids.pkl", "wb"))
