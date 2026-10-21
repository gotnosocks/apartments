import pandas as pd, numpy as np

t = pd.read_parquet("traffic.parquet")
r = pd.read_parquet("resid.parquet", columns=["listing_id", "building"])
t["building"] = t.building.astype(str)
r["building"] = r.building.astype(str)
m = r.merge(t, on="building", how="left")
o = pd.DataFrame({"listing_id": m.listing_id})
o["truck route faced"] = np.where(
    m.truck_through, "through", np.where(m.truck_any, "local", "none")
)
o["travel lanes, widest faced"] = pd.cut(
    m.lanes_faced, [0, 1, 2, 3, 4, 99], labels=["1", "2", "3", "4", "5+"]
).astype(str)
o["posted speed, faced"] = m.speed_faced.round().astype("Int64").astype(str)
o.to_parquet("traffic_fields.parquet")
b = pd.read_parquet("bld_fields.parquet")
b.drop(columns=["cell500", "taxblock"]).to_parquet("bld_fields_noloc.parquet")
