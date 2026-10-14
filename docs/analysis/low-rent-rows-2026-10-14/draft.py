import numpy as np, pandas as pd, re

f = pd.read_parquet("/data1/apartments/tmp/suspect/lowrent/screen3.parquet")
PLACE = {
    "draft",
    "test",
    "tbd",
    "n/a",
    "na",
    "x",
    "xx",
    "xxx",
    "a",
    "info",
    "none",
    "-",
    ".",
}


def placeholder(t):
    if t is None or t != t:
        return False
    s = t.strip().lower()
    letters = re.sub(r"[^a-z]", "", s)
    return (
        s in PLACE
        or (len(letters) >= 1 and len(set(letters)) <= 2 and len(s.split()) <= 2)
        or "draft" in s.split()[:3]
    )


f["placeholder"] = f.description.apply(placeholder)
f["draft_ad"] = f.placeholder & f.only_withdrawn_day
for name in ["placeholder", "draft_ad"]:
    m = f[name]
    g = f[m & f.oth.notna()]
    print(
        f"{name:12s} n={int(m.sum()):5d} with_other={len(g):5d} far={g.far.mean():.4f} n_far={int(g.far.sum())}"
    )
print(
    f[f.placeholder]
    .description.str.strip()
    .str.lower()
    .value_counts()
    .head(25)
    .to_string()
)
print(
    f[f.draft_ad][
        ["canonical_unit_url", "description", "asking_rent", "bedrooms", "oth"]
    ]
    .assign(oth=lambda x: np.exp(x.oth).round())
    .to_string(max_colwidth=60)
)
