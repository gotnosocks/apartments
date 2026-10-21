import json

d = json.load(open("explainer-data.json"))
s = json.load(open("summ.json"))
h = json.load(open("heldout.json"))
c = json.load(open("contrib.json"))
sc = json.load(open("screen.json"))
d["convergence_note"] = (
    "fails the gate: max R-hat 1.0149 on amp[outer] against 1.01; chain medians of amp[outer] 0.371, 0.375, 0.379, 0.381; every other quantity passes"
)
d["summary"] = {
    "gym_run": s["gym"],
    "unit_run": {
        k: s["unit"][k] for k in ("run", "coef", "zones", "nu", "sigma", "zone_gap_pct")
    },
    "attrs_run": {k: s["attrs"][k] for k in ("run", "coef", "zones")},
}
d["t_variance"] = {
    "note": "variance of T = error + building effect + map value (posterior means), demeaned within zone, over training ads",
    "attrs": 0.0622,
    "unit": 0.0530,
    "gym": c["T_gym"],
    "gym_zone": {"manhattan": c["T_gym_zone"]["0"], "outer": c["T_gym_zone"]["1"]},
}
d["contrib"] = {
    "note": "x.gamma at posterior means per group; rise_alone = rise in T variance when the group's contribution is added back alone; shapley = average rise over the 24 orderings of the four groups",
    **c,
}
d["screen"] = {
    "note": "share of each run's building effects (posterior mean, weighted by inverse posterior variance) explained by the building gym flag, grouped 5-fold CV, against 50 permutations",
    **sc,
}
d["heldout"] = {
    "note": "latest split, 189,649 held-out ads, 68 draws per run (every 8th kept); elpd differences are gym run minus the named run; err = log ask - posterior median of mu",
    **h,
}
d["predictions"] = [
    [
        "G1",
        "gym premium +1% to +5%, median near +3%",
        "+7.64% (7.12 to 8.16)",
        "miss: above the range",
    ],
    [
        "G2",
        "doorman full-time falls 2 to 4 points; part-time and elevator 1 to 3; condo under 2",
        "full-time 17.17 to 14.05; part-time 11.08 to 8.43; elevator 7.98 to 6.69; condo 10.86 to 10.47",
        "hit",
    ],
    [
        "G3",
        "size, laundry and dishwasher premiums each move under 1 point",
        "largest move 0.03 points",
        "hit",
    ],
    [
        "G4",
        "truck-route ads' predicted log rent changes under 0.5 points on average",
        "+0.04 points on training ads, +0.04 on held-out ads",
        "hit",
    ],
    [
        "G5",
        "T variance falls from 0.0530 by under 0.001",
        "0.0511, a fall of 0.0019",
        "miss: fell twice as much as predicted",
    ],
    [
        "G6",
        "gym explains 5% to 15% of the unit run's building effects, above the null",
        "1.1% (null 95th percentile below 0)",
        "miss: beats the null, far below the range",
    ],
    [
        "G7",
        "held-out elpd rises 0 to 1,500 against the unit run; RMSE moves under 0.001",
        "elpd -11 (SE 3); RMSE 0.11731 to 0.11732",
        "miss on elpd, hit on RMSE",
    ],
    [
        "G8",
        "converges within the 1 hour cap at about $0.45",
        "9.6 min, $0.38, max R-hat 1.015 on amp[outer]",
        "miss: fails the R-hat gate",
    ],
]
json.dump(d, open("explainer-data.json", "w"), separators=(",", ":"))
