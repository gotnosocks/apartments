"""Photo disagreement, part 3: the reads against the groups, the bar, and reader agreement.

The script reads every `reads/batch_NN.jsonl`, joins the labels to the draw through
`blind.parquet`, and computes on the first reads:

- each category's count and share in A, B, R and A47 (the group A ads with `none_apparent`
  from the text readers), with a building-clustered SE, and the differences A less B, A less
  R, A47 less B and A47 less R with clustered SEs;
- the mean condition and light grade of each group and the same differences;
- the bar: a category with at least 8 reads in A (or A47) and a share at least twice the
  share in B and in R, or a grade difference above 3 SEs;
- the number of category flags from chance: 5,000 shuffles of the group labels, with the
  ads of a building kept next to each other in the shuffled order.

The reader categories and the grades take as their base the ads with at least one photo
read. `few_photos` takes every ad. On the ads read twice the script computes Cohen's kappa
for each reader category and the correlation of each grade. It prints the tables and writes
`score.json` and `reads.parquet`."""

import glob
import json

import numpy as np
import pandas as pd
from scipy import stats

OUT = "/data1/apartments/tmp/photo-disagreement-2026-11-14/"
SCREEN = "/data1/apartments/tmp/market-disagreement-2026-11-14/"
READER_CATS = [
    "dark_or_shaft",
    "low_ceiling",
    "awkward_layout",
    "tiny_or_windowless_bedroom",
    "kitchen_poor",
    "bath_poor",
    "worn_finishes",
    "ground_or_basement",
    "street_noise_cues",
    "other_unit_or_renderings",
]
CATS = [*READER_CATS, "few_photos", "nothing_wrong"]
GRADES = ["condition", "light"]
GROUPS = {"A_cheap_slow": "A", "B_cheap_fast": "B", "R_random": "R"}
MIN_READS, RATIO, GRADE_SES, SHUFFLES, SEED = 8, 2.0, 3.0, 5000, 20261114

lines = []
for path in sorted(glob.glob(OUT + "reads/batch_*.jsonl")):
    for s in open(path):
        if s.strip():
            lines.append(json.loads(s))
reads = pd.DataFrame(lines)
assert reads.label.is_unique, reads.label[reads.label.duplicated()].tolist()
unknown = {c for cs in reads.categories for c in cs} - set(READER_CATS)
assert not unknown, unknown
blind = pd.read_parquet(OUT + "blind.parquet")
draw = pd.read_parquet(SCREEN + "draw.parquet")
draw["listing_id"] = draw.listing_id.astype(str)
text = pd.read_parquet(SCREEN + "reads.parquet")[["listing_id", "category"]]
text["listing_id"] = text.listing_id.astype(str)
d = blind.merge(reads, on="label", how="left", validate="1:1")
print("labels with no read:", d.photos.isna().sum())
d = d.merge(draw[["listing_id", "building", "group", "gap1", "D"]], on="listing_id")
d = d.merge(text.rename(columns={"category": "text_cause"}), on="listing_id")
d["group"] = d.group.map(GROUPS)
d["seen"] = d.photos.fillna(0) > 0
for c in READER_CATS:
    d[c] = [float(c in (cs if isinstance(cs, list) else [])) for cs in d.categories]
d["nothing_wrong"] = (d[READER_CATS].sum(axis=1) == 0).astype(float)
d["few_photos"] = d.few_photos.astype(float)
for c in [*READER_CATS, "nothing_wrong", *GRADES]:
    d.loc[~d.seen, c] = np.nan
for g in GRADES:
    d[g] = pd.to_numeric(d[g], errors="coerce")
d.to_parquet(OUT + "reads.parquet")
first = d[~d.repeat].reset_index(drop=True)
first["a47"] = (first.group == "A") & (first.text_cause == "none_apparent")
print("A47 ads:", int(first.a47.sum()))


def mean_se(x, building):
    """The mean of `x` over its non-missing values and its building-clustered SE."""
    keep = x.notna()
    x, building = x[keep], building[keep]
    m = x.mean()
    sums = (x - m).groupby(building).sum()
    return m, np.sqrt((sums**2).sum()) / len(x), len(x)


def diff_se(x, building, one, two):
    """The mean of `x` in mask `one` less its mean in mask `two`, with an SE clustered on
    buildings over both masks."""
    keep = x.notna()
    a, b = one & keep, two & keep
    ma, mb = x[a].mean(), x[b].mean()
    u = pd.Series(0.0, index=x.index)
    u[a] = (x[a] - ma) / a.sum()
    u[b] -= (x[b] - mb) / b.sum()
    return ma - mb, np.sqrt((u.groupby(building).sum() ** 2).sum())


def flags(table, case, b, r):
    """The categories over the bar for mask `case` against masks `b` and `r`."""
    out = []
    for c in CATS:
        n = table.loc[case, c].sum()
        s = table.loc[case, c].mean()
        if n >= MIN_READS and s >= RATIO * table.loc[b, c].mean():
            if s >= RATIO * table.loc[r, c].mean():
                out.append(c)
    return out


