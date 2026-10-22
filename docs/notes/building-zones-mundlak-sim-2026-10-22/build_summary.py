"""Compact summary of the building-means fit on the realistic simulation, next to run 1."""

import json

R = "/data1/apartments/tmp/sim-recovery/realistic"
OUT = "docs/notes/building-zones-mundlak-sim-2026-10-22/summary.json"


def r5(x):
    return None if x is None else round(float(x), 5)


def rows(ts):
    return [
        {
            "term": t["term"],
            "truth": r5(t["truth"]),
            "median": r5(t["median"]),
            "q05": r5(t["q05"]),
            "q95": r5(t["q95"]),
            "covered": t["covered"],
            "chains": [r5(c) for c in t["chain_medians"]],
        }
        for t in ts
    ]


out = {"model": "building-zones-mundlak", "level": 0.9, "runs": {}}
for key, f in (("run1_floor", "score.json"), ("fit_a_mundlak", "score-mundlak.json")):
    d = json.load(open(f"{R}/{f}"))
    out["runs"][key] = {
        "fit": d["run"],
        "diagnostics": d["diagnostics"],
        "seconds": d["seconds"],
        "summary": {k: v for k, v in d["summary"].items() if k != "misses"},
        "misses": [m["term"] for m in d["summary"]["misses"]],
        "terms": rows(d["terms"] + d["noise"]),
        "means": rows(d.get("extra_terms", [])),
        "bld_sd": d["hyper"]["bld_sd"],
        "amp": d["hyper"]["amp"],
        "maps": {
            z: {
                k: {
                    a: r5(b) if isinstance(b, float) else b
                    for a, b in v[k]["with_rows"].items()
                }
                for k in ("F", "bld", "level")
            }
            for z, v in d["maps"].items()
        },
    }
json.dump(out, open(OUT, "w"), separators=(",", ":"))
