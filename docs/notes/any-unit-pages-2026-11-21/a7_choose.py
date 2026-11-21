"""Choose each mark's form on half A and check it on half B.

Text mark: a candidate phrase joins when its half-A pages hold at least twice the half's
rate of both the overlap fact (`ov_4_10`) and the size fact (`sqft_differ`), from
`a6_page_facts.py`. Overlap mark: among the forms, the one whose half-A pages carry the text
mark and the size fact at the highest rate, among forms marking at least 1,000 half-A pages.
Neither choice reads an ask level or a model.
"""

import duckdb

OUT = "/data1/apartments/tmp/any-unit"
P = f"'{OUT}/pages.parquet'"
PHR = [
    "any_unit",
    "multiple_units",
    "other_units",
    "similar_units",
    "may_vary",
    "various_units",
    "prices_vary",
    "representative",
]

if __name__ == "__main__":
    c = duckdb.connect()
    b = c.sql(
        f"select avg(ov_4_10::int) ov, avg(sqft_differ::int) sq from {P} where half = 'A'"
    ).fetchone()
    keep = []
    for k in PHR:
        ov, sq, n = c.sql(
            f"select avg(ov_4_10::int), avg(sqft_differ::int), count(*) from {P} "
            f"where half = 'A' and {k}"
        ).fetchone()
        lo, ls = ov / b[0], sq / b[1]
        print(f"{k:16s} pages {n:6d} lift overlap {lo:4.1f} lift size {ls:4.1f}")
        if lo >= 2 and ls >= 2:
            keep.append(k)
    print("text mark:", " or ".join(keep))
    tm = "(" + " or ".join(keep) + ")"
    print("\noverlap forms, half A: pages, % text mark, % size differs, % mixed")
    forms = [
        c for c in c.sql(f"select * from {P} limit 0").columns if c.startswith("ov")
    ]
    for f in forms:
        r = c.sql(
            f"select count(*), round(100*avg({tm}::int),1), round(100*avg(sqft_differ::int),1), "
            f"round(100*avg(mixed::int),1) from {P} where half = 'A' and {f}"
        ).fetchone()
        print(f"{f:10s}", r)
    print(
        "\nall half-A pages: % text mark",
        c.sql(f"select round(100*avg({tm}::int),2) from {P} where half='A'").fetchone(),
    )
