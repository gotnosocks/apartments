import pandas as pd, numpy as np

r = pd.read_parquet("resid.parquet", columns=["listing_id", "building"])
reg = (
    pd.read_parquet(
        "/data1/apartments/external/registry/20261019-bcfbb52-extend/registry.parquet",
        columns=["building", "bbl", "latitude", "longitude"],
    )
    .drop_duplicates("building")
    .set_index("building")
)
pl = pd.read_parquet(
    "/data1/apartments/external/pluto/20261017-2c61ff1-all-lots4/pluto.parquet"
)
pl["bbl"] = pl.bbl.astype(str).str.replace(r"\.0$", "", regex=True)
for k in ["yearbuilt", "yearalter1", "yearalter2", "unitsres", "builtfar"]:
    pl[k] = pd.to_numeric(pl[k], errors="coerce")
pl = pl.sort_values("version").drop_duplicates("bbl", keep="last").set_index("bbl")
fr = pd.read_parquet(
    "/data1/apartments/external/frontage/20261020-fbf9a82/frontage.parquet"
).set_index("building")
b = pd.DataFrame(index=pd.Index(r.building.unique(), name="building"))
bbl = reg.bbl.reindex(b.index).astype("string").str.replace(r"\.0$", "", regex=True)
p = pl.reindex(bbl.fillna("x").to_numpy())
p.index = b.index
yb = p.yearbuilt.where(p.yearbuilt > 1700)
b["era (PLUTO year built)"] = (
    pd.cut(
        yb,
        [1700, 1899, 1919, 1939, 1959, 1979, 1999, 2009, 2030],
        labels=[
            "<1900",
            "1900-19",
            "1920-39",
            "1940-59",
            "1960-79",
            "1980-99",
            "2000-09",
            "2010+",
        ],
    )
    .astype(str)
    .replace("nan", "unknown")
)
alt = np.fmax(p.yearalter1.fillna(0), p.yearalter2.fillna(0))
b["altered (PLUTO yearalter)"] = np.select(
    [alt >= 2010, alt >= 1990, alt > 0], ["2010+", "1990-2009", "before 1990"], "never"
).astype(str)
b["building class"] = (
    p.bldgclass.astype(str).str[0].replace({"None": "unknown", "nan": "unknown"})
)
b["historic district"] = p.histdist.notna().astype(str)
b["landmark (LPC)"] = p.landmark.notna().astype(str)
b["residential units"] = pd.cut(
    p.unitsres, [-1, 2, 5, 10, 20, 50, 100, 300, 1e5]
).astype(str)
b["built FAR"] = pd.cut(p.builtfar, [-1, 1, 2, 3, 4, 6, 9, 1e3]).astype(str)
w = fr.front_width_ft.reindex(b.index)
c = fr.corner.reindex(b.index)
band = (
    pd.cut(
        w, [0, 40, 60, 80, 1e3], labels=["<=40 ft", "41-60 ft", "61-80 ft", ">80 ft"]
    )
    .astype(str)
    .replace("nan", "width unknown")
)
b["frontage width x corner"] = band + np.where(
    c == 1, " corner", np.where(c == 0, " mid-block", " corner?")
)
st = fr.front_street.reindex(b.index).astype(str)
top = st[w > 40].value_counts()
top = top[top >= 60].index
b["avenue (mid-block vs corner)"] = np.where(
    st.isin(top) & (w > 40),
    st + np.where(c == 1, " corner", " mid-block"),
    "not a listed avenue",
)
lat = reg.latitude.reindex(b.index).to_numpy()
lon = reg.longitude.reindex(b.index).to_numpy()
x = (lon + 73.98) * 84.3 * 1000
y = (lat - 40.75) * 111.0 * 1000
b["cell500"] = (
    pd.Series(np.floor(x / 500), index=b.index).astype("Int64").astype(str)
    + "_"
    + pd.Series(np.floor(y / 500), index=b.index).astype("Int64").astype(str)
)
b["taxblock"] = bbl.str[:6].fillna("none")
o = (
    r[["listing_id"]].join(b, on=r.building)
    if False
    else r.merge(b.reset_index(), on="building").drop(columns="building")
)
o.to_parquet("bld_fields.parquet")
print(o.shape)
for c in b.columns[:9]:
    print(c, b[c].value_counts().head(6).to_dict())
