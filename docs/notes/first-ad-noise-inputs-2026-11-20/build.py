"""Inputs known on an ad's first day, for first ads of units and the backtest's open ads.

Usage: build.py DATASET_DIR [CUT]. Reads the outlier sprint's table of placed ads (label, lister,
lot) and its pulls of city records, and writes inputs.parquet in the scratch folder.

Every input of an ad opened on day d reads ads opened before d and records first dated
before d, plus the ad's own label, lister and counts. No input reads an ask. `check.py`
compares this build with builds given CUT, a day: those drop every ad opened after CUT and
every record first dated after it, replace later closing days by CUT + 1 (still open), and
write the inputs of the ads opened on CUT.
"""

import json
import re
import sys

import duckdb
import pyarrow as pa

OUT = "/data1/apartments/tmp/po-firstad-noise"
G = "/data1/apartments/tmp/outlier-sprint/s2/G"
JUNK = re.compile(
    r"^(BLDG|BUILDING|BASEMENT|BASEM|BASEME|BASE|BSMT|CELLAR|ROOF|HALL|LOBBY|STORE|PUBLIC"
    r"|NA|NONE|ALL|YARD|\d*(ST|ND|RD|TH)?FL(R|OOR|O|OO)?\d*"
    r"|.*(FLOOR|FLOO|BATH|KIT|HALL|STAIR).*)$"
)
PARSE = """case when regexp_matches({c}, '^\\d+[A-Z]*$') then regexp_extract({c}, '^(\\d+)', 1)
     when regexp_matches({c}, '^[A-Z]+\\d+$') then regexp_extract({c}, '(\\d+)$', 1) end fl,
case when regexp_matches({c}, '^\\d+[A-Z]*$') then regexp_replace({c}, '^\\d+', '')
     when regexp_matches({c}, '^[A-Z]+\\d+$') then regexp_replace({c}, '\\d+$', '') end ln"""
BEFORE = "range between unbounded preceding and interval 1 day preceding"


def norm(a):
    a = re.sub(r"[^A-Z0-9]", "", (a or "").upper())
    a = re.sub(r"^(APT|UNIT|APARTMENT|NO)(?=\w)", "", a)
    return a.lstrip("0")


def dated_records():
    """(lot, label, first date) of eviction records, and condo unit lots with no date."""
    rows = []
    for r in json.load(open(f"{G}/city/evictions.json")):
        n = norm(r.get("eviction_apt_num"))
        if n and not JUNK.match(n) and r.get("bbl"):
            rows.append((r["bbl"][:10], n, r["d0"][:10]))
    bill = {
        (r["borocode"], int(r["condono"])): r["bbl"][:10]
        for r in json.load(open(f"{G}/city/condo/pluto_condono.json"))
    }
    for r in json.load(open(f"{G}/city/condo/units.json")):
        n = norm(r.get("aptno"))
        b = bill.get((r["boro"], int(r["condo_number"]) % 100000))
        if n and b and not JUNK.match(n):
            rows.append((b, n, "1900-01-01"))
    return pa.table(
        {
            "bbl": [r[0] for r in rows],
            "nlab": [r[1] for r in rows],
            "d0": [r[2] for r in rows],
        }
    )


