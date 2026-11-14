"""Counts for label-join: the history pairs v17 joins and v18 keeps or splits, the label units
split, the label-month drops v18 undoes, and L1's rows and held-out ads in split units."""

import importlib.util
import json
import sys

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

STR = {
    pa.string(): pd.StringDtype("pyarrow"),
    pa.large_string(): pd.StringDtype("pyarrow"),
}.get


def read(path, columns):
    """A parquet file with its strings held by Arrow, which takes less memory."""
    return pq.read_table(path, columns=columns).to_pandas(types_mapper=STR)


WT = sys.argv[1]
S = "/data1/apartments/tmp/sprint-20261113/label-join"
D = "/data1/apartments/pipeline/datasets"
L1 = "/data1/apartments/frontier/runs/drift-building-phase-b0-latest-9a7830fb-l1"
L1DS = "/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cluster_se(x, b):
    """SE of the sum of `x` about its mean, clustered by `b`."""
    x = np.asarray(x, dtype=float)
    t = pd.Series(x - x.mean()).groupby(np.asarray(b)).sum()
    return float(np.sqrt(len(t) / (len(t) - 1) * (t**2).sum()))


def diff_se(x, a, b):
    """SE of the mean of `x` where `a` holds less its mean elsewhere, with both groups clustered
    together by `b`: each building sums its ads' parts of the difference."""
    x = np.asarray(x, dtype=float)
    a = np.asarray(a, dtype=bool)
    part = np.where(a, (x - x[a].mean()) / a.sum(), -(x - x[~a].mean()) / (~a).sum())
    t = pd.Series(part).groupby(np.asarray(b)).sum()
    return float(np.sqrt(len(t) / (len(t) - 1) * (t**2).sum()))


lu = load("label_units", f"{WT}/pipeline/models/analysis/label_units.py")
res = {}

# History pairs: the ones v17's layer 4 joins, and what v18 does with them.
pairs = pd.read_parquet(f"{S}/pairs.parquet")
pages = pd.read_parquet(f"{S}/pages.parquet", columns=["unit_id", "pages"])
pages = pages[pages.unit_id.isin(set(pairs.unit_id) | set(pairs.other_unit_id))]
every = pages.explode("pages")
every["label"] = every.pages.str.extract(lu.PAGE)[1]
print("pages", len(every), flush=True)
keys = lu.spelling_keys(every[["unit_id", "label"]])
labels = every.groupby("unit_id").label.agg(lambda x: sorted(set(x.dropna())))
del pages, every
p17 = read(f"{S}/page_units_v17.parquet", None).set_index("page_unit")
p18 = read(f"{S}/page_units_v18.parquet", None).set_index("page_unit")
both = pairs.unit_id.isin(p17.index) & pairs.other_unit_id.isin(p17.index)
pr = pairs[both].copy()
for side, col in (("a", "unit_id"), ("b", "other_unit_id")):
    pr[f"{side}3"] = p17.after3.reindex(pr[col]).to_numpy()
    pr[f"{side}4"] = p17.after4.reindex(pr[col]).to_numpy()
    pr[f"{side}f17"] = p17.final.reindex(pr[col]).to_numpy()
    pr[f"{side}f18"] = p18.final.reindex(pr[col]).to_numpy()
    pr[f"{side}_labels"] = labels.reindex(pr[col]).to_numpy()
pr["agree"] = [
    bool(keys.get(u, set()) & keys.get(v, set()))
    for u, v in zip(pr.unit_id, pr.other_unit_id)
]
pr["blank"] = [
    not keys.get(u) or not keys.get(v) for u, v in zip(pr.unit_id, pr.other_unit_id)
]
pr["joined17"] = (pr.a3 != pr.b3) & (pr.a4 == pr.b4)
pr["apart18"] = pr.af18 != pr.bf18
res["pairs"] = {
    "all": len(pairs),
    "with_rows_both_sides": int(both.sum()),
    "agree": int(pr.agree.sum()),
    "blank_side": int(pr.blank.sum()),
    "joined_by_v17_history": int(pr.joined17.sum()),
    "joined17_agree": int((pr.joined17 & pr.agree).sum()),
    "joined17_blank_side": int((pr.joined17 & pr.blank).sum()),
    "joined17_apart_in_v18": int((pr.joined17 & pr.apart18).sum()),
    "joined17_disagree_but_together_in_v18": int(
        (pr.joined17 & ~pr.agree & ~pr.apart18).sum()
    ),
}
pr.to_parquet(f"{S}/pairs_classified.parquet")

