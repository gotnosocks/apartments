import json, numpy as np, pandas as pd
from rentfrontier import frontage as fr

reg = pd.read_parquet(fr.REGISTRY, columns=["building", "bbl", "bin"])
fp = pd.read_parquet(fr.FOOTPRINTS, columns=["bin", "geometry"])
pl = pd.read_parquet(fr.PLUTO, columns=["bbl", "lottype"])
bm = pd.read_parquet(fr.BASEMAP)
st = fr.street_points(bm)
s = bm[bm.layer == "street"].reset_index(drop=True)
lanes = s.attributes.map(
    lambda a: pd.to_numeric(json.loads(a).get("number_travel_lanes"), errors="coerce")
)
speed = s.attributes.map(
    lambda a: pd.to_numeric(json.loads(a).get("posted_speed"), errors="coerce")
)
out = pd.DataFrame({"building": reg.building.drop_duplicates()}).set_index("building")
L = st.assign(width=lanes.reindex(st.road).to_numpy() * 12.0)
t = fr.frontage(reg, fp, L, pl).set_index("building")
out["lanes_faced"] = t.front_width_ft / 12.0
S = st.assign(width=speed.reindex(st.road).to_numpy())
t = fr.frontage(reg, fp, S, pl).set_index("building")
out["speed_faced"] = t.front_width_ft
print("lanes", out.lanes_faced.describe(), flush=True)
g = json.load(open("/data1/apartments/external/truckroutes/raw/truck.geojson"))
rows = []
for k, f in enumerate(g["features"]):
    p = f["properties"]
    geo = f["geometry"]
    if geo is None:
        continue
    lines = (
        geo["coordinates"] if geo["type"] == "MultiLineString" else [geo["coordinates"]]
    )
    for line in lines:
        line = np.asarray(line, float)
        P, U = fr.densify(fr.metres(line[:, 0], line[:, 1]), fr.STREET_STEP_M)
        if len(P):
            rows.append(
                pd.DataFrame(
                    {"x": P[:, 0], "y": P[:, 1], "ux": U[:, 0], "uy": U[:, 1]}
                ).assign(
                    width=30.0,
                    name=p.get("street", ""),
                    road=k,
                    rt=p.get("routetype", ""),
                )
            )
T = pd.concat(rows, ignore_index=True)
for nm, sub in (
    ("truck_any", T),
    ("truck_through", T[T.rt.str.lower().str.startswith("thr")]),
):
    t = fr.frontage(
        reg, fp, sub.drop(columns="rt").reset_index(drop=True), pl
    ).set_index("building")
    out[nm] = t.front_width_ft.notna()
    print(nm, out[nm].mean(), flush=True)
out.reset_index().to_parquet("traffic.parquet")
print("done")
