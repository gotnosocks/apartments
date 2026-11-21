"""Page facts with no ask level, and the lift of each candidate phrase on them, by half.

For every page with two or more candidate ads:
- `beds_n`: distinct bedroom counts; `mixed` when two or more;
- `sqft_differ`: two stated sizes more than 15% apart;
- `ov_k_t`: a pair of ads running at once for at least k days with different bedroom
  counts or asks more than t apart in log (from `a3_pairs.py`).
A phrase's lift is the share of its pages with a fact over the share among all pages of
the half. The yardsticks for the text mark are the overlap and size facts; the text mark
itself is the yardstick for the overlap mark (`a7_choose.py`).
"""

import sys

import duckdb

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from a4_text import PHRASES  # noqa: E402

OUT = "/data1/apartments/tmp/any-unit"
FORMS = [(k, t) for k in (1, 4, 14) for t in (0.05, 0.10, 0.20)]

if __name__ == "__main__":
    c = duckdb.connect()
    ov = ", ".join(
        f"bool_or(shared >= {k} and (beds_differ or ask_gap > {t})) ov_{k}_{int(t * 100)}"
        for k, t in FORMS
    )
    ov += ", bool_or(shared >= 4 and beds_differ) ovb_4, bool_or(shared >= 4 and ask_gap > 0.10) ova_4_10"
    ovc = ", ".join(
        f"coalesce(o.ov_{k}_{int(t * 100)}, false) ov_{k}_{int(t * 100)}"
        for k, t in FORMS
    )
    c.sql(f"""
    copy (
      with f as (
        select unit_id, any_value(building) building, any_value(half) half, count(*) ads,
               count(distinct bedrooms) beds_n,
               max(square_feet) filter (where square_feet between 150 and 6000) sq_hi,
               min(square_feet) filter (where square_feet between 150 and 6000) sq_lo
        from '{OUT}/ads.parquet' group by 1 having count(*) >= 2
      ),
      o as (select unit_id, {ov} from '{OUT}/pairs.parquet' group by 1)
      select f.*, beds_n >= 2 mixed, coalesce(sq_hi > 1.15 * sq_lo, false) sqft_differ,
             {ovc}, coalesce(o.ovb_4, false) ovb_4, coalesce(o.ova_4_10, false) ova_4_10,
             {", ".join("t." + k for k in PHRASES)}
      from f left join o using (unit_id) join '{OUT}/page_text.parquet' t using (unit_id)
    ) to '{OUT}/pages.parquet' (format parquet)
    """)
    P = f"'{OUT}/pages.parquet'"
    facts = ["mixed", "sqft_differ", "ov_4_10", "ovb_4", "ova_4_10"]
    avg = ", ".join(f"round(100 * avg({f}::int), 1) {f}" for f in facts)
    print("pages with two or more ads, % with each fact")
    base = c.sql(
        f"select half, count(*) pages, {avg} from {P} group by 1 order by 1"
    ).df()
    print(base.to_string(index=False))
    for h in "AB":
        print(f"\nhalf {h}: phrase pages, % with each fact")
        q = " union all ".join(
            f"select '{k}' phrase, count(*) pages, {avg} from {P} where half = '{h}' and {k}"
            for k in PHRASES
        )
        print(c.sql(q).df().to_string(index=False))
    print("\nhalf A: overlap forms, pages and % in buildings with any text phrase page")
