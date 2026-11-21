"""The two marks as chosen on half A (`a7_choose.py`), their counts, and the check on half B.

- text: a candidate ad of the page says it offers any unit of the building
  (`a4_text.PHRASES["any_unit"]`);
- overlap: two candidate ads of the page run at once for at least 4 days with asks more
  than 10% apart (`ova_4_10`).
Pages with one candidate ad carry no overlap and are counted for the text mark only.
Writes `marks.parquet`, one row per page with two or more candidate ads.
"""

import duckdb

OUT = "/data1/apartments/tmp/any-unit"
P = f"'{OUT}/pages.parquet'"

if __name__ == "__main__":
    c = duckdb.connect()
    c.sql(f"""
    copy (select unit_id, building, half, ads, mixed, sqft_differ,
                 any_unit m_text, ova_4_10 m_overlap, (any_unit or ova_4_10) m_any
          from {P}) to '{OUT}/marks.parquet' (format parquet)
    """)
    M = f"'{OUT}/marks.parquet'"
    print(
        "text-marked pages with one candidate ad:",
        c.sql(
            f"select half, count(*) from '{OUT}/page_text.parquet' where any_unit and ads = 1 group by 1 order by 1"
        ).fetchall(),
    )
    print("\npages with two or more ads by mark and half")
    print(
        c.sql(f"""
    select half, count(*) pages,
           sum(m_text::int) n_text, sum(m_overlap::int) n_overlap,
           sum((m_text and m_overlap)::int) n_both, sum(m_any::int) n_either,
           sum(ads) filter (where m_any) either_ads,
           count(distinct building) filter (where m_any) either_buildings
    from {M} group by 1 order by 1""")
        .df()
        .to_string(index=False)
    )
    print(
        "\n% of pages with each fact: all, text, overlap, either (half B is the check)"
    )
    for h in "AB":
        r = c.sql(f"""
        select round(100*avg(sqft_differ::int),1), round(100*avg(mixed::int),1),
          round(100*avg(sqft_differ::int) filter (where m_text),1),
          round(100*avg(mixed::int) filter (where m_text),1),
          round(100*avg(sqft_differ::int) filter (where m_overlap),1),
          round(100*avg(m_text::int) filter (where m_overlap),2),
          round(100*avg(m_overlap::int) filter (where m_text),2),
          round(100*avg(m_text::int),2), round(100*avg(m_overlap::int),2)
        from {M} where half = '{h}'""").fetchone()
        print(
            h,
            "size differs: all",
            r[0],
            "text",
            r[2],
            "overlap",
            r[4],
            "| mixed beds: all",
            r[1],
            "text",
            r[3],
            "| text among overlap",
            r[5],
            "vs all",
            r[7],
            "| overlap among text",
            r[6],
            "vs all",
            r[8],
        )
    print("\nbuildings holding the most marked pages")
    print(
        c.sql(f"""select building, half, count(*) pages, sum(m_text::int) n_text,
                    sum(m_overlap::int) n_overlap from {M} where m_any
                    group by 1, 2 order by 3 desc limit 12""")
        .df()
        .to_string(index=False)
    )
