"""Photo disagreement, part 4: the grades against the fields L1 already reads.

The script takes the first reads of `reads.parquet` with a grade and joins each ad's building
fields (year built and last alteration, residential units, doorman) and L1's own median for
the ad (`pred1`, on the log of the net ask). It prints:

- each group's median ask, year built, units and its shares of post-2000, large and doorman
  buildings;
- the correlation of each grade with those fields and with `pred1` over the 3 groups;
- a least-squares fit of each grade on the group (R as the base), first alone and then with
  the fields added, with building-clustered SEs, to show how much of A's higher grade the
  fields take up;
- inside R, the random group, the slope of the gap and of the market score D on each grade.

It writes `pattern.json`."""

import json

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

OUT = "/data1/apartments/tmp/photo-disagreement-2026-11-14/"
PIPE = "/data1/apartments/pipeline/datasets/rows-b3ddebf19af1dc1e.parquet"
AGE = "/data1/apartments/external/building-age/20261021-3a64aa22/age.parquet"
REG = "/data1/apartments/external/registry/20261019-bcfbb52-extend/registry.parquet"
PLUTO = "/data1/apartments/external/pluto/20261017-2c61ff1-all-lots4/pluto.parquet"
SCREEN = "/data1/apartments/tmp/market-disagreement-2026-11-14/"
GRADES = ["condition", "light"]

d = pd.read_parquet(OUT + "reads.parquet")
d = d[~d.repeat & d.seen].reset_index(drop=True)
draw = pd.read_parquet(SCREEN + "draw.parquet")
draw["listing_id"] = draw.listing_id.astype(str)
d = d.merge(draw[["listing_id", "pred1", "y1", "bedrooms", "boro"]], on="listing_id")

f = pq.ParquetFile(PIPE)
want = pa.array(d.listing_id.tolist(), type=f.schema_arrow.field("listing_id").type)
parts = []
for g in range(f.num_row_groups):
    t = f.read_row_group(g, columns=["listing_id", "doorman_type"])
    parts.append(t.filter(pc.is_in(t["listing_id"], value_set=want)).to_pandas())
pipe = pd.concat(parts)
pipe["listing_id"] = pipe.listing_id.astype(str)
d = d.merge(pipe.drop_duplicates("listing_id"), on="listing_id", how="left")

age = pd.read_parquet(AGE, columns=["building", "year_built", "alter1", "alter2"])
reg = pd.read_parquet(REG, columns=["building", "bbl"]).drop_duplicates("building")
pl = pd.read_parquet(PLUTO, columns=["bbl", "version", "unitsres"])
pl = pl.sort_values("version").drop_duplicates("bbl", keep="last")
bld = reg.merge(pl, on="bbl", how="left").merge(age, on="building", how="outer")
d = d.merge(bld.drop_duplicates("building"), on="building", how="left")

year = pd.to_numeric(d.year_built, errors="coerce").where(lambda s: s > 1700)
d["year"] = year
d["post2000"] = (year >= 2000).astype(float)
d["prewar"] = (year < 1940).astype(float)
d["year_missing"] = year.isna().astype(float)
d["units"] = pd.to_numeric(d.unitsres, errors="coerce")
d["large"] = (d.units >= 100).astype(float)
d["log_units"] = np.log(d.units.clip(lower=1)).fillna(0.0)
d["units_missing"] = d.units.isna().astype(float)
doorman = d.doorman_type.astype(str).str.lower()
d["doorman"] = doorman.isin(["full_time", "part_time"]).astype(float)
d["manhattan"] = (d.boro.astype(str) == "1").astype(float)
print("doorman codes:", d.doorman_type.astype(str).value_counts().to_dict())

out = {"groups": {}, "correlations": {}, "fits": {}, "random": {}}
for g, part in d.groupby("group"):
    out["groups"][g] = {
        "ads": len(part),
        "median_ask": round(float(np.exp(part.y1).median())),
        "median_l1": round(float(np.exp(part.pred1).median())),
        "median_year": float(part.year.median()),
        "post2000": round(100 * float(part.post2000.mean()), 1),
        "prewar": round(100 * float(part.prewar.mean()), 1),
        "median_units": float(part.units.median()),
        "large": round(100 * float(part.large.mean()), 1),
        "doorman": round(100 * float(part.doorman.mean()), 1),
    }
    print(g, out["groups"][g])

FIELDS = ["pred1", "post2000", "prewar", "large", "doorman", "manhattan", "bedrooms"]
for g in GRADES:
    keep = d[g].notna()
    out["correlations"][g] = {
        c: round(float(np.corrcoef(d.loc[keep, g], d.loc[keep, c])[0, 1]), 2)
        for c in FIELDS
    }
    print(g, "correlations:", out["correlations"][g])


def fit(frame, target, columns):
    """Least squares of `target` on `columns` and a constant, with building-clustered SEs
    and the share of variance taken up."""
    x = np.column_stack([np.ones(len(frame)), frame[columns].to_numpy(float)])
    y = frame[target].to_numpy(float)
    bread = np.linalg.pinv(x.T @ x)
    beta = bread @ x.T @ y
    resid = y - x @ beta
    scores = pd.DataFrame(x * resid[:, None]).groupby(frame.building.to_numpy()).sum()
    meat = scores.to_numpy().T @ scores.to_numpy()
    se = np.sqrt(np.diag(bread @ meat @ bread))
    r2 = 1 - resid.var() / y.var()
    names = ["const", *columns]
    return {n: [round(b, 3), round(s, 3)] for n, b, s in zip(names, beta, se)}, r2


d["A"] = (d.group == "A").astype(float)
d["B"] = (d.group == "B").astype(float)
CONTROLS = [
    "pred1",
    "bedrooms",
    "manhattan",
    "post2000",
    "prewar",
    "year_missing",
    "log_units",
    "units_missing",
    "doorman",
]
for g in GRADES:
    part = d[d[g].notna()].reset_index(drop=True)
    alone, r2_alone = fit(part, g, ["A", "B"])
    fields, r2_fields = fit(part, g, CONTROLS)
    both, r2_both = fit(part, g, ["A", "B", *CONTROLS])
    out["fits"][g] = {
        "n": len(part),
        "group_alone": alone,
        "r2_group_alone": round(r2_alone, 3),
        "r2_fields_alone": round(r2_fields, 3),
        "with_fields": both,
        "r2_with_fields": round(r2_both, 3),
    }
    print(g, json.dumps(out["fits"][g]))

rand = d[d.group == "R"].reset_index(drop=True)
for g in GRADES:
    part = rand[rand[g].notna()].reset_index(drop=True)
    row = {"n": len(part)}
    for target in ("gap1", "D"):
        row[target] = fit(part, target, [g])[0][g]
    out["random"][g] = row
    print("R:", g, row)
for g in GRADES:
    part = d[d[g].notna()].reset_index(drop=True)
    row = {"n": len(part)}
    for target in ("gap1", "D"):
        row[target] = fit(part, target, [g, "A", "B"])[0][g]
    out["random"][g + "_within_groups"] = row
    print("within groups:", g, row)

with open(OUT + "pattern.json", "w") as sink:
    json.dump(out, sink, indent=1)