def main(dataset, cut=None):
    tag = "" if cut is None else f"-cut-{cut}"
    con = duckdb.connect(f"{OUT}/w{tag}.duckdb")
    con.execute(
        f"set memory_limit='2GB'; set threads=3; set temp_directory='{OUT}/tmp'"
    )
    con.execute(f"attach '{G}/work/w.duckdb' as g (read_only)")
    con.register("x", dated_records())
    con.execute("""
    create or replace table recs as
    select bbl, nlab, min(d0)::date d0 from (
      select bbl, nlab, d0 from g.hpd union all select * from x) group by 1, 2""")
    if cut is not None:
        con.execute(f"delete from recs where d0 > date '{cut}'")
    con.execute("""
    create or replace table fetched as
    select bbl from g.hpd_lots union select bbl from g.condo_lots""")
    # ads with the as-of counts of their building and lister
    off = "off_day" if cut is None else f"least(off_day, date '{cut}' + 1)"
    keep = "" if cut is None else f"and on_day <= date '{cut}'"
    con.execute(f"""
    create or replace table ads as
    with a as (
      select * replace ({off} as off_day) from g.ads where on_day is not null {keep}),
    pr as (
      select b.listing_id, b.on_day - p.off_day gap,
             p.bedrooms = b.bedrooms
             and p.full_baths is not distinct from b.full_baths
             and p.half_baths is not distinct from b.half_baths same_counts
      from a b join a p
        on p.building_id = b.building_id and p.lister = b.lister
       and p.nlab <> b.nlab and p.on_day < b.on_day
       and p.off_day between b.on_day - 30 and b.on_day),
    rl as (
      select listing_id, min(gap) gap_any,
             min(case when same_counts then gap end) gap_same
      from pr group by 1)
    select a.listing_id, a.building_id, a.nlab, a.lister, a.bbl, a.apartments, a.on_day,
           a.off_day, coalesce(rl.gap_same <= 7, false) relabel,
           rl.gap_same, rl.gap_any,
           count(*) over (partition by a.building_id order by a.on_day {BEFORE}) b_ads,
           min(a.on_day) over (partition by a.building_id) b_first,
           count(*) over (partition by a.lister order by a.on_day {BEFORE}) l_ads,
           coalesce(sum(coalesce(rl.gap_same <= 7, false)::int)
             over (partition by a.lister order by a.on_day {BEFORE}), 0) l_rel,
           count(*) over (partition by a.building_id, a.lister
             order by a.on_day {BEFORE}) lb_ads,
           count(*) over (partition by a.building_id, a.lister order by a.on_day
             range between interval 90 day preceding and interval 1 day preceding) lb_90,
           count(*) over (partition by a.building_id, a.nlab
             order by a.on_day {BEFORE}) lab_ads
    from a left join rl using (listing_id)""")
    # the day a label's second spell opened (a gap of over 180 days since its last ad)
    con.execute("""
    create or replace table est as
    with s as (
      select building_id, nlab, on_day,
             lag(coalesce(off_day, on_day)) over (
               partition by building_id, nlab order by on_day, listing_id) prev_off
      from ads where nlab <> ''),
    t as (
      select building_id, nlab, on_day,
             row_number() over (partition by building_id, nlab order by on_day) k
      from s where prev_off is null or on_day - prev_off > 180)
    select building_id, nlab, on_day est_day from t where k = 2""")
    con.execute(f"""
    create or replace table grid as
    select building_id, fl, ln, min(gday) gday from (
      select building_id, {PARSE.format(c="nlab")}, est_day gday from est
      union all
      select b.building_id, {PARSE.format(c="r.nlab")}, r.d0 from recs r
      join (select distinct building_id, bbl from ads where bbl is not null) b using (bbl))
    where fl is not null group by 1, 2, 3""")
    only = "" if cut is None else f"and r.d = date '{cut}'"
    # targets: each unit's first row in the dataset, and every held-out row
    con.execute(f"""
    create or replace table rows as
    select listing_id::varchar listing_id, building, unit_id, first_day::date d, open held,
           ln(latest_ask) y, bedrooms, year(price_at::date) yr,
           row_number() over (partition by coalesce(unit_id, listing_id::varchar)
             order by first_day::date, listing_id) k
    from read_parquet('{dataset}/rows.parquet')""")
    con.execute(f"""
    create or replace table tg as
    select r.listing_id, r.building, r.held, r.k, r.d, a.building_id, a.nlab, a.lister,
           a.bbl, a.apartments, a.relabel, a.b_ads, (r.d - a.b_first) / 365.25 b_years,
           a.l_ads, a.l_rel, a.lab_ads, a.lb_ads, a.lb_90, a.gap_same, a.gap_any, {PARSE.format(c="a.nlab")}
    from rows r join ads a using (listing_id)
    where (r.k = 1 or r.held) {only}""")
    con.execute("""
    create or replace table inputs as
    with gl as (
      select t.listing_id, count(distinct g.fl) grid_floors,
             count(distinct case when g.ln = t.ln then g.fl end) line_floors
      from tg t join grid g
        on g.building_id = t.building_id and g.fl <> t.fl and g.gday < t.d
      where t.fl is not null group by 1),
    rc as (
      select t.listing_id, count(*) rec_labels,
             max((r.nlab = t.nlab)::int) in_recs
      from tg t join recs r on r.bbl = t.bbl and r.d0 < t.d group by 1),
    e as (
      select t.listing_id from tg t join est e
        on e.building_id = t.building_id and e.nlab = t.nlab and e.est_day < t.d)
    select t.*, coalesce(rc.in_recs, 0) = 1 in_recs, coalesce(rc.rec_labels, 0) rec_labels,
           (f.bbl is not null) lot_fetched, (e.listing_id is not null) spells2,
           coalesce(gl.grid_floors, 0) grid_floors, coalesce(gl.line_floors, 0) line_floors
    from tg t left join gl using (listing_id) left join rc using (listing_id)
    left join e using (listing_id) left join fetched f on f.bbl = t.bbl""")
    con.execute(f"""
    copy (
      select *, case
        when nlab is null or nlab = '' then 'no label'
        when in_recs or spells2 then 'pass'
        when fl is not null and grid_floors >= 2 and line_floors > 0 then 'pass'
        when not (lot_fetched and apartments > 0 and rec_labels >= 0.75 * apartments)
          then 'thin records'
        when fl is null or grid_floors < 2 then 'no grid'
        else 'fail' end label_st
      from inputs) to '{OUT}/inputs{tag}.parquet' (format parquet)""")
    if cut is not None:
        return
    # the proxy of the 2026-11-12 note: a training row against the other rows of its cell
    con.execute(f"""
    copy (
      with c as (
        select *, count(*) over w n, sum(y) over w s from rows where not held
        window w as (partition by building, bedrooms, yr))
      select listing_id, building, k, d, bedrooms, yr, y - (s - y) / (n - 1) cell_res
      from c where n >= 3) to '{OUT}/proxy.parquet' (format parquet)""")
    q = "select held, k = 1 first_row, count(*) n from rows group by all order by all"
    print("dataset rows by held-out and first row of the unit")
    print(con.execute(q).df().to_string(index=False))
    q = "select held, count(*) n, count(lister) lister, count(bbl) lot from tg group by 1"
    print("targets joined to the ads table")
    print(con.execute(q).df().to_string(index=False))
    q = "select label_st, count(*) n from read_parquet('{}/inputs.parquet') group by 1"
    print(con.execute(q.format(OUT) + " order by 1").df().to_string(index=False))


if __name__ == "__main__":
    main(*sys.argv[1:])
