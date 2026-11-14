"""S17, part 5: the readers' verdicts scored, and candidate rules counted over the pool.

I join the three reading files to the sample and change row 25 from the reader's `studio` to
`unresolved`, leaning studio. Its two texts describe open sleeping areas, but the unit's 2014
and 2015 ads and line units 321, 421 and 521 code 1 to 2 bedrooms, and I told the readers to
settle a coded 0 as a studio only when nothing else contradicts it.

Then I count verdicts, backing kinds and room reasons in the sample. The precision of "a studio
coded on 5 or more rooms has more bedrooms than coded" counts a `bedrooms` verdict as a hit and
a `studio` or `other` verdict as a miss. I give it with 95% Wilson intervals over all 30 rows
(an unresolved row counts as a miss) and over the settled rows alone, for all room counts, for
5 rooms and for 6 or more. These raw figures describe the sample, in which held-out ads make 14
of 30 rows against 70 of the 893 pool rows outside S16's draw. For the pool I weight each cell
by its size and give stratified shares with their SEs:

- the share of each verdict, a stratified mean;
- the bedroom share of settled rows, a ratio of two stratified means, with a linearized SE.

From the ads file I add, for each pool row, whether the unit has an earlier ad coded 1 bedroom
or more, at any distance and within 730 days, to score prediction 5. Then for each candidate
rule I count the pool rows it marks (overall, held-out, units and buildings), the held-out ads
outside S16's draw it marks with L1's mean gap (SE clustered by building) and their share
inside the 80% interval, beside the same figures for the unmarked ads, the contrast between the
two means with a building-clustered SE, and the sample rows it marks with their verdicts. Last,
I estimate the gap of the 70 held-out ads after a fix by taking L1's bedroom step `delta_k` off
the gap of each ad a rule marks, where k is the unit's modal count; this is arithmetic on L1's
coefficients, not a refit. I write `scores.json`."""

import glob
import json

import numpy as np
import pandas as pd

OUT = "/data1/apartments/tmp/studio-rooms-2026-11-14/"
ADS = "/data1/apartments/pipeline/datasets/ads-3775f6d9b3e028ca.parquet"
Z = 1.959964


def wilson(k, n):
    if n == 0:
        return None
    p = k / n
    c = (p + Z * Z / (2 * n)) / (1 + Z * Z / n)
    h = Z * np.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / (1 + Z * Z / n)
    return {"k": int(k), "n": int(n), "p": p, "lo": c - h, "hi": c + h}


def cluster_mean_se(v, g):
    v = np.asarray(v, float)
    if len(v) < 2:
        return None
    t = pd.Series(v - v.mean()).groupby(np.asarray(g)).sum()
    if len(t) < 2:
        return None
    return float(np.sqrt(len(t) / (len(t) - 1) * (t**2).sum()) / len(v))


def cluster_contrast(v, m, g):
    """Marked mean less unmarked mean, with a CR1 building-clustered SE."""
    v, m = np.asarray(v, float), np.asarray(m, float)
    if m.sum() < 2 or (1 - m).sum() < 2:
        return None, None
    x = np.column_stack([np.ones_like(m), m])
    bread = np.linalg.inv(x.T @ x)
    beta = bread @ x.T @ v
    score = pd.DataFrame(x * (v - x @ beta)[:, None]).groupby(np.asarray(g)).sum()
    k = len(score)
    cov = bread @ (k / (k - 1) * score.T.values @ score.values) @ bread
    return float(beta[1]), float(np.sqrt(cov[1, 1]))


def stratified(g, y, x=None):
    """Pool share of y, or of y among rows with x, from whole sample cells, with its SE."""
    y = np.asarray(y, float)
    x = np.ones_like(y) if x is None else np.asarray(x, float)
    cells = pd.DataFrame({"cell": g.cell.values, "w": g.weight.values, "y": y, "x": x})
    c = cells.groupby("cell").agg(
        n=("y", "size"), w=("w", "first"), y=("y", "mean"), x=("x", "mean")
    )
    c["N"] = c.w * c.n
    big_y, big_x = (c.N * c.y).sum(), (c.N * c.x).sum()
    r = big_y / big_x
    cells["z"] = cells.y - r * cells.x
    c["s2"] = cells.groupby("cell").z.var(ddof=1).fillna(0.0)
    var = (c.N**2 * (1 - c.n / c.N) * c.s2 / c.n).sum() / big_x**2
    return {"p": float(r), "se": float(np.sqrt(var)), "pool_rows": float(c.N.sum())}


