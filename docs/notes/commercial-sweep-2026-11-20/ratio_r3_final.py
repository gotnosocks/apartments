"""Settle the codes of the ratio-row hand read and draft ledger lines for it. Not imported.

A first read coded apartment stands. A row the first reader coded commercial, placeholder or
unclear had a blind second read (`ratio_r2_second.py`); where the two agree the code stands,
and where they differ the code is the hand decision in `HAND`, made from the whole block.
Rows settled as commercial or placeholder get ledger lines in the format of `sw7_candidates.py`,
appended to `candidate_rows.ndjson` after the sweep's 23 lines, which stay as they were.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = Path("/data1/apartments/tmp/ratio-read")
SWEEP_SOURCE = "commercial sweep 2026-11-20 blind Sonnet reads (docs/notes/commercial-sweep-2026-11-20)"
SOURCE = (
    "commercial sweep 2026-11-21 hand read of the ratio rows, two blind Sonnet reads "
    "(docs/notes/commercial-sweep-2026-11-20)"
)
REASON = {"commercial": "nonresidential", "placeholder": "bedrooms_unknown"}
BUILDING_LEVEL = (
    HERE.parent / "building-level-read-2026-11-20" / "candidate_rows.ndjson"
)
# Hand decisions on the 23 rows whose two reads differ, with the reason for each.
HAND = {
    "R060": (
        "placeholder",
        "The text is a single period, and every ad of the building near that day is a 2 to 4 bed unit.",
    ),
    "R075": (
        "commercial",
        "This ad offers an office/studio work space with storage rooms and a price per square foot; the 3 bed ad of the unit came a year later.",
    ),
    "R142": (
        "apartment",
        "Amenity text of a residential rental building, coded as a studio.",
    ),
    "R153": (
        "placeholder",
        "The text is empty and the 0 bed code conflicts with the unit's 3 bed, 2700 sq ft loft ad.",
    ),
    "R187": (
        "commercial",
        "The whole text describes a ground-floor studio for commercial use with a garage door; no living space is offered.",
    ),
    "R191": (
        "placeholder",
        "The text is the one word LOFT, coded 0 bed, while the unit's other ad and the building's lofts are 2 bed.",
    ),
    "R248": (
        "commercial",
        "A duplex office pitched to businesses with a wet bar and no kitchen or bedroom; the same space's other ad calls it a duplex office priced per square foot.",
    ),
    "R374": (
        "commercial",
        "Hotel marketing text for suites and rooms of The Pierre, not a lease of a home.",
    ),
    "R401": (
        "unclear",
        "The text names retail space and a street entrance but never says what the 440 sq ft unit is.",
    ),
    "R458": (
        "placeholder",
        "The text is three exclamation marks, coded 0 bed, and no ad of the building near that day is a studio.",
    ),
    "R465": (
        "commercial",
        "A luxurious duplex office with gallery lighting, a wet bar in a closet, prior office tenants and a price per square foot.",
    ),
    "R471": (
        "apartment",
        "A live/work loft with bedrooms, a separate kitchen and laundry that people may live in.",
    ),
    "R484": (
        "apartment",
        "A stub text whose 1 bed, 1 bath code fits a building of small apartments.",
    ),
    "R509": (
        "apartment",
        "A stub text whose 0 bed, 1 bath code fits the building's studio ads of the same weeks.",
    ),
    "R514": (
        "apartment",
        "A stub text whose 1 bed, 950 sq ft code fits a residential building of studios to 4 beds.",
    ),
    "R523": (
        "placeholder",
        "The text is the form's own 'Draft rental description', so the ad shows no listing.",
    ),
    "R654": (
        "unclear",
        "Every ad of the building that week carries the same stub with 0, 1 and 2 bed codes, so the code may be real.",
    ),
    "R706": (
        "apartment",
        "Amenity text of a residential rental building, coded as a studio.",
    ),
    "R725": (
        "placeholder",
        "The text is a dash, coded 0 bed, and the building's ads of the same weeks are 1 and flex 2 bed units.",
    ),
    "R807": (
        "unclear",
        "The text is 'not avail' with 0 bed and 4000 sq ft and no other ad, so nothing shows what the space is.",
    ),
    "R882": (
        "apartment",
        "A parlor one-bedroom with a full kitchen, zoned for residential or commercial tenancy, that people may live in.",
    ),
    "R892": (
        "placeholder",
        "The text is one letter, coded 0 bed, 1 bath like the building's other stubs, and the building's real ad is a 2 bed, 2 bath.",
    ),
    "R916": (
        "unclear",
        "This ad pitches a showroom with frontage but offers a kitchen and laundry, and the unit's later ads are a live/work residence.",
    ),
}


def own_text(block: str) -> str:
    """The ad's own text from its read block, up to the first other ad."""
    t = block.split("\nText: ", 1)[1].split("\n- Other ad (", 1)[0]
    return " ".join(t.split())


