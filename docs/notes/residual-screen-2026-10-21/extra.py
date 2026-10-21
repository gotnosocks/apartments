import pandas as pd, numpy as np

r = pd.read_parquet("resid.parquet", columns=["listing_id"])
d = pd.read_parquet(
    "/data1/apartments/frontier/datasets/b0-edc83b49f9bacd8c-alldata-v36-dense-nyc/rows.parquet",
    columns=["listing_id", "bedrooms"],
)
p = pd.read_parquet(
    "/data1/apartments/pipeline/datasets/rows-edc83b49f9bacd8c.parquet",
    columns=["listing_id", "square_feet", "listed_floor", "elevator"],
).drop_duplicates("listing_id")
f = r.merge(d, on="listing_id", how="left").merge(p, on="listing_id", how="left")
s = f.square_feet.where((f.square_feet > 100) & (f.square_feet < 10000))
dev = np.log(s) - np.log(s).groupby(f.bedrooms.clip(upper=4)).transform("median")
o = pd.DataFrame({"listing_id": f.listing_id})
o["size vs bedroom median"] = (
    pd.cut(
        dev,
        [-9, -0.4, -0.2, -0.1, 0, 0.1, 0.2, 0.4, 9],
        labels=[
            "< -33%",
            "-33 to -18%",
            "-18 to -10%",
            "-10 to 0%",
            "0 to +11%",
            "+11 to +22%",
            "+22 to +49%",
            "> +49%",
        ],
    )
    .astype(str)
    .replace("nan", "unknown")
)
el = (
    f.elevator.map({True: "elevator", False: "walk-up"}).fillna("elev unknown")
    if f.elevator.dtype == bool
    else f.elevator.astype(str)
)
fb = (
    pd.cut(
        f.listed_floor,
        [0, 1, 2, 3, 4, 6, 200],
        labels=["1", "2", "3", "4", "5-6", "7+"],
    )
    .astype(str)
    .replace("nan", "unknown")
)
o["floor x elevator"] = el.astype(str) + " / floor " + fb
o.to_parquet("extra_fields.parquet")
print(o["floor x elevator"].value_counts().head(20))
print(o["size vs bedroom median"].value_counts())