reads = pd.concat(
    pd.read_json(p, lines=True) for p in sorted(glob.glob(OUT + "reads/*.jsonl"))
)
assert sorted(reads.row_id) == list(range(30)), sorted(reads.row_id)
OVERRIDES = {25: {"verdict": "unresolved", "true_bedrooms": None, "lean": "studio"}}
for rid, change in OVERRIDES.items():
    for col, val in change.items():
        reads.loc[reads.row_id == rid, col] = val
feat = pd.read_parquet(OUT + "features.parquet")
SAMPLE_COLS = set(pd.read_parquet(OUT + "sample.parquet").columns)

# Whether the unit has an earlier ad coded 1 or more, at any distance and within 730 days.
ads = pd.read_parquet(ADS, columns=["listing_id", "unit_id", "on_day", "bedrooms"])
ads["day"] = pd.to_datetime(ads.on_day)
me = ads[ads.listing_id.isin(set(feat.listing_id)) & ads.unit_id.notna()]
ads = ads[ads.unit_id.isin(set(me.unit_id)) & (ads.bedrooms >= 1)]
pairs = me[["listing_id", "unit_id", "day"]].merge(
    ads, on="unit_id", suffixes=("", "_o")
)
pairs = pairs[(pairs.day_o < pairs.day) & (pairs.listing_id_o != pairs.listing_id)]
early = set(pairs.listing_id)
early_near = set(pairs.listing_id[(pairs.day - pairs.day_o).dt.days <= 730])
feat["unit_earlier_1plus"] = feat.listing_id.isin(early)
feat["unit_earlier_near_1plus"] = feat.listing_id.isin(early_near)
del ads, pairs
s = (
    pd.read_parquet(OUT + "sample.parquet")
    .merge(reads, on="row_id")
    .merge(
        feat[["listing_id"] + [c for c in feat if c not in SAMPLE_COLS]],
        on="listing_id",
    )
)
s["hit"] = s.verdict == "bedrooms"
s["settled"] = s.verdict != "unresolved"
res = {"verdicts": s.verdict.value_counts().to_dict()}
res["verdicts_weighted"] = (
    s.groupby("verdict").weight.sum() / s.weight.sum()
).to_dict()
res["by_cell"] = {c: g.verdict.value_counts().to_dict() for c, g in s.groupby("cell")}
for name, m in [
    ("all", s.index == s.index),
    ("5", s.bin == "5"),
    ("6+", s.bin != "5"),
    ("6-7", s.bin.isin(["6", "7"])),
    ("8-20", s.bin == "8-20"),
]:
    g = s[m]
    res[f"precision_{name}"] = {
        "all_rows": wilson(g.hit.sum(), len(g)),
        "settled": wilson(g.hit.sum(), g.settled.sum()),
        "unresolved": int((~g.settled).sum()),
        "weighted_hit_share": stratified(g, g.hit),
        "weighted_hit_share_settled": stratified(g, g.hit, g.settled),
        "weighted_unresolved_share": stratified(g, ~g.settled),
    }
res["verdicts_weighted_se"] = {
    v: stratified(s, s.verdict == v) for v in sorted(s.verdict.unique())
}
res["backing"] = s[s.settled].backing.explode().value_counts().to_dict()
res["backing_first"] = (
    s[s.settled]
    .backing.map(lambda v: v[0] if len(v) else "none")
    .value_counts()
    .to_dict()
)
res["rooms_reason"] = s.rooms_reason.value_counts().to_dict()
res["rooms_reason_by_verdict"] = {
    f"{v}/{r}": int(n)
    for (v, r), n in s.groupby(["verdict", "rooms_reason"]).size().items()
}
res["lean_unresolved"] = s[~s.settled].lean.value_counts().to_dict()

