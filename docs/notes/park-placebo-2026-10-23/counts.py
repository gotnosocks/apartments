"""Row counts for the park frontage line and placebo tests. Reads no rents.

    PYTHONPATH=frontier/src python counts.py LOTS_GEOJSON OUT_DIR

LOTS_GEOJSON holds MapPLUTO 26v2 lots from City Planning's ArcGIS feature service (sha256
310e82af2cd053a409c2dda531931c098e5a8805f2a5416cbb76d4fd1b7ebea9, kept at
/data1/apartments/tmp/conference-followups/park-placebo/lots.geojson).
"""

import glob
import json
import re
import sys

import numpy as np
import pandas as pd
from scipy.sparse.csgraph import connected_components
from scipy.sparse import coo_matrix
from scipy.spatial import cKDTree

from rentfrontier import building_parks, building_park_front as bpf, frontage

LOTS = sys.argv[1]
OUT = sys.argv[2]
FRONT_M, NEAR_M = 40.0, 200.0
ROWS = "/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc/rows.parquet"
PIPE = "/data1/apartments/pipeline/datasets/rows-b3ddebf19af1dc1e.parquet"
PARK = "/data1/apartments/external/building-park-front/20261022-5ddc0e5d/park_front.parquet"

r = pd.read_parquet(
    ROWS,
    columns=[
        "listing_id",
        "audit_id",
        "building",
        "unit_id",
        "latest_day",
        "bedrooms",
        "full_baths",
        "shared_space",
    ],
)
r = r[~r.shared_space.astype(bool)].drop(columns="shared_space")
p = pd.read_parquet(
    PIPE,
    columns=[
        "listing_id",
        "page",
        "view_exposures",
        "window_exposures",
        "listed_floor",
        "advertised_floor",
        "label_derived_floor",
    ],
)
r = r.merge(p, on="listing_id", how="left")
r["building"] = r.building.astype(str)
del p

# unit label from the page URL, and its floor and line
lab = r.page.astype(str).str.rsplit("/", n=1).str[-1].str.lower()
m = lab.str.extract(r"^(?:apt-?|unit-?|#)?(\d{1,2})-?([a-z]{1,2})$")
r["line"] = m[1]
r.loc[m[1].isin(["fl", "th", "st", "nd", "rd"]), "line"] = np.nan
r["label_floor"] = pd.to_numeric(m[0], errors="coerce")
fr = lab.str.extract(r"^(?:\d{1,2})-?(f|r|fr|rr|front|rear)$")[0]
r["front_rear"] = fr.map(
    {
        "f": "front",
        "fr": "front",
        "front": "front",
        "r": "rear",
        "rr": "rear",
        "rear": "rear",
    }
)
r["floor"] = r.listed_floor.fillna(r.label_floor)

ve = r.view_exposures.fillna("").astype(str)
r["se_park_view"] = ve.str.contains('"park":true', regex=False)
r["se_any_view"] = ve.str.contains(":true", regex=False)
we = r.window_exposures.fillna("").astype(str)
r["exp"] = ""
for k in ("north", "east", "south", "west"):
    r["exp"] = r.exp + np.where(we.str.contains(f'"{k}":true', regex=False), k[0], "")
r = r.drop(columns=["view_exposures", "window_exposures", "page"])
del ve, we

# building distances
park = (
    pd.read_parquet(PARK).drop_duplicates("building").set_index("building").park_edge_m
)
r["park_m"] = park.reindex(r.building).to_numpy()

reg = pd.read_parquet(frontage.REGISTRY, columns=["building", "bin"])
reg = reg[reg.building.astype(str).isin(set(r.building))]
fps = pd.read_parquet(frontage.FOOTPRINTS, columns=["bin", "geometry"])

g = json.load(open(LOTS))
lots = []
for f in g["features"]:
    a = f["properties"]
    owner = (a["OwnerName"] or "").upper()
    cls = a["BldgClass"] or ""
    open_land = (a["BldgArea"] or 0) < 0.1 * a["LotArea"]
    if cls.startswith("Z8"):
        kind = "cemetery"
    elif open_land and (
        cls[:2] == "U6"
        or re.search(
            r"LIRR|RAILROAD|RLRD|AMTRAK|RR PASS|TRANSIT AUTH|METROPOLITAN TRANS|LACKAWANNA",
            owner,
        )
    ):
        kind = "rail"
    elif (
        open_land
        and a["LandUse"] == "11"
        and not re.search(r"PARKS|BATTERY PARK", owner)
    ):
        kind = "vacant"
    else:
        continue
    lots.append(
        dict(
            kind=kind,
            bbl=int(a["BBL"]),
            owner=owner,
            acres=a["LotArea"] / 43560,
            geometry=json.dumps(f["geometry"]),
        )
    )
lots = pd.DataFrame(lots)

