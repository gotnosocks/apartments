import json, sys
from pathlib import Path

HERE = Path(__file__).parent
d = json.load(open(sys.argv[1]))
LBL = {
    "market": (
        "Market at the ask date",
        "The citywide level of rents for 11 June 2026: intercept, trend and daily season.",
    ),
    "bedrooms": ("Two bedrooms", "Bedroom step against a one-bedroom."),
    "neighbourhood": (
        "Park Slope",
        "Neighbourhood level against Chelsea, the reference.",
    ),
    "building_drift": (
        "Building's own walk",
        "How this building has moved against the market since 2010, read at June 2026.",
    ),
    "building": (
        "Building's own level",
        "What the building earns beyond its measured attributes and its neighbourhood.",
    ),
    "unit": (
        "Unit's own effect",
        "What #2 earns beyond everything above, learned from its 2019, 2020 and 2023 listings.",
    ),
    "building_feature_slopes": (
        "Building's own slopes",
        "This building's own deviations on size, baths and floor.",
    ),
    "building class": ("Walk-up (class C)", "PLUTO class C0, a three-family walk-up."),
    "building size": (
        "Building size",
        "Three floors, three apartments, about 900 sq ft each, FAR 1.41.",
    ),
    "building status": ("Altered since 2000", "PLUTO records an alteration in 2002."),
    "size": (
        "Square feet not stated",
        "No ad for the unit gives a size; the size-unknown column applies.",
    ),
    "elevator": ("Elevator not stated", "The ad leaves it blank."),
    "laundry": ("Laundry not stated", "The ad leaves it blank."),
    "floor": (
        "Floor not coded",
        "The ad text says 2nd floor; the coded floor is unresolved, so the floor-unknown column applies.",
    ),
    "description": ("Ad text", "Dishwasher mentioned."),
    "bedroom_market_curve": (
        "Two-bed market curve",
        "The 2-bedroom group's own path against the market.",
    ),
    "views": ("Garden view", ""),
    "hvac": ("Central air", "Ductless split units, per the ad."),
    "relisting": ("Relisting", "Months since the unit's previous listing (about 29)."),
    "bathrooms": ("One bath", "The reference."),
    "building era": ("Built 1901", "Era 1900-1929, the reference."),
    "outdoor space": ("No outdoor space", "The reference."),
    "doorman": ("No doorman", "The reference."),
}


def q(x):
    return [round(x["log"][k], 4) for k in ("p2_5", "p10", "p50", "p90", "p97_5")]


terms = []
for t in d["terms"]:
    f = t["focus"]
    if max(abs(v) for v in q(f)) < 1e-4 and abs(t["typical"]["log"]["p50"]) < 1e-4:
        continue
    if t["term"] not in LBL:
        print("skip", t["term"])
        continue
    terms.append(
        dict(
            k=t["term"],
            lab=LBL[t["term"]][0],
            ex=LBL[t["term"]][1],
            f=q(f),
            sd=round(f["sd"], 4),
            cm=[round(c, 4) for c in f["chain_medians"]],
            dis=f["chains_disagree"],
            dr=[round(v, 4) for v in f.get("draws", [])][:200],
            t50=round(t["typical"]["log"]["p50"], 4),
            df=q(t["difference"]),
            usd=round(t["lmdi_usd"]["focus"]["p50"]),
        )
    )
mp = d["market_parts"]
P = d["predictive"]
out = dict(
    run=d["run"],
    draws=d["draws"],
    chains=d["chains"],
    total=dict(
        f=q(d["fitted"]["focus_log_total"]),
        cm=d["fitted"]["focus_log_total"]["chain_medians"],
        dr=[round(v, 4) for v in d["fitted"]["focus_log_total"]["draws"]],
    ),
    fitted=d["fitted"]["focus"],
    typical=d["fitted"]["typical"],
    market={k: round(mp[k]["log"]["p50"], 4) for k in mp},
    noise=dict(
        sigma=round(d["noise"]["sigma"]["log"]["p50"], 4),
        nu=round(d["noise"]["nu"]["log"]["p50"], 2),
        unit_scale=round(d["noise"]["unit_scale"]["log"]["p50"], 4),
    ),
    terms=terms,
    pred={
        k: {kk: round(vv, 3) for kk, vv in P[k].items()}
        for k in ("in_sample", "new_unit", "psis_loo_bundle")
    },
    pins=[round(v) for v in P["in_sample_draws"]],
    pnew=[round(v) for v in P["new_unit_draws"]],
    path=[
        [
            m["month"][:7],
            m["own"]["p2_5"],
            m["own"]["p10"],
            m["own"]["median"],
            m["own"]["p90"],
            m["own"]["p97_5"],
        ]
        for m in d["monthly_path"]
    ],
    bl=[
        [
            u["listing_id"],
            u["on_market"],
            u["last_ask"],
            u["first_ask"],
            u["method"],
            [[c[0], c[1]] for c in u["price_changes"]],
            u["off_market"],
            round(u["estimate"]),
            round(u["pit"], 3),
        ]
        for u in d["raw"]["listings"]
    ],
    comps=[
        [
            c["address"] + " #" + c["unit"],
            c["price_at"][:10],
            c["ask"],
            c["sqft"],
            round(c["miles"], 2),
            round(c["estimate"]) if c["estimate"] else None,
        ]
        for c in d["raw"]["comps"]["nearest"]
    ],
    cstat=dict(
        n=d["raw"]["comps"]["count"],
        med=d["raw"]["comps"]["median_ask"],
        q=d["raw"]["comps"]["quartiles"],
        n3=d["raw"]["comps"]["may_jul_2026_count"],
        med3=d["raw"]["comps"]["may_jul_2026_median"],
    ),
    typrow=dict(
        building=d["typical_row"]["building"],
        ask=d["typical_row"]["asking_rent"],
        fitted=round(d["typical_row"]["fitted_rent"]),
    ),
)
s = json.dumps(out, separators=(",", ":"))
# the page: head, the payload as a JSON script, then the scenes
page = (
    (HERE / "head.html").read_text()
    + '<script id="data" type="application/json">\n'
    + s.replace("</", "<\\/")
    + "\n</script>\n<script>\n"
    + (HERE / "app.js").read_text()
    + "</script>\n"
)
(HERE.parent / "explainer.html").write_text(page)
print(len(s), len(terms), [t["k"] for t in terms])
print(out["market"], out["total"]["f"], sum(t["f"][2] for t in terms))
print(out["pins"][:5])