# Label units: each v17 label unit of page units with rows, split when its page units fall in
# two or more v18 label units.
pu = pd.DataFrame({"f17": p17.final, "f18": p18.final.reindex(p17.index)})
n18 = pu.groupby("f17").f18.nunique()
split_units = n18[n18 > 1]
res["label_units"] = {
    "v17_multi_page": int((pu.groupby("f17").size() > 1).sum()),
    "v18_multi_page": int((pu.groupby("f18").size() > 1).sum()),
    "v17_split": len(split_units),
    "v18_units_from_split": int(split_units.sum()),
    "page_units_in_split": int(pu.f17.isin(split_units.index).sum()),
}
del p17, p18
print("label units", flush=True)

# Rows: the ledger's rows under both rules.
u = read(
    f"{S}/units.parquet",
    columns=[
        "listing_id",
        "dropped",
        "bedrooms",
        "price_at",
        "period",
        "label17",
        "label18",
        "split_unit",
        "split17",
        "split18",
        "building",
    ],
)
kept = ~u.dropped.to_numpy()
ads = read(
    f"{D}/ads-3775f6d9b3e028ca.parquet",
    columns=["listing_id", "first_day", "bathrooms", "label_fate"],
)
ads = ads[ads.listing_id.isin(set(u.listing_id))].set_index("listing_id")
baths = read(f"{D}/rows-b3ddebf19af1dc1e.parquet", ["listing_id", "bathrooms"])
baths = baths.set_index("listing_id").bathrooms
u["bathrooms"] = baths.reindex(u.listing_id).to_numpy()
drop = ~kept
first = pd.to_datetime(
    ads.first_day.reindex(u.listing_id[drop]).to_numpy()
).tz_localize("UTC")
u.loc[drop, "bathrooms"] = ads.bathrooms.reindex(u.listing_id[drop]).to_numpy()
u.loc[drop, "price_at"] = first
u.loc[drop, "period"] = first
u["period"] = pd.to_datetime(u.period, utc=True)
fate = ads.label_fate.reindex(u.listing_id).to_numpy()
del ads, baths


def months(r, label):
    """label_months' fate for each row of `r` under `label`."""
    lab = pd.factorize(r[label])[0]
    per = (r.period.dt.year * 12 + r.period.dt.month).to_numpy()
    price = r.price_at.astype("int64").to_numpy()
    lid = pd.factorize(r.listing_id, sort=True)[0]
    k = pd.DataFrame(
        {
            "lab": lab,
            "per": per,
            "bed": r.bedrooms.to_numpy(),
            "bath": r.bathrooms.to_numpy(),
        }
    )
    g = k.groupby(["lab", "per"])
    out = np.full(len(r), None, dtype=object)
    for col in ("bed", "bath"):
        mn, mx = g[col].transform("min"), g[col].transform("max")
        bad = (mn != mx) & mn.notna() & mx.notna()
        out[bad.to_numpy()] = "conflicting_layout_same_label_month"
    order = np.lexsort((-lid, -price, per, lab))
    first = np.r_[
        True, (lab[order][1:] != lab[order][:-1]) | (per[order][1:] != per[order][:-1])
    ]
    sup = np.zeros(len(r), bool)
    sup[order[~first]] = True
    out[sup & (out == None)] = "superseded_in_label_month"  # noqa: E711
    return out


# A row's fate can change only in a v17 label unit v18 splits, so the check runs on those rows.
n = u.groupby("label17").label18.nunique()
sub = u.label17.isin(set(n[n > 1].index)).to_numpy()
r = u[sub]
print("rows read", sub.sum(), flush=True)
m17 = months(r, "label17")
f = pd.Series(fate[sub]).where(pd.notna(fate[sub]), None).to_numpy()
m18 = months(r, "label18")
res["label_months"] = {
    "rows_checked": int(sub.sum()),
    "build_dropped_in_checked": int((f != None).sum()),  # noqa: E711
    "v17_dropped": int((m17 != None).sum()),  # noqa: E711
    "v17_differs_from_build": int(sum(a != b for a, b in zip(m17, f))),
    "v18_dropped": int((m18 != None).sum()),  # noqa: E711
    "back_in_v18": int(((m17 != None) & (m18 == None)).sum()),  # noqa: E711
    "newly_dropped_in_v18": int(((m17 == None) & (m18 != None)).sum()),  # noqa: E711
}
del r

del u, fate, f, m17, m18
print("label months", flush=True)

# Kept rows and L1's rows, joined in DuckDB, which spills to disk.
import duckdb  # noqa: E402

