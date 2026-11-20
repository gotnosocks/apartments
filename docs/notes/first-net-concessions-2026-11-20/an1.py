import json, pickle, numpy as np, pandas as pd

r = pd.read_parquet("/data1/apartments/tmp/po-firstnet/recs.parquet")
ids = pickle.load(open("/data1/apartments/tmp/po-firstnet/ids.pkl", "rb"))
r["c"] = pd.to_datetime(r.collected_at, unit="s")
r["lc"] = pd.to_datetime(r.last_collected_at, unit="s")
for k in ids:
    s = r[r.listing_id.isin(ids[k])]
    n = s.groupby("listing_id").size()
    print(
        k,
        "listings",
        n.size,
        "multi",
        (n > 1).sum(),
        "records dist",
        n.value_counts().sort_index().to_dict(),
    )
    print(
        " collected range",
        s.c.min(),
        s.c.max(),
        s.c.dt.to_period("M").value_counts().sort_index().to_dict(),
    )
    g = s.sort_values("c").groupby("listing_id")
    mfn = g.mf.agg(lambda v: len(set(np.nan_to_num(np.array(v, float)))))
    print(
        " listings with months-free differing across records",
        (mfn > 1).sum(),
        "of multi",
        (n > 1).sum(),
    )
    last = g.tail(1)
    print(" latest mf>0", (last.mf.fillna(0) > 0).sum())
    ch = mfn[mfn > 1].index[:6]
    for l in ch:
        print(
            s[s.listing_id == l]
            .sort_values("c")[
                ["listing_id", "c", "lc", "price", "mf", "ner", "lease", "status"]
            ]
            .to_string(header=False)
        )
