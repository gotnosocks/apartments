import json, sys, time, numpy as np, pandas as pd
from pathlib import Path
from rentfrontier import drift_deals as dd

run = Path(
    "/data1/apartments/frontier/runs/drift-building-bedtext-layout-range-b0-market-d9028c57-range-j"
)
ads = Path("/data1/apartments/pipeline/datasets/ads-14f9e88d75290a0f.parquet")
orig = dd.first_net


def variant(share, seed):
    def f(first, final, page, free):
        base = orig(first, final, page, free)
        first = np.asarray(first, float)
        rng = np.random.default_rng(seed)
        late = rng.random(len(base)) < share
        fr = np.nan_to_num(np.asarray(free, float)) > 0
        return np.where(fr & late & np.isfinite(base), first, base)

    return f


out = {}
for name, fn in (
    ("current", orig),
    ("all_late", variant(1.0, 0)),
    ("half_late_s1", variant(0.5, 1)),
    ("half_late_s2", variant(0.5, 2)),
    ("quarter_late", variant(0.25, 3)),
):
    dd.first_net = fn
    t = time.time()
    v = dd.validate(run, ads)
    out[name] = v
    print(
        name,
        round(time.time() - t),
        "s free",
        v["ads_with_free_months"],
        "of",
        v["ads_with_first_ask"],
        flush=True,
    )
    for key in ("by_first_ask_place",):
        for row in (v[key][0], v[key][1], v[key][-1]):
            print(
                "  ",
                row["place"],
                row["ads"],
                "raised %.1f cut %.1f med days %.0f medchg %.2f"
                % (
                    100 * row["share_raised"],
                    100 * row["share_cut"],
                    row["median_days_on_market"],
                    row["median_change_pct"],
                ),
            )
    u = v["uncautioned"]["by_first_ask_place"][0]
    print(
        "   uncautioned(no texts) d1",
        u["ads"],
        "raised %.1f" % (100 * u["share_raised"]),
    )
    w = v["without_free_months"]["by_first_ask_place"][0]
    print("   no-free d1", w["ads"], "raised %.1f" % (100 * w["share_raised"]))
json.dump(out, open("/data1/apartments/tmp/po-firstnet/val.json", "w"))
