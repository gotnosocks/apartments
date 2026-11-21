"""Pairs of candidate ads on one page that run at once, from `a2_ads.py`'s frame.

For each pair on a page whose runs share at least one day: the days shared, whether the
bedroom counts differ, and `ask_gap`, the log distance between the two ads' ask ranges
(0 when the ranges meet). Prints the distribution on half A, where the mark's form is
chosen.
"""

import duckdb

OUT = "/data1/apartments/tmp/any-unit"
c = duckdb.connect()
c.sql(f"create view a as select * from '{OUT}/ads.parquet'")
c.sql(f"""
copy (
  select x.unit_id, x.building, x.half,
         x.listing_id l1, y.listing_id l2,
         datediff('day', greatest(x.first_day, y.first_day),
                  least(x.end_day, y.end_day)) + 1 shared,
         (x.bedrooms is distinct from y.bedrooms) beds_differ,
         case when x.ask_hi < y.ask_lo then ln(y.ask_lo / x.ask_hi)
              when y.ask_hi < x.ask_lo then ln(x.ask_lo / y.ask_hi)
              else 0 end ask_gap,
         abs(datediff('day', x.first_day, y.first_day)) start_gap
  from a x join a y on x.unit_id = y.unit_id and x.listing_id < y.listing_id
  where greatest(x.first_day, y.first_day) <= least(x.end_day, y.end_day)
) to '{OUT}/pairs.parquet' (format parquet)
""")
c.sql(f"create view p as select * from '{OUT}/pairs.parquet'")
print(
    c.sql(
        "select half, count(*) pairs, count(distinct unit_id) pages from p group by 1"
    ).df()
)
print("half A, pairs by days shared and what differs")
print(
    c.sql("""
select case when shared<=3 then 'a 1-3' when shared<=13 then 'b 4-13'
            when shared<=29 then 'c 14-29' else 'd 30+' end shared,
       count(*) pairs,
       round(avg(beds_differ::int),3) beds_differ,
       round(avg((ask_gap>0.03)::int),3) gap3,
       round(avg((ask_gap>0.10)::int),3) gap10,
       round(avg((ask_gap>0.20)::int),3) gap20
from p where half='A' group by 1 order by 1
""").df()
)
