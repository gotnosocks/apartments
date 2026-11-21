"""Deals ads on marked pages, from the live build the Deals page was published from.

The Deals table (`/data1/apartments/site/deals/deals.json`, sorted by `below_share`) comes
from the run `...-6cd1f12b-range-m3`, whose build is `ads-417bbdf5ed03f5d3.parquet` with
`records-941f4a6588cbd8cc.parquet`. The marks are recomputed there, as `a8_marks.py` defines
them, for the pages holding a Deals ad: `text` when a candidate ad of the page says it offers
any unit of the building; `overlap` when two candidate ads run at once for 4 days or more
with asks more than 10% apart. `overlap_other` leaves out the Deals ad's own pairs, as the
held-out test does. No model output is read beyond the table's order.
"""

import json
import re
import sys

import duckdb
import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from a4_text import PHRASES  # noqa: E402

OUT = "/data1/apartments/tmp/any-unit"
ADS = "/data1/apartments/pipeline/datasets/ads-417bbdf5ed03f5d3.parquet"
REC = "/data1/apartments/pipeline/datasets/records-941f4a6588cbd8cc.parquet"
RX = re.compile(PHRASES["any_unit"], re.I)

if __name__ == "__main__":
    deals = pd.DataFrame(json.load(open("/data1/apartments/site/deals/deals.json")))
    assert deals.below_share.is_monotonic_increasing
    deals["rank"] = range(1, len(deals) + 1)
    deals["plain"] = deals.cautions.map(len) == 0
    deals["rank_plain"] = deals.plain.cumsum().where(deals.plain)
    c = duckdb.connect()
    c.register("d", deals[["listing_id"]])
    pg = c.sql(f"""
      select listing_id::varchar listing_id, unit_id, first_day::date first_day,
             coalesce(off_day::date, fetched::date) end_day,
             least(first_ask, latest_ask) ask_lo, greatest(first_ask, latest_ask) ask_hi
      from '{ADS}' where fate is not null and unit_id in
        (select unit_id from '{ADS}' a join d on a.listing_id::varchar = d.listing_id
         where a.unit_id is not null)
    """).df()
    own = c.sql(f"""select listing_id::varchar listing_id, unit_id from '{ADS}'
                    where listing_id::varchar in (select listing_id from d)""").df()
    print(
        "deals",
        len(deals),
        "with a unit page",
        int(own.unit_id.notna().sum()),
        "page ads",
        len(pg),
        flush=True,
    )
    wanted = set(pg.listing_id)
    f = pq.ParquetFile(REC)
    best = {}
    for g in range(f.metadata.num_row_groups):
        t = f.read_row_group(
            g, columns=["listing_id", "collected_at", "raw_listing_json"]
        )
        for lid, ca, s in zip(
            t.column("listing_id").to_pylist(),
            t.column("collected_at").to_pylist(),
            t.column("raw_listing_json").to_pylist(),
        ):
            lid = str(lid)
            if lid not in wanted or not s:
                continue
            j = json.loads(s) or {}
            key = (j.get("status") == "ACTIVE", ca)
            if lid not in best or key >= best[lid][0]:
                best[lid] = (key, bool(RX.search(j.get("description") or "")))
    pg["any_unit"] = pg.listing_id.map(lambda x: best.get(x, (None, False))[1])
    print("page ads with a text", len(best), "with the phrase", int(pg.any_unit.sum()))
    c.register("pg", pg)
    c.register("own", own)
    m = c.sql("""
      with pr as (
        select x.unit_id, x.listing_id l1, y.listing_id l2
        from pg x join pg y on x.unit_id = y.unit_id and x.listing_id < y.listing_id
        where datediff('day', greatest(x.first_day, y.first_day),
                       least(x.end_day, y.end_day)) + 1 >= 4
          and (x.ask_hi * 1.0 < y.ask_lo / exp(0.10) or y.ask_hi * 1.0 < x.ask_lo / exp(0.10))
      )
      select own.listing_id,
             coalesce((select bool_or(any_unit) from pg where pg.unit_id = own.unit_id), false) m_text,
             exists (select 1 from pr where pr.unit_id = own.unit_id) m_overlap,
             exists (select 1 from pr where pr.unit_id = own.unit_id
                     and pr.l1 <> own.listing_id and pr.l2 <> own.listing_id) m_overlap_other
      from own
    """).df()
    D = deals.merge(m, on="listing_id", how="left").fillna(
        {"m_text": False, "m_overlap": False, "m_overlap_other": False}
    )
    D["m_any"] = D.m_text | D.m_overlap
    D["m_any_other"] = D.m_text | D.m_overlap_other
    D[
        [
            "listing_id",
            "rank",
            "rank_plain",
            "building",
            "m_text",
            "m_overlap",
            "m_overlap_other",
        ]
    ].query("m_text or m_overlap").to_csv(
        __file__.rsplit("/", 1)[0] + "/deals_marked.csv", index=False
    )
    for col in ("m_text", "m_overlap", "m_overlap_other", "m_any", "m_any_other"):
        top = D[D["rank"] <= 100][col]
        topp = D[D.rank_plain <= 100][col]
        print(
            f"{col:16s} all {int(D[col].sum()):4d} of {len(D)} ({100 * D[col].mean():.2f}%)"
            f" | top 100: {int(top.sum())}"
            f" | uncautioned {int(D[D.plain][col].sum())} of {int(D.plain.sum())},"
            f" their top 100: {int(topp.sum())}"
        )
    print(
        "marked Deals ads by building:",
        D[D.m_any].building.value_counts().head(8).to_dict(),
    )
