import json, sys

d = json.load(open(sys.argv[1]))
LBL = {
    "market": (
        "Market at the ask date",
        "The citywide level of rents for this date: intercept, the 12-year trend and the daily season.",
    ),
    "bedrooms": ("Five or more bedrooms", "Bedroom step against a one-bedroom."),
    "bathrooms": ("Three full baths", "Bath step against one bath."),
    "neighbourhood": ("Tribeca", "Neighbourhood level against Chelsea, the reference."),
    "building_drift": (
        "Building's own walk",
        "How this building has moved against the market over time, read at April 2025.",
    ),
    "building": (
        "Building's own level",
        "What the building earns beyond its measured attributes and its neighbourhood.",
    ),
    "unit": (
        "Unit's own effect",
        "What 5S earns beyond everything above, learned from its single listing.",
    ),
    "building size": (
        "Building size",
        "Height, apartment count, space per apartment and lot density.",
    ),
    "building status": ("Historic district", "Tribeca South Historic District."),
    "building_feature_slopes": (
        "Building's own slopes",
        "This building's own deviations on size, baths and floor.",
    ),
    "size": (
        "Square feet",
        "2,000 sq ft is the median for a 5-bed, so this adds nothing.",
    ),
    "building era": ("Built 1938", "Era 1930-1959 against 1900-1929."),
    "rooms beyond bedrooms": ("Nine rooms", "Four or more rooms beyond the bedrooms."),
    "elevator": (
        "Elevator not stated",
        "The ad leaves it blank; PLUTO says D7, an elevator building.",
    ),
    "bedroom_market_curve": (
        "Big-unit market curve",
        "The 3+ bedroom group's own path against the market.",
    ),
    "floor": ("5th floor", "Log floor."),
    "description": ("Ad text", "Renovated, no fee, high ceilings."),
    "relisting": ("First listing", "First time this unit was listed."),
    "doorman": ("Virtual doorman", ""),
    "hvac": ("Central air", ""),
    "views": ("City view", ""),
    "laundry": ("Laundry", ""),
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
            b["unit"],
            b["listed"] or b["off_market"],
            b["last_ask"],
            b["beds"],
            b["baths"],
            b["sqft"],
        ]
        for b in d["raw"]["building_listings"]
    ],
    comps=[
        [
            c["building"],
            c["first_day"][:10],
            c["latest_ask"],
            c["bedrooms"],
            c["bathrooms"],
            c["square_feet"],
        ]
        for c in d["raw"]["tribeca_comps"]
        if c["latest_ask"]
    ],
    typrow=dict(
        building=d["typical_row"]["building"],
        ask=d["typical_row"]["asking_rent"],
        fitted=round(d["typical_row"]["fitted_rent"]),
    ),
)
s = json.dumps(out, separators=(",", ":"))
open("payload.json", "w").write(s)
print(len(s), len(terms), [t["k"] for t in terms])
print(out["market"], out["total"]["f"], sum(t["f"][2] for t in terms))
print(out["pins"][:5])