# merge touching lots of a kind into one tract; a tract of 5 acres or more counts
tract = np.zeros(len(lots), int)
nxt = 0
for kind, sub in lots.groupby("kind"):
    pts, own = [], []
    for i, geom in zip(sub.index, sub.geometry):
        for ring in building_parks.rings(json.loads(geom)):
            q, _ = frontage.densify(frontage.metres(ring[:, 0], ring[:, 1]), 5.0)
            pts.append(q)
            own += [i] * len(q)
    pts = np.vstack(pts)
    own = np.array(own)
    pairs = cKDTree(pts).query_pairs(15.0, output_type="ndarray")
    idx = {v: k for k, v in enumerate(sub.index)}
    a_, b_ = (
        np.vectorize(idx.get)(own[pairs[:, 0]]),
        np.vectorize(idx.get)(own[pairs[:, 1]]),
    )
    n = len(sub)
    adj = coo_matrix((np.ones(len(a_)), (a_, b_)), shape=(n, n))
    _, lab_ = connected_components(adj, directed=False)
    tract[[idx[i] for i in sub.index]] = lab_ + nxt
    nxt += lab_.max() + 1
lots["tract"] = tract
lots["tract_acres"] = lots.groupby("tract").acres.transform("sum")

placebo = {}
tracts = {}
for kind in ("cemetery", "rail", "vacant"):
    if kind == "vacant":
        r["vacant_m"] = np.nan
        continue
    sub = lots[(lots.kind == kind) & (lots.tract_acres >= bpf.FRONT_ACRES)]
    frame = pd.DataFrame(
        {"acres": 1e3, "typecategory": "placebo", "geometry": sub.geometry}
    )
    t = bpf.table(reg, fps, frame).set_index("building").park_edge_m
    placebo[kind] = t
    r[f"{kind}_m"] = t.reindex(r.building).to_numpy()
    tracts[kind] = (
        sub.groupby("tract")
        .agg(acres=("acres", "sum"), lots=("bbl", "size"), owner=("owner", "first"))
        .to_dict("records")
    )

# expressway centrelines from the basemap
bm = pd.read_parquet(
    "/data1/apartments/external/basemap/20261016-5f07157-all/basemap.parquet"
)
bm = bm[bm.layer == "street"]
hw = bm[bm.attributes.map(lambda s: json.loads(s).get("rw_type")) == "2"]
frame = pd.DataFrame(
    {
        "acres": 1e3,
        "typecategory": "placebo",
        "geometry": [
            json.dumps(
                {"type": "Polygon", "coordinates": json.loads(gm)["coordinates"]}
            )
            for gm in hw.geometry
        ],
    }
)
t = bpf.table(reg, fps, frame).set_index("building").park_edge_m
r["highway_m"] = t.reindex(r.building).to_numpy()

for k in ("park", "cemetery", "rail", "vacant", "highway"):
    d = r[f"{k}_m"]
    r[f"{k}_front"] = d < FRONT_M
    r[f"{k}_near"] = (d >= FRONT_M) & (d < NEAR_M)

# ad text
groups = (
    r.park_front
    | r.park_near
    | r.cemetery_front
    | r.rail_front
    | r.highway_front
    | r.cemetery_near
    | r.rail_near
)
want = set(r.listing_id[groups].astype(str))
sid = re.compile(r'"source_listing_id": "([^"]+)"')
park_re = re.compile(
    r"park[- ]views?|views? (?:of|over|onto|into|across) (?:the )?(?:[a-z]+ ){0,2}park|"
    r"(?:overlook|fac|front)(?:s|es|ing)? (?:onto |on |over )?(?:the )?(?:[a-z]+ ){0,2}park|park[- ]facing|"
    r"(?:across|directly on|right on|steps to|steps from) (?:the )?(?:central|prospect|riverside|tompkins|mccarren|fort greene|washington|madison|stuyvesant|morningside|marcus garvey|maria hernandez|cooper|irving) (?:square )?park",
    re.I,
)
view_re = re.compile(
    r"park[- ]views?|views? (?:of|over|onto|into|across) (?:the )?(?:[a-z]+ ){0,2}park|overlook(?:s|ing)? (?:the )?(?:[a-z]+ ){0,2}park|park[- ]facing|fac(?:es|ing) (?:the )?(?:[a-z]+ ){0,2}park",
    re.I,
)
cem_re = re.compile(r"cemetery|graveyard", re.I)
rail_re = re.compile(r"rail ?yard|train yard|railroad|tracks", re.I)
txt = {}
for path in sorted(
    glob.glob("/data1/apartments/frontier/descriptions/*/evidence.jsonl")
):
    with open(path) as fh:
        for line in fh:
            mm = sid.search(line)
            if not mm or mm.group(1) not in want:
                continue
            s = json.loads(line).get("description") or ""
            if len(s) <= 20:
                continue
            new = (
                bool(view_re.search(s)),
                bool(park_re.search(s)),
                bool(cem_re.search(s)),
                bool(rail_re.search(s)),
            )
            old = txt.get(mm.group(1), (False,) * 4)
            txt[mm.group(1)] = tuple(a or b for a, b in zip(old, new))
