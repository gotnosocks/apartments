"""Backtest range-j: per held-out ad, building level, support, scores and outcomes."""

import json, hashlib
from pathlib import Path
import numpy as np, pandas as pd
from rentfrontier import run as R, drift_score, drift_diagnostics, drift_deals

OUT = Path("/data1/apartments/tmp/po-thinlevel")
SEED = "thin-level-2026-11-20"


def half(b):
    return hashlib.sha1((SEED + b).encode()).digest()[0] & 1


d = [
    p
    for p in R.RUNS.iterdir()
    if "d9028c57-range-j" in p.name and (p / "posterior.npz").exists()
][0]
ds = drift_score.dataset_dir(d)
rec = json.loads((d / "result.json").read_text())
man = json.loads((ds / "manifest.json").read_text())
ads = Path(man["build"]["ads"]["path"])
print(
    d.name, ds, ads, {k: man[k] for k in man if k in ("backtest", "market_day", "day")}
)
frame, h, held = drift_deals._held_frame(d)
print(len(frame), held.sum(), frame.columns.tolist())
lv, why = drift_diagnostics.levels(d, rec, frame.building.astype(str).to_numpy())
assert lv is not None, why
b = frame.building.astype(str)
uk = b + "|" + frame.unit_id.astype(str)
tr = ~held
nb = b[tr].value_counts()
nu = uk[tr & frame.unit_id.notna().to_numpy()].value_counts()
nunits = pd.DataFrame({"b": b[tr], "u": uk[tr]}).groupby("b").u.nunique()
a = drift_deals._ads(ads, h.listing_id)
codes, _ = drift_deals._run_cautions(d, frame, h, held, a, ads, None)
final = h.latest_ask.to_numpy(float)
free = np.nan_to_num(a.months_free.to_numpy(float)) > 0
gross = a.first_ask.to_numpy(float)
first = drift_deals.first_net(gross, final, a.page_price, free)
ok = np.isfinite(first) & (first > 0)
res = drift_score.score_run(d, at=np.log(np.where(ok, first, final)))
day = pd.to_datetime(h.final_day if "final_day" in h else h.latest_day)
off = pd.to_datetime(a.off_day).to_numpy()
end = np.where(np.isnat(off), day.to_numpy(), off)
days = (end - pd.to_datetime(a.first_day).to_numpy()) / np.timedelta64(1, "D")
ok &= np.isfinite(days) & (days >= 0)
hb = h.building.astype(str).to_numpy()
hu = uk[held].to_numpy()
o = pd.DataFrame(
    dict(
        listing_id=h.listing_id.astype(str).to_numpy(),
        building=hb,
        unit_id=h.unit_id.astype(str).to_numpy(),
        neighbourhood=h.neighbourhood.astype(str).to_numpy(),
        bedrooms=h.bedrooms.to_numpy(float),
        ask=final,
        first=first,
        ok=ok,
        free=free,
        pred=res["pred"],
        y=res["y"],
        cdf=res["cdf"],
        place=res["cdf_at"],
        unit_sd=res["unit_sd"],
        q05=res["q"][:, 1] if abs(res["quantiles"][1] - 0.05) < 1e-9 else np.nan,
        days=days,
        change=final / np.where(ok, first, 1.0) - 1,
        off=~np.isnat(off),
        caut=[",".join(c) for c in codes],
    )
)
print("quantiles", res["quantiles"])
o["level"] = lv.level.reindex(hb).to_numpy()
o["level_sd"] = lv.level_sd.reindex(hb).to_numpy()
o["zone"] = lv.zone.reindex(hb).to_numpy()
o["n_bld"] = nb.reindex(hb).fillna(0).astype(int).to_numpy()
o["n_unit"] = nu.reindex(hu).fillna(0).astype(int).to_numpy()
o["n_other"] = o.n_bld - o.n_unit
o["n_units_bld"] = nunits.reindex(hb).fillna(0).astype(int).to_numpy()
o["gap"] = o.y - o.pred
o["gap_first"] = np.where(ok, np.log(np.where(ok, first, 1)) - o.pred, np.nan)
o["half"] = [half(x) for x in hb]
o.to_parquet(OUT / "back_ads.parquet")
lv["n_train"] = nb.reindex(lv.index).fillna(0).astype(int)
lv.reset_index().to_parquet(OUT / "back_levels.parquet")
print(o.describe().T.round(3).to_string())
print(o.level.isna().sum(), (o.caut != "").mean())