masks = {
    "A": first.group == "A",
    "A47": first.a47,
    "B": first.group == "B",
    "R": first.group == "R",
}
score = {"categories": {}, "grades": {}, "flags": {}, "chance": {}, "agreement": {}}
print("\ncategory: count, share % (SE) by group; differences in points (SE)")
for c in CATS:
    row = {}
    for name, mask in masks.items():
        m, se, n = mean_se(first.loc[mask, c], first.loc[mask, "building"])
        row[name] = {
            "count": int(first.loc[mask, c].sum()),
            "n": n,
            "share": round(100 * m, 1),
            "se": round(100 * se, 1),
        }
    for case in ("A", "A47"):
        for control in ("B", "R"):
            diff, se = diff_se(first[c], first.building, masks[case], masks[control])
            row[f"{case}-{control}"] = [round(100 * diff, 1), round(100 * se, 1)]
    score["categories"][c] = row
    print(
        f"{c:27s}",
        " ".join(
            f"{k} {row[k]['count']:3d}/{row[k]['n']:3d} {row[k]['share']:5.1f} ({row[k]['se']:.1f})"
            for k in masks
        ),
        "|",
        " ".join(f"{k} {row[k][0]:+.1f} ({row[k][1]:.1f})" for k in row if "-" in k),
    )
print("\ngrade: mean (SE) n by group; differences (SE, t)")
for g in GRADES:
    row = {}
    for name, mask in masks.items():
        m, se, n = mean_se(first.loc[mask, g], first.loc[mask, "building"])
        row[name] = {"mean": round(m, 3), "se": round(se, 3), "n": n}
    for case in ("A", "A47"):
        for control in ("B", "R"):
            diff, se = diff_se(first[g], first.building, masks[case], masks[control])
            row[f"{case}-{control}"] = [
                round(diff, 3),
                round(se, 3),
                round(diff / se, 2),
            ]
    row["flag_A"] = bool(max(abs(row["A-B"][2]), abs(row["A-R"][2])) > GRADE_SES)
    row["flag_A47"] = bool(max(abs(row["A47-B"][2]), abs(row["A47-R"][2])) > GRADE_SES)
    score["grades"][g] = row
    print(
        f"{g:10s}",
        " ".join(
            f"{k} {row[k]['mean']:.2f} ({row[k]['se']:.2f}) {row[k]['n']}"
            for k in masks
        ),
        "|",
        " ".join(
            f"{k} {row[k][0]:+.2f} ({row[k][1]:.2f}, t {row[k][2]:+.1f})"
            for k in row
            if "-" in k
        ),
    )

rng = np.random.default_rng(SEED)
for case in ("A", "A47"):
    found = flags(first, masks[case], masks["B"], masks["R"])
    score["flags"][case] = found
    pool = first[masks[case] | masks["B"] | masks["R"]].reset_index(drop=True)
    sizes = [int(masks[k].sum()) for k in (case, "B", "R")]
    buildings = pool.building.unique()
    position = {b: np.flatnonzero(pool.building.to_numpy() == b) for b in buildings}
    counts = np.zeros(SHUFFLES, dtype=int)
    by_cat = dict.fromkeys(CATS, 0)
    for i in range(SHUFFLES):
        order = np.concatenate([position[b] for b in rng.permutation(buildings)])
        idx = np.empty(len(pool), dtype=int)
        idx[order] = np.arange(len(pool))
        one = pd.Series(idx < sizes[0])
        two = pd.Series((idx >= sizes[0]) & (idx < sizes[0] + sizes[1]))
        three = pd.Series(idx >= sizes[0] + sizes[1])
        hit = flags(pool, one, two, three)
        counts[i] = len(hit)
        for c in hit:
            by_cat[c] += 1
    score["chance"][case] = {
        "mean_flags": round(float(counts.mean()), 3),
        "share_any": round(float((counts > 0).mean()), 3),
        "share_at_least_observed": round(float((counts >= len(found)).mean()), 3),
        "by_category": {c: round(n / SHUFFLES, 3) for c, n in by_cat.items() if n},
    }
    print(f"\nflags for {case}: {found}; chance: {score['chance'][case]}")

rep = d[d.repeat].merge(first, on="listing_id", suffixes=("_2", "_1"))
rep = rep[rep.seen_1 & rep.seen_2]
print(f"\nagreement on {len(rep)} ads read twice")
for c in [*READER_CATS, "nothing_wrong"]:
    a, b = rep[c + "_1"], rep[c + "_2"]
    po = (a == b).mean()
    pe = a.mean() * b.mean() + (1 - a.mean()) * (1 - b.mean())
    kappa = (po - pe) / (1 - pe) if pe < 1 else float("nan")
    score["agreement"][c] = {
        "first": int(a.sum()),
        "second": int(b.sum()),
        "both": int((a * b).sum()),
        "kappa": None if np.isnan(kappa) else round(float(kappa), 2),
    }
    print(f"{c:27s}", score["agreement"][c])
for g in GRADES:
    both = rep[[g + "_1", g + "_2"]].dropna()
    score["agreement"][g] = {
        "n": len(both),
        "pearson": round(float(stats.pearsonr(both.iloc[:, 0], both.iloc[:, 1])[0]), 2),
        "spearman": round(
            float(stats.spearmanr(both.iloc[:, 0], both.iloc[:, 1])[0]), 2
        ),
        "within_1": round(
            float(((both.iloc[:, 0] - both.iloc[:, 1]).abs() <= 1).mean()), 2
        ),
        "equal": round(float((both.iloc[:, 0] == both.iloc[:, 1]).mean()), 2),
    }
    print(g, score["agreement"][g])

with open(OUT + "score.json", "w") as sink:
    json.dump(score, sink, indent=1)