c = duckdb.connect()
c.execute(
    "set memory_limit='1500MB'; set threads=2; set preserve_insertion_order=false;"
    f"set temp_directory='{S}/duck'"
)
U = f"read_parquet('{S}/units.parquet')"
row = c.execute(f"""
    SELECT count(*), count(*) FILTER (split17 = split_unit), count(*) FILTER (label17 != label18),
        count(*) FILTER (split17 != split18)
    FROM {U} WHERE NOT dropped""").fetchone()
c.execute(f"""
    CREATE TEMP TABLE split AS SELECT split17 FROM {U} WHERE NOT dropped
    GROUP BY 1 HAVING count(DISTINCT split18) > 1""")
res["rows"] = {
    "kept": row[0],
    "split17_matches_build": row[1],
    "label_unit_changes": row[2],
    "unit_changes": row[3],
    "units_split": c.execute("SELECT count(*) FROM split").fetchone()[0],
    "rows_in_units_split": c.execute(
        f"SELECT count(*) FROM {U} WHERE NOT dropped AND split17 IN (SELECT split17 FROM split)"
    ).fetchone()[0],
}
print("rows", flush=True)
c.execute(f"""
    COPY (
        SELECT l.file_row_number AS i, l.listing_id::VARCHAR AS listing_id, l.unit_id,
            u.split17, u.split18, u.split17 IN (SELECT split17 FROM split) AS insplit
        FROM read_parquet('{L1DS}/rows.parquet', file_row_number = true) l
        LEFT JOIN (SELECT listing_id::VARCHAR AS listing_id, split17, split18 FROM {U}
            WHERE NOT dropped) u ON u.listing_id = l.listing_id::VARCHAR
        ORDER BY 1
    ) TO '{S}/l1_units.parquet'""")
print("l1 units", flush=True)
l1 = c.execute(f"""
    SELECT listing_id, split17 IS NULL AS missing, coalesce(split17 = unit_id, false) AS same,
        coalesce(split17 != split18, false) AS change, coalesce(insplit, false) AS insplit
    FROM read_parquet('{S}/l1_units.parquet') ORDER BY i""").df()
n_l1_split = c.execute(
    f"SELECT count(DISTINCT split17) FROM read_parquet('{S}/l1_units.parquet') WHERE insplit"
).fetchone()[0]
s = np.load(f"{L1}/pred_scores.npz", allow_pickle=True)
held = s["heldout"]
assert len(held) == len(l1)
assert (l1.listing_id.to_numpy()[held].astype(str) == s["listing"].astype(str)).all()
change = l1.change.to_numpy()
insplit = l1.insplit.to_numpy()
res["l1"] = {
    "rows": len(l1),
    "missing_from_build": int(l1.missing.sum()),
    "unit_matches_split17": int(l1.same.sum()),
    "rows_changing_unit": int(change.sum()),
    "rows_in_units_split": int(insplit.sum()),
    "units_split": int(n_l1_split),
    "heldout": int(held.sum()),
    "heldout_changing_unit": int(change[held].sum()),
    "heldout_in_units_split": int(insplit[held].sum()),
}
gap = s["y"] - s["pred"]
b = s["building"]
gaps = {}
for name, g in (("in_units_split", insplit[held]), ("changing_unit", change[held])):
    for side, mask in ((name, g), (f"not_{name}", ~g)):
        n = int(mask.sum())
        gaps[side] = {
            "n": n,
            "gap_pct": 100 * float(gap[mask].mean()),
            "gap_se_pct": 100 * cluster_se(gap[mask], b[mask]) / n,
            "sq_gap": float((gap[mask] ** 2).mean()),
            "sq_gap_se": cluster_se(gap[mask] ** 2, b[mask]) / n,
            "elpd": float(s["elpd"][mask].mean()),
        }
    gaps[f"{name}_minus_rest"] = {
        "gap_pct": 100 * float(gap[g].mean() - gap[~g].mean()),
        "gap_se_pct": 100 * diff_se(gap, g, b),
        "sq_gap": float((gap[g] ** 2).mean() - (gap[~g] ** 2).mean()),
        "sq_gap_se": diff_se(gap**2, g, b),
        "elpd": float(s["elpd"][g].mean() - s["elpd"][~g].mean()),
        "elpd_se": diff_se(s["elpd"], g, b),
    }
res["l1"]["gaps"] = gaps
print(json.dumps(res, indent=1))
json.dump(res, open(f"{S}/count.json", "w"), indent=1)
