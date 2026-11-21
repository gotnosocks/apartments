"""Candidate phrases on each ad's text, and each page's phrase flags.

One text per listing: the description of its last ACTIVE record, else of its last record
(the rule of `descriptions.record_descriptions`). Each candidate phrase is a word-bounded,
case-insensitive pattern. A page carries a phrase when any of its candidate ads does. The
text is the only input; no ask is read. Writes `texts.parquet` (one row per candidate ad:
flags, label, and the text) and `page_text.parquet` (one row per page: flags).
"""

import duckdb

OUT = "/data1/apartments/tmp/any-unit"
UNIT = r"(?:units?|apartments?|apts?|residences?|homes?|layouts?|floor ?plans?)"
PHRASES = {
    "any_unit": rf"\bany (?:other |available |vacant )?{UNIT} in (?:the|this|our) building\b"
    rf"|\bany of (?:the|our) (?:available |vacant )?{UNIT}\b",
    "multiple_units": rf"\b(?:multiple|several|many|numerous) {UNIT} (?:are |now )?available\b",
    "other_units": rf"\b(?:other|more|additional) {UNIT} (?:are |also )?available\b"
    rf"|\b(?:ask|inquire|contact us) (?:me |us )?about (?:our )?other {UNIT}\b",
    "similar_units": rf"\bsimilar {UNIT}\b",
    "may_vary": r"\b(?:units?|apartments?|unit shown|apartment shown|photos?|pictures?|images?"
    r"|finishes|layouts?|exposures?|floors?) (?:shown |pictured )?(?:may|might|will|can) "
    r"(?:vary|differ)\b",
    "various_units": rf"\b(?:various|different|varying) (?:floors|{UNIT}|exposures|lines)\b",
    "prices_vary": r"\b(?:prices?|pricing|rents?) (?:start(?:s|ing)?|rang(?:e|es|ing)|var(?:y|ies))\b"
    r"|\bstarting (?:at|from) \$",
    "representative": r"\b(?:photos?|pictures?|images?) (?:are |is )?(?:of (?:a |an )?)?"
    r"(?:representative|model|similar|sample|another)\b|\bfor illustrative purposes\b",
}


if __name__ == "__main__":
    c = duckdb.connect()
    c.sql("set memory_limit='2GB'")
    flags = list(PHRASES)
    cols = ", ".join(
        f"regexp_matches(coalesce(r.description, ''), '(?i){v.replace(chr(39), chr(39) * 2)}') {k}"
        for k, v in PHRASES.items()
    )
    c.sql(f"""
    copy (
      with r as (
        select listing_id, label, description,
               row_number() over (partition by listing_id
                                  order by (status = 'ACTIVE') desc, collected_at desc) k
        from '{OUT}/rec_texts.parquet'
      )
      select a.listing_id, a.unit_id, a.building, a.half, r.label,
             r.description is not null has_text, {cols}, r.description
      from '{OUT}/ads.parquet' a left join r on r.listing_id = a.listing_id and r.k = 1
    ) to '{OUT}/texts.parquet' (format parquet)
    """)
    T = f"'{OUT}/texts.parquet'"
    print(
        c.sql(f"select count(*) ads, sum(has_text::int) with_text from {T}").fetchall()
    )
    anys = ", ".join(f"bool_or({k}) {k}" for k in flags)
    c.sql(f"""
    copy (select unit_id, any_value(building) building, any_value(half) half, count(*) ads, {anys}
          from {T} group by 1) to '{OUT}/page_text.parquet' (format parquet)
    """)
    sums = ", ".join(f"sum({k}::int) {k}" for k in flags)
    print("ads by phrase and half")
    print(
        c.sql(f"select half, {sums} from {T} group by 1 order by 1")
        .df()
        .set_index("half")
        .T
    )
    print("pages by phrase and half")
    print(
        c.sql(
            f"select half, {sums} from '{OUT}/page_text.parquet' group by 1 order by 1"
        )
        .df()
        .set_index("half")
        .T
    )
