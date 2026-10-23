"""Sensitivity: first-ask slopes with the 3-day typo cutoff at |d| > 0.005 as well as 0.5."""
import importlib.util, json, sys
import numpy as np, pandas as pd
p = "/data1/apartments/research-group/members/fable/models/first_ask_analysis.py"
spec = importlib.util.spec_from_file_location("faa", p); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
rng = np.random.default_rng(m.SEED)
mb, base = m.load_export("base"); mf, fa = m.load_export("firstask")
frame = pd.read_parquet(m.BASE_ROWS, columns=["listing_id","building","unit_id","price_at","latest_day","latest_ask"]).iloc[base["row"]].reset_index(drop=True)
d0 = pd.to_datetime(frame.price_at, utc=True).dt.tz_localize(None).dt.normalize()
d1 = pd.to_datetime(frame.latest_day)
ym = (d0.dt.year*100 + d0.dt.month).to_numpy(); cl = frame.building.astype(str).to_numpy()
d = base["y"] - fa["y"]; days = (d1 - d0).dt.days.to_numpy()
e = fa["y"].astype(np.float32)[None, :] - fa["mu_first"]
z = m.lagged_instrument(pd.DataFrame({"listing_id": frame.listing_id, "building": frame.building, "unit_id": frame.unit_id, "d0": d0.dt.date}))
out = {}
for cut in (0.5, 0.005):
    typo = (np.abs(d) > cut) & (days <= 3); pr = ~typo
    r = {"dropped": int(typo.sum())}
    r["primary"], _ = m.regress(d, e, pr, ym, cl, rng)
    r["changed_only"], _ = m.regress(d, e, pr & (d != 0), ym, cl, rng)
    has = pr & ~np.isnan(z)
    r["iv"], _ = m.regress(d, e, has, ym, cl, rng, z=np.nan_to_num(z))
    out[str(cut)] = r
    print(cut, json.dumps(r), flush=True)
json.dump(out, open(sys.argv[1], "w"), indent=1)
