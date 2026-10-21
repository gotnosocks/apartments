import pandas as pd, json

exec(open("sizecov.py").read().split("res={}")[0])
pf = pd.read_parquet("pipe_fields.parquet", columns=["listing_id", "floor plans"])
f = f.merge(pf, on="listing_id", how="left")
m = f.layer == "none"
fp = f["floor plans"].astype(str)
out = {
    "still missing with a plan": float(fp[m].isin(["1", "2"]).mean()),
    "all with a plan": float(fp.isin(["1", "2"]).mean()),
    "coverage if every plan gives a size": float(
        ((f.layer != "none") | fp.isin(["1", "2"])).mean()
    ),
}
print(out)
json.dump(out, open("sizecov_plans.json", "w"))