if __name__ == "__main__":
    D = pd.read_parquet(OUT / "draw_r1.parquet")
    R1 = pd.read_csv(OUT / "r1_parsed.csv", dtype=str).rename(
        columns={"answer": "answer1", "quote": "quote1", "why": "why1"}
    )
    S = pd.read_parquet(OUT / "draw_r2.parquet")[["read2_id", "read_id"]]
    R2 = pd.read_csv(OUT / "r2_parsed.csv", dtype=str)
    X = D.merge(R1, on="read_id").merge(S, on="read_id", how="left")
    X = X.merge(R2, on="read2_id", how="left").sort_values("read_id")
    blocks = json.loads((OUT / "blocks.json").read_text())
    assert len(X) == 934 and X.answer1.notna().all()
    assert X[X.answer1 != "apartment"].answer2.notna().all()
    dis = X.answer2.notna() & (X.answer1 != X.answer2)
    assert set(X[dis].read_id) == set(HAND), "hand decisions cover the disagreements"
    X["final"] = X.answer1.where(~dis, X.read_id.map(lambda i: HAND.get(i, ("",))[0]))
    X["settled_by"] = np.select(
        [X.answer2.isna(), ~dis], ["one read", "two reads agree"], "hand"
    )
    X["hand_why"] = X.read_id.map(lambda i: HAND.get(i, ("", ""))[1])
    cols = [
        "read_id",
        "read2_id",
        "listing_id",
        "half",
        "m_text",
        "m_short",
        "bed",
        "first_day",
        "answer1",
        "answer2",
        "final",
        "settled_by",
        "quote1",
        "why1",
        "quote2",
        "why2",
        "hand_why",
    ]
    X[cols].to_csv(HERE / "reads_ratio_all.csv", index=False)
    X["set"] = np.where(X.m_text, "word", "no word")
    print("first reads", X.answer1.value_counts().to_dict())
    two = X.answer2.notna()
    print(
        "second reads",
        int(two.sum()),
        "agree",
        int((two & ~dis).sum()),
        "disagree",
        int(dis.sum()),
    )
    print(pd.crosstab(X.answer1, X.answer2.fillna("-")).to_string())
    print("final by set")
    print(pd.crosstab(X.final, X.set, margins=True).to_string())
    print("final by half")
    print(pd.crosstab(X.final, X.half, margins=True).to_string())
    print("final by set and half")
    print(pd.crosstab(X.final, [X.set, X.half]).to_string())

    keep = X[X.final.isin(list(REASON))]
    lines = []
    for r in keep.itertuples():
        bed = None if pd.isna(r.bedrooms) else float(r.bedrooms)
        if r.final == "placeholder":
            quote = own_text(blocks[r.listing_id])
        else:
            quote = r.quote1 if r.answer1 == r.final else r.quote2
        reads = f"Sonnet reads {r.read_id} and {r.read2_id}, blind to the ask"
        ev = [{"kind": "ad_text", "quote": f"Ad text: {quote}"}]
        if r.settled_by == "hand":
            ev.append(
                {
                    "kind": "read",
                    "detail": f"{reads}, differed ({r.answer1}, {r.answer2}); hand decision: {r.hand_why}",
                }
            )
        else:
            ev.append({"kind": "read", "detail": f"{reads}, agree: {r.why1}"})
        lines.append(
            {
                "change": "exclude",
                "decided": "2026-11-21",
                "evidence": ev,
                "listing_id": r.listing_id,
                "reason": REASON[r.final],
                "source": SOURCE,
                "when": {"bedrooms": bed, "period": str(r.first_day)[:7]},
            }
        )
    path = HERE / "candidate_rows.ndjson"
    old = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
    old = [x for x in old if x["source"] == SWEEP_SOURCE]
    assert len(old) == 23
    with open(path, "w") as f:
        for x in old + lines:
            f.write(json.dumps(x, sort_keys=True) + "\n")
    print(
        "new lines",
        len(lines),
        "by reason",
        keep.final.map(REASON).value_counts().to_dict(),
        "total",
        len(old) + len(lines),
    )
    new_ids = set(keep.listing_id)
    print("overlap with the 23", sorted(new_ids & {x["listing_id"] for x in old}))
    bl = [json.loads(x) for x in BUILDING_LEVEL.read_text().splitlines() if x.strip()]
    hit = sorted(new_ids & {str(x.get("listing_id")) for x in bl})
    print("building-level lines", len(bl), "overlap", len(hit), hit)
