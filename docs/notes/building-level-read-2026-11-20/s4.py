import json, pandas as pd, numpy as np, pyarrow.parquet as pq

pd.set_option("display.width", 250, "display.max_rows", 500)
REG = "/data1/apartments/external/registry/20261120-6cd1f12-extend/registry.parquet"
print(pq.read_schema(REG).names)
DS = "/data1/apartments/frontier/datasets/b0-4f487ef77bb6ca61-alldata-dense-nyc-market-bedtext/rows.parquet"
f = pd.read_parquet(
    DS, columns=["neighbourhood", "bedrooms", "latest_ask", "latest_day"]
)
f["year"] = pd.to_datetime(f.latest_day).dt.year
med = (
    f.groupby(["neighbourhood", "year", "bedrooms"])
    .latest_ask.agg(["median", "size", lambda s: s.quantile(0.99)])
    .reset_index()
)
med.columns = ["neighbourhood", "year", "bedrooms", "nb_median", "nb_n", "nb_p99"]
med.to_parquet("nb_medians.parquet")
rows = pd.read_parquet("sel_rows.parquet")
rows["year"] = pd.to_datetime(rows.latest_day).dt.year
rows = rows.merge(med, on=["neighbourhood", "year", "bedrooms"], how="left")
rows["ratio"] = rows.latest_ask / rows.nb_median
A = pd.read_parquet("sel_ads.parquet").drop_duplicates("listing_id")
A["listing_id"] = A.listing_id.astype(str)
rows["listing_id"] = rows.listing_id.astype(str)
rows = rows.merge(
    A[
        [
            "listing_id",
            "page",
            "square_feet",
            "advertised_floor",
            "lease_term",
            "months_free",
            "building_check",
            "ask_check",
            "ledger_entries",
        ]
    ],
    on="listing_id",
    how="left",
)
R = pd.read_parquet("sel_records.parquet")
R["listing_id"] = R.listing_id.astype(str)


def info(s):
    j = json.loads(s)
    pdt = j.get("propertyDetails") or {}
    ad = pdt.get("address") or {}
    return pd.Series(
        {
            "desc": j.get("description") or "",
            "unit": ad.get("unit"),
            "street": ad.get("street"),
            "src": (j.get("legacy") or {}).get("sourceGroupLabel"),
            "furn_rent": (j.get("pricing") or {}).get("furnishedRent"),
            "lease_m": (j.get("pricing") or {}).get("leaseTermMonths"),
            "ptype": pdt.get("propertyType") if "propertyType" in pdt else None,
            "pd_keys": ",".join(pdt.keys()),
        }
    )


I = R.raw_listing_json.apply(info)
I["listing_id"] = R.listing_id.values
print(I.pd_keys.iloc[0])
rows = rows.merge(I.drop(columns="pd_keys"), on="listing_id", how="left")
rows.to_parquet("packet.parquet")
print(
    rows[rows.grp == "rhat"].desc.notna().mean(),
    rows[rows.grp == "rhat"].desc.fillna("").str.len().describe(),
)