# Candidate rules over the pool.
f = feat
f["ukey"] = np.where(
    f.unit_id.isna(),
    "row:" + f.listing_id.astype(str),
    f.building + "|" + f.unit_id.astype(str),
)
rules = {
    "rooms_5plus (the pool)": f.rooms >= 5,
    "rooms_5": f.rooms == 5,
    "rooms_6plus": f.rooms >= 6,
    "rooms_6_7": f.rooms.between(6, 7),
    "unit_near_1plus": f.unit_near_1plus > 0,
    "unit_near_1plus_rooms": f.unit_near_1plus_rooms,
    "unit_near_all_1plus": f.unit_near_all_1plus,
    "unit_near_all_1plus_no_typed_studio": f.unit_near_all_1plus & ~f.unit_typed_studio,
    "unit_near_1plus_rooms_5_7": f.unit_near_1plus_rooms & (f.rooms <= 7),
    "unit_earlier_1plus": f.unit_earlier_1plus,
    "unit_earlier_near_1plus": f.unit_earlier_near_1plus,
    "line_1plus_rooms": f.line_1plus_rooms > 0,
    "size_900plus": f["size"] >= 900,
    "no_studio_in_text": ~f.says_studio & (f.desc_len > 80),
}
kept = f.held & ~f.s16_drawn
res["rules"] = {}
for name, m in rules.items():
    m = m.fillna(False).astype(bool)
    hm, hu = kept & m, kept & ~m
    sm = s.listing_id.isin(set(f.listing_id[m]))
    res["rules"][name] = {
        "rows": int(m.sum()),
        "held": int((m & f.held).sum()),
        "held_outside_s16": int(hm.sum()),
        "train": int((m & ~f.held).sum()),
        "units": int(f.ukey[m].nunique()),
        "buildings": int(f.building[m].nunique()),
        "gap_marked": float(f.gap[hm].mean()) if hm.any() else None,
        "gap_marked_se": cluster_mean_se(f.gap[hm], f.building[hm]),
        "in80_marked": float(f.in80[hm].mean()) if hm.any() else None,
        "gap_unmarked": float(f.gap[hu].mean()) if hu.any() else None,
        "gap_unmarked_se": cluster_mean_se(f.gap[hu], f.building[hu]),
        "in80_unmarked": float(f.in80[hu].mean()) if hu.any() else None,
        "contrast": cluster_contrast(f.gap[kept], m[kept], f.building[kept])[0],
        "contrast_se": cluster_contrast(f.gap[kept], m[kept], f.building[kept])[1],
        "sample_marked": s[sm].verdict.value_counts().to_dict(),
        "sample_precision": wilson(s[sm].hit.sum(), sm.sum()),
        "sample_precision_settled": wilson(s[sm].hit.sum(), (sm & s.settled).sum()),
    }
    for b in ["5", "6+"]:
        mb = m & ((f.rooms == 5) if b == "5" else (f.rooms >= 6))
        smb = sm & ((s.bin == "5") if b == "5" else (s.bin != "5"))
        res["rules"][name][f"rooms_{b}"] = {
            "rows": int(mb.sum()),
            "held_outside_s16": int((kept & mb).sum()),
            "gap": float(f.gap[kept & mb].mean()) if (kept & mb).any() else None,
            "sample": s[smb].verdict.value_counts().to_dict(),
        }

# The gap of the 70 after a fix by a history rule: L1's step off each marked ad.
for name in [
    "unit_near_1plus",
    "unit_near_1plus_rooms",
    "unit_near_all_1plus",
    "unit_earlier_near_1plus",
]:
    m = rules[name].fillna(False).astype(bool) & kept
    fixed = f.gap.where(~m, f.gap - f.delta_k)
    res[f"fixed_gap_{name}"] = {
        "ads": int(kept.sum()),
        "marked": int(m.sum()),
        "mean_gap_before": float(f.gap[kept].mean()),
        "mean_gap_after": float(fixed[kept].mean()),
        "marked_gap_before": float(f.gap[m].mean()) if m.any() else None,
        "marked_gap_after": float(fixed[m].mean()) if m.any() else None,
        "mean_delta": float(f.delta_k[m].mean()) if m.any() else None,
    }
# The same from the reads: held-out sample rows read as bedrooms, with the reader's count.
hs = s[s.held].copy()
post = np.load(
    "/data1/apartments/frontier/runs/drift-building-phase-b0-latest-9a7830fb-l1/posterior.npz",
    allow_pickle=True,
)
names = [str(n) for n in post["names"]]
b = dict(zip(names, post["kept/beta"].reshape(-1, len(names)).mean(axis=0)))


def bath_terms(k, full):
    return sum(b.get(f"bed={k}:full>={j}", 0.0) for j in (2, 3, 4) if full >= j)


def step(k, full):
    k, full = int(min(k, 5)), 1 if np.isnan(full) else full
    return (
        sum(b[f"bed>={j}"] for j in range(1, k + 1))
        + bath_terms(k, full)
        - bath_terms(0, full)
    )


hs["step"] = [
    step(k, fb) if v == "bedrooms" and pd.notna(k) else 0.0
    for v, k, fb in zip(hs.verdict, hs.true_bedrooms, hs.full_baths)
]
res["sample_held"] = {
    "rows": len(hs),
    "weighted_gap_before": float((hs.weight * hs.gap).sum() / hs.weight.sum()),
    "weighted_gap_after": float(
        (hs.weight * (hs.gap - hs.step)).sum() / hs.weight.sum()
    ),
    "rows_table": hs[
        [
            "row_id",
            "cell",
            "verdict",
            "true_bedrooms",
            "gap",
            "step",
            "k_unit",
            "unit_near_1plus",
            "unit_earlier_1plus",
        ]
    ]
    .round(3)
    .to_dict("records"),
}
json.dump(res, open(OUT + "scores.json", "w"), indent=1, default=str)
print(json.dumps(res, indent=1, default=str))