tx = r.listing_id.astype(str).map(txt)
r["has_text"] = tx.notna()
r["text_park_view"] = tx.map(lambda v: v[0] if isinstance(v, tuple) else False)
r["text_park_any"] = tx.map(lambda v: v[1] if isinstance(v, tuple) else False)
r["text_cemetery"] = tx.map(lambda v: v[2] if isinstance(v, tuple) else False)
r["text_rail"] = tx.map(lambda v: v[3] if isinstance(v, tuple) else False)
r["park_view"] = r.se_park_view | r.text_park_view


def summary(s):
    b = s.groupby("building")
    lines = s.dropna(subset=["line"])
    nl = lines.groupby("building").line.nunique()
    pv = s.groupby("building").park_view.agg(["min", "max"])
    contrast = pv.index[(pv["min"] == 0) & (pv["max"] == 1)]
    bl = lines.groupby(["building", "line"]).park_view.mean().reset_index()
    blc = bl.groupby("building").park_view.agg(["min", "max"])
    line_contrast = blc.index[(blc["min"] < 0.5) & (blc["max"] >= 0.5)]
    return {
        "ads": int(len(s)),
        "buildings": int(b.ngroups),
        "units": int(s.unit_id.nunique()),
        "ads_with_line": int(s.line.notna().sum()),
        "buildings_2plus_lines": int((nl >= 2).sum()),
        "ads_front_rear_label": int(s.front_rear.notna().sum()),
        "ads_floor_known": int(s.floor.notna().sum()),
        "ads_text": int(s.has_text.sum()),
        "ads_se_park_view": int(s.se_park_view.sum()),
        "ads_text_park_view": int(s.text_park_view.sum()),
        "ads_text_park_any": int(s.text_park_any.sum()),
        "ads_park_view_either": int(s.park_view.sum()),
        "ads_se_any_view": int(s.se_any_view.sum()),
        "ads_window_exposure": int((s.exp != "").sum()),
        "ads_text_cemetery": int(s.text_cemetery.sum()),
        "ads_text_rail": int(s.text_rail.sum()),
        "buildings_park_view_contrast": int(len(contrast)),
        "ads_in_contrast_buildings": int(s.building.isin(contrast).sum()),
        "buildings_line_contrast": int(len(line_contrast)),
        "ads_in_line_contrast_buildings": int(s.building.isin(line_contrast).sum()),
    }


out = {
    "rows": int(len(r)),
    "ads_with_line": int(r.line.notna().sum()),
    "ads_text_any": None,
}
for k in ("park", "cemetery", "rail", "vacant", "highway"):
    other = ~r.park_front if k != "park" else True
    out[f"{k}_front"] = summary(r[r[f"{k}_front"] & other])
    out[f"{k}_near"] = summary(r[r[f"{k}_near"] & ~r.park_front & other])
out["tracts"] = tracts
for k in ("cemetery", "rail"):
    out[f"{k}_front_buildings"] = (
        r[r[f"{k}_front"] & ~r.park_front].building.value_counts().to_dict()
    )
# park view by floor in park-front buildings
pf = r[r.park_front & r.floor.notna()]
bins = pd.cut(
    pf.floor, [-1, 2, 5, 10, 20, 200], labels=["0-2", "3-5", "6-10", "11-20", "21+"]
)
out["park_front_by_floor"] = (
    pf.groupby(bins, observed=True)
    .agg(ads=("park_view", "size"), park_view=("park_view", "sum"))
    .to_dict("index")
)
out["park_front_floor_quartiles"] = pf.floor.quantile([0.25, 0.5, 0.75, 0.9]).to_dict()
# per-building view-share among park-front buildings
pv = r[r.park_front].groupby("building").park_view.mean()
out["park_front_view_share_quantiles"] = pv.quantile(
    [0.1, 0.25, 0.5, 0.75, 0.9]
).to_dict()
out["park_front_buildings_no_view_ad"] = int((pv == 0).sum())
r[
    [
        "listing_id",
        "audit_id",
        "building",
        "unit_id",
        "line",
        "front_rear",
        "floor",
        "se_park_view",
        "text_park_view",
        "park_view",
        "exp",
        "has_text",
    ]
    + [f"{k}_m" for k in ("park", "cemetery", "rail", "vacant", "highway")]
].to_parquet(OUT + "/groups.parquet")
json.dump(out, open(OUT + "/counts.json", "w"), indent=1, default=str)
print(json.dumps(out, indent=1, default=str))
