import re, numpy as np, pandas as pd, pyarrow.parquet as pq
from scipy.stats import norm

d = np.load(
    "/data1/apartments/frontier/runs/drift-building-b0-latest-67d14e17-b9/pred_scores.npz",
    allow_pickle=True,
)
qs = list(d["quantiles"])
h = pd.DataFrame(
    {
        "listing_id": [str(x) for x in d["listing"]],
        "building": d["building"],
        "cdf": d["cdf"],
        "gap": d["y"] - d["pred"],
    }
)
h["z"] = np.clip(
    h.gap
    / ((d["q"][:, qs.index(0.75)] - d["q"][:, qs.index(0.25)]) / (2 * norm.ppf(0.75))),
    -6,
    6,
)
F = pq.read_table(
    "/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-bedtext/rows.parquet",
    columns=[
        "listing_id",
        "bed_flex_at",
        "bed_text_fewer",
        "bedrooms",
        "income_restricted",
    ],
).to_pandas()
F["listing_id"] = F.listing_id.astype(str)
F = F.drop_duplicates("listing_id").set_index("listing_id").reindex(h.listing_id)
h["flag"] = (F.bed_flex_at.fillna(False) | F.bed_text_fewer.fillna(False)).to_numpy()
h["beds"] = F.bedrooms.to_numpy()
h["inc"] = F.income_restricted.fillna(False).to_numpy(bool)
T = (
    pd.read_parquet("texts_b9.parquet")
    .set_index("listing_id")
    .text.reindex(h.listing_id)
    .fillna("")
)
half = (
    pd.read_parquet("held_b9.parquet", columns=["listing_id", "half"])
    .astype({"listing_id": str})
    .set_index("listing_id")
    .half.reindex(h.listing_id)
)
h["half"] = half.to_numpy()
h["text"] = T.to_numpy()
P = {
    "flexible layout/space": r"\bflexib(?:le|ility)\b[^.!]{0,50}\b(?:layout|floor ?plan|space|room|living|sleeping|bedroom|arrangement|usage|use)|\b(?:layout|floor ?plan|space|room|bedroom|arrangement)s?\b[^.!]{0,30}\bflexib(?:le|ility)",
    "flex create/wall": r"\bflexib\w+ to create\b|\bwall (?:is )?not (?:yet )?installed|\bcan (?:easily )?be (?:divided|walled|partitioned|converted)|\beasily conver",
    "office as room": r"\b(?:home )?office\b[^.!]{0,25}\b(?:or|/) ?(?:guest|nursery|bed|den|study)|\bbed(?:room)?s? ?(?:or|/) ?(?:home )?(?:office|den|study|nursery)|\bbedrooms? including an? (?:home )?office|\badditional rooms?\b[^.!]{0,30}\boffice|\b(?:office|den|study) ?/ ?(?:bed|guest)",
    "loft sleeping": r"\b(?:sleeping|sleep|bed) loft\b|\bloft(?:ed)? (?:bed|bedroom|sleeping|space with)|\bladder\b|\blofted\b",
    "railroad": r"\brail ?road\b",
    "studio word, beds>=1": r"\bstudio\b",
    "windowless/interior room": r"\bwindowless\b|\binterior (?:room|bedroom)|\bno window",
    "roommates/shares": r"\broom ?mates?\b|\bshares?\b[^.!]{0,15}\b(?:ok|welcome|friendly)|\bperfect for shar",
}
rng = np.random.default_rng(20261118)


def cv(z, x, fold):
    pred = np.empty_like(z)
    for k in range(5):
        tr = fold != k
        A = np.c_[np.ones(tr.sum()), x[tr]]
        b = np.linalg.lstsq(A, z[tr], rcond=None)[0]
        pred[~tr] = b[0] + b[1] * x[~tr]
    return 1 - ((z - pred) ** 2).sum() / ((z - z.mean()) ** 2).sum()


for name in ("read", "unread"):
    u = h[(h.half == name) & ~h.inc & ~h.flag].reset_index(drop=True)
    b = u.building.unique()
    fold = u.building.map(
        dict(zip(b, rng.permutation(np.arange(len(b)) % 5)))
    ).to_numpy()
    z = u.z.to_numpy()
    lo, ct, hi = (
        (u.cdf < 0.01).to_numpy(),
        ((u.cdf > 0.25) & (u.cdf < 0.75)).to_numpy(),
        (u.cdf > 0.99).to_numpy(),
    )
    print(
        name,
        len(u),
        "unflagged ads; flagged left out:",
        int((h.half.eq(name) & h.flag & ~h.inc).sum()),
    )
    for k, p in P.items():
        f = u.text.str.contains(p, regex=True).to_numpy().copy()
        if "studio" in k:
            f &= (u.beds >= 1).to_numpy()
        x = f.astype(float)
        e = cv(z, x, fold)
        n95 = np.quantile([cv(z, rng.permutation(x), fold) for _ in range(100)], 0.95)
        print(
            f"  {k:26s} n {f.sum():6d} below {100 * f[lo].mean():5.1f} ctl {100 * f[ct].mean():5.1f} above {100 * f[hi].mean():5.1f} gap {u.gap[f].mean():+.4f} other {u.gap[~f].mean():+.4f} expl {e:+.5f} null95 {n95:.5f} {'pass' if e > max(0, n95) else 'fail'}"
        )
