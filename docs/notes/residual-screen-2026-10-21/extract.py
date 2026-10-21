import pyarrow.parquet as pq, pandas as pd, numpy as np, sys

try:
    import orjson as js
except ImportError:
    import json as js
ids = set(
    pd.read_parquet("resid.parquet", columns=["listing_id"]).listing_id.astype(str)
)
pf = pq.ParquetFile(
    "/data1/apartments/pipeline/datasets/records-086e22e48969b098.parquet"
)
out = {}


def g(d, *k):
    for x in k:
        if not isinstance(d, dict):
            return None
        d = d.get(x)
    return d


for i in range(pf.num_row_groups):
    t = pf.read_row_group(
        i, columns=["listing_id", "collected_at", "raw_listing_json"]
    ).to_pandas()
    t["listing_id"] = t.listing_id.astype(str)
    t = t[t.listing_id.isin(ids)]
    for lid, ca, s in zip(t.listing_id, t.collected_at, t.raw_listing_json):
        if lid in out and out[lid]["_at"] >= ca:
            continue
        try:
            j = js.loads(s)
        except Exception:
            continue
        pdx = g(j, "propertyDetails") or {}
        am = g(pdx, "amenities") or {}
        fe = g(pdx, "features") or {}
        md = g(j, "media") or {}
        pr = g(j, "pricing") or {}
        rec = {
            "_at": ca,
            "source_type": g(j, "listingSource", "sourceType"),
            "license_type": g(j, "legacy", "license", "licenseType"),
            "business": g(j, "legacy", "license", "businessName"),
            "source_group": g(j, "legacy", "sourceGroupLabel"),
            "premium": g(j, "isPremiumHdpEnabled"),
            "mls": g(j, "mlsNumber") is not None,
            "display_unit": g(pdx, "address", "displayUnit"),
            "rooms": g(pdx, "roomCount"),
            "sqft_known": g(pdx, "livingAreaSize") not in (None, 0),
            "photos": len(g(md, "photos") or []) if md else -1,
            "plans": len(g(md, "floorPlans") or []) if md else -1,
            "video": bool(g(md, "videos")) if md else None,
            "tour3d": g(md, "tour3dUrl") is not None if md else None,
            "desc_len": len(g(j, "description") or ""),
            "n_fees": len(pr.get("additionalFees") or [])
            + len(pr.get("moveInFees") or [])
            + len(pr.get("monthlyFees") or []),
            "nofee_text": "no fee" in (g(j, "description") or "").lower(),
            "amen": "|".join(sorted(am.get("list") or [])),
            "feat": "|".join(sorted(fe.get("list") or [])),
            "outdoor_private": "|".join(
                sorted(fe.get("privateOutdoorSpaceTypes") or [])
            ),
            "outdoor_shared": "|".join(sorted(am.get("sharedOutdoorSpaceTypes") or [])),
            "parking": "|".join(sorted(am.get("parkingTypes") or [])),
            "fireplace": "|".join(sorted(fe.get("fireplaceTypes") or [])),
            "views": "|".join(sorted(fe.get("views") or [])),
            "storage": "|".join(sorted(am.get("storageSpaceTypes") or [])),
        }
        out[lid] = rec
    print(i, pf.num_row_groups, len(out), flush=True)
df = pd.DataFrame.from_dict(out, orient="index").drop(columns="_at")
df.index.name = "listing_id"
df.reset_index().to_parquet("raw_fields.parquet")
print("done", len(df))
