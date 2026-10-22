import json, os

R = "/data1/apartments/tmp/sim-recovery"


def r4(x):
    return None if x is None else round(float(x), 5)


out = {
    "model": "building-zones-floor",
    "source_run": "building-zones-floor-b0-latest-6b5a5b4a-dense-w1000",
    "level": 0.9,
    "runs": {},
}
for s in ("realistic", "null", "height"):
    p = f"{R}/{s}/score.json"
    if not os.path.exists(p):
        continue
    d = json.load(open(p))
    terms = [
        {
            "term": t["term"],
            "truth": r4(t["truth"]),
            "median": r4(t["median"]),
            "q05": r4(t["q05"]),
            "q95": r4(t["q95"]),
            "covered": t["covered"],
            "rows": t.get("rows"),
            "chains": [r4(c) for c in t["chain_medians"]],
        }
        for t in d["terms"] + d["noise"]
    ]
    curves = {
        g: [
            {
                "floor": r["floor"],
                "truth": r4(r["truth"]),
                "median": r4(r["median"]),
                "q05": r4(r["q05"]),
                "q95": r4(r["q95"]),
                "covered": r["covered"],
                "rows": r["rows"],
                "chains": [r4(c) for c in r["chain_medians"]],
            }
            for r in v
        ]
        for g, v in d["curves"].items()
    }
    maps = {
        z: {
            k: {
                "with_rows": {
                    a: r4(b) if isinstance(b, float) else b
                    for a, b in v[k]["with_rows"].items()
                },
                "by_rows": {
                    bn: {a: r4(b) if isinstance(b, float) else b for a, b in x.items()}
                    for bn, x in v[k]["by_rows"].items()
                },
            }
            for k in ("F", "bld", "level")
        }
        for z, v in d["maps"].items()
    }
    run = {
        "fit": d["run"],
        "diagnostics": d["diagnostics"],
        "seconds": d["seconds"],
        "summary": {k: v for k, v in d["summary"].items() if k != "misses"},
        "misses": [m["term"] for m in d["summary"]["misses"]],
        "terms": terms,
        "curves": curves,
        "maps": maps,
        "hyper": d["hyper"],
        "walk": [
            {
                "term": w["term"],
                "truth": r4(w["truth"]),
                "median": r4(w["median"]),
                "q05": r4(w["q05"]),
                "q95": r4(w["q95"]),
            }
            for w in d["walk"]
        ],
    }
    if "height" in d:
        run["height"] = d["height"]
    out["runs"][s] = run
x = (
    json.load(open(f"{R}/re_check.json"))
    if os.path.exists(f"{R}/re_check.json")
    else None
)
if x:
    out["building_unit_mix_correlation"] = x
json.dump(out, open(f"{R}/summary.json", "w"), separators=(",", ":"))
print(os.path.getsize(f"{R}/summary.json"), "bytes")
