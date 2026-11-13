"""S2: did the FARE Act (in force 2025-06-11) move asks of ads that used to charge the
renter a broker fee?

The GraphQL digests' `noFee` field is false on all 131,912 ads that carry it, so the script reads the
fee from each listing's last description instead:

1. `no_fee`, the text flag of `rentfrontier.features.DESCRIPTION_FLAGS`
   (`/data1/apartments/tmp/outlier-sprint/qual/flags.parquet`);
2. `fee_stated`, wording that puts a broker fee on the renter, matched here over the
   descriptions in `/data1/apartments/tmp/outlier-sprint/s2/R/recs.parquet`.

An ad with neither counts as silent. The script tabulates the shares by the month the ad opened, the
within-building gap of fee against no-fee ads by half-year, and a switch test on consecutive
ads of a unit: the held-out ad's gap by the fee status of the unit's previous ad and of its
own, for held-out ads opened before and after the Act."""

import json

import numpy as np
import pandas as pd
import pyarrow.compute as pc
import pyarrow.parquet as pq

import common as c

FEE = (
    r"(?i)(?:broker(?:'s|s)? fee|brokers? commission|fee (?:applies|is required|of \d)"
    r"|(?:\d{1,2}(?:\.\d+)?\s?%|one month'?s?|1 month'?s?|\d{1,2}(?:\.\d+)? months?'?) "
    r"(?:broker(?:'s)? )?(?:fee|commission)|tenant pays (?:the )?(?:broker(?:'s)? )?fee"
    r"|\bfee:\s*\d|\bfee\s*=\s*\d)"
)
NOFEE_SPLIT = r"(?i)\bno (?:broker )?fee"
ACT = pd.Timestamp("2025-06-11")

f = pq.ParquetFile(c.RECS)
parts = []
for g in range(f.num_row_groups):
    t = f.read_row_group(g, columns=["listing_id", "last_collected_at", "description"])
    desc = pc.fill_null(t["description"], "")
    parts.append(
        pd.DataFrame(
            {
                "listing_id": t["listing_id"].to_numpy(zero_copy_only=False),
                "t": t["last_collected_at"].to_numpy(zero_copy_only=False),
                "fee_stated": pc.match_substring_regex(desc, FEE).to_numpy(
                    zero_copy_only=False
                ),
                "nofee_any": pc.match_substring_regex(desc, NOFEE_SPLIT).to_numpy(
                    zero_copy_only=False
                ),
            }
        )
    )
fee = pd.concat(parts).sort_values("t").drop_duplicates("listing_id", keep="last")
fl = pd.read_parquet(
    "/data1/apartments/tmp/outlier-sprint/qual/flags.parquet",
    columns=["listing_id", "no_fee"],
)
fee = fee.merge(fl, on="listing_id", how="left")
print(
    "fee table",
    len(fee),
    fee[["fee_stated", "nofee_any", "no_fee"]].mean().round(4).to_dict(),
    flush=True,
)

d = c.rows()
p = pd.read_parquet(
    "/data1/apartments/tmp/outlier-sprint/s2/H/proc.parquet",
    columns=["listing_id", "t_on"],
)
p["t_on"] = p.t_on.dt.tz_convert(None)
d = d.merge(p.drop_duplicates("listing_id"), on="listing_id", how="left")
d = d.merge(fee[["listing_id", "fee_stated", "no_fee"]], on="listing_id", how="left")
d["opened"] = d.t_on.where(d.t_on.notna() & (d.t_on <= d.priced), d.priced)
d["status"] = np.where(
    d.no_fee.isna(),
    "unread",
    np.where(
        d.no_fee.fillna(False),
        "nofee",
        np.where(d.fee_stated.fillna(False), "fee", "silent"),
    ),
)
d["month"] = d.opened.dt.to_period("M").astype(str)
m = (d.opened >= "2023-01-01") & (d.opened < "2026-12-01")
share = pd.crosstab(d.month[m], d.status[m], normalize="index").round(4)
share["n"] = d.month[m].value_counts().sort_index()
share.to_csv(c.OUT + "s2_share_by_month.csv")
print(share.to_string(), flush=True)

d = d.sort_values(["ukey", "priced", "listing_id"])
same = d.ukey.eq(d.ukey.shift())
d["prev_status"] = np.where(same, d.status.shift(), "first")
d["prev_opened"] = d.opened.shift().where(same)
d = d.sort_index()
h = c.heldout(d)
res = {
    "n_heldout": len(h),
    "share_heldout": h.status.value_counts(normalize=True).round(4).to_dict(),
}

# fee against no-fee within building, by half-year of opening
h["half"] = (
    h.opened.dt.year.astype(str) + "H" + np.where(h.opened.dt.month <= 6, "1", "2")
)
h["wgap"] = c.within(h.gap, h.building.astype(str) + "@" + h.half)
rows = []
for half, g in h[h.status.isin(["fee", "nofee"])].groupby("half"):
    if half < "2019H1":
        continue
    nb = g.groupby("building").status.nunique()
    both = g[g.building.isin(nb[nb == 2].index)]
    if (both.status == "fee").sum() < 30:
        continue
    dm, se = c.cluster_mean_diff(
        both.wgap.to_numpy(),
        (both.status == "nofee").to_numpy(),
        both.building.to_numpy(),
    )
    rows.append(
        {
            "half": half,
            "n_fee": int((both.status == "fee").sum()),
            "n_nofee": int((both.status == "nofee").sum()),
            "nofee_minus_fee": dm,
            "se": se,
        }
    )
t = pd.DataFrame(rows)
t.to_csv(c.OUT + "s2_within_building.csv", index=False)
print(t.to_string(), flush=True)
res["within_building"] = rows

# switch test: held-out ads whose unit's previous ad stated a fee or no fee
sw = h[
    h.prev_status.isin(["fee", "nofee"]) & h.status.isin(["fee", "nofee", "silent"])
].copy()
sw["after"] = sw.opened >= ACT
sw["prev_before"] = sw.prev_opened < ACT
rows = []
for after in (False, True):
    for prev in ("fee", "nofee"):
        for cur in ("fee", "nofee", "silent"):
            g = sw[(sw.after == after) & (sw.prev_status == prev) & (sw.status == cur)]
            if len(g) < 30:
                continue
            rows.append(
                {
                    "after_act": after,
                    "prev": prev,
                    "cur": cur,
                    "n": len(g),
                    "gap": float(g.gap.mean()),
                    "se": c.cluster_se(g.gap.to_numpy(), g.building.to_numpy())
                    / len(g),
                    "cov80": float(g.in80.mean()),
                }
            )
t = pd.DataFrame(rows)
t.to_csv(c.OUT + "s2_switch.csv", index=False)
print(t.to_string(), flush=True)
res["switch"] = rows
# the contrast: previous ad charged a fee, against previous ad said no fee, after the Act
# less before it
for after in (False, True):
    g = sw[sw.after == after]
    dm, se = c.cluster_mean_diff(
        g.gap.to_numpy(), (g.prev_status == "fee").to_numpy(), g.building.to_numpy()
    )
    res[f"prevfee_minus_prevnofee_after{int(after)}"] = [dm, se]
    print("after", after, "prev fee - prev no fee", dm, se, flush=True)
h[["listing_id", "status", "prev_status", "opened"]].to_parquet(
    c.OUT + "s2_status.parquet"
)
json.dump(res, open(c.OUT + "s2.json", "w"), indent=1)
