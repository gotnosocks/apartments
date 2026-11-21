"""Review round: score the full read of the 195 and draft ledger bedroom sets.

A row is kept when the read's best count equals the text mark's count (`bed_text`, 5 and over
read as `5+`) and most of the unit's other counted ads code that count (`majority` of
`z8_full_draw.py`). Kept rows become `bedrooms` set rows in `candidate_rows.ndjson`, in the
format of `commercial-sweep-2026-11-20/candidate_rows.ndjson`, backed by the agreeing ads of
the unit (`other_ad`). The `ad_text` quote is the reader's quote when the ad's own text holds
it, else the words around the ad's own count. Nothing is imported. The reads go to
`full_reads.csv`, and the drafted rows are checked against the sweep's and the building-level
read's candidate files.
"""

import json
import re
from pathlib import Path

import pandas as pd

OUT = Path("/data1/apartments/tmp/zero-bed")
HERE = Path(__file__).resolve().parent
NOTES = HERE.parent
WORD = {"0": 0, "1": 1, "2": 2, "3": 3, "4": 4, "5+": 5}
NUM = {2: "two|2", 3: "three|3", 4: "four|4", 5: "five|5"}
SOURCE = "zero-bed apartments 2026-11-21 blind Sonnet reads (docs/notes/zero-bed-apartments-2026-11-21)"


def own_texts() -> dict[str, str]:
    """The ad's own text in each reader block, by read id."""
    out = {}
    for p in sorted(OUT.glob("full_batch_*.md")):
        for b in p.read_text().split("\n### ")[0:]:
            b = b.removeprefix("### ")
            rid = b.split("\n", 1)[0].strip()
            t = re.search(r"^Text: (.*)$", b, re.M)
            out[rid] = t.group(1) if t else ""
    return out


def quote_for(text: str, quote: str, n: int) -> str:
    if quote and quote in text:
        return quote
    k = min(n, 5)
    m = re.search(rf"\b(?:{NUM[k]})[\s-]*(?:bed(?:room)?s?|br|bd|bdrm)\b", text, re.I)
    if not m:
        return ""
    a, b = max(0, m.start() - 60), min(len(text), m.end() + 60)
    return text[a:b].strip()


if __name__ == "__main__":
    L = pd.concat(
        [
            pd.read_json(p, lines=True, dtype=str)
            for p in sorted(OUT.glob("full_labels_*.ndjson"))
        ]
    )
    D = pd.read_parquet(OUT / "full_draw.parquet").merge(L, on="read_id", how="left")
    assert len(D) == 195 and D.best_count.notna().all()
    D["best"] = D.best_count.map(WORD)
    D["agree_text"] = D.best == D.bed_text.clip(upper=5)
    D["keep"] = D.agree_text & D.majority
    print("best_count", D.best_count.value_counts().sort_index().to_dict())
    print("read agrees with the text mark", int(D.agree_text.sum()), "of", len(D))
    print(
        "read agrees, by half",
        D.groupby("half").agree_text.agg(["sum", "size"]).to_dict("index"),
    )
    print(
        "unit majority",
        int(D.majority.sum()),
        "read agrees and majority (kept)",
        int(D.keep.sum()),
    )
    print(pd.crosstab(D.agree_text, D.majority).to_string())
    print(
        "kept by half",
        D[D.keep].half.value_counts().to_dict(),
        "count set",
        D[D.keep].bed_text.value_counts().sort_index().to_dict(),
    )
    print("same_apartment of kept", D[D.keep].same_apartment.value_counts().to_dict())
    T = own_texts()
    cand = []
    noquote = 0
    for r in D[D.keep].sort_values("listing_id").itertuples():
        n = int(r.bed_text)
        q = quote_for(T.get(r.read_id, ""), r.quote, n)
        agree = [str(i) for i in r.agree_ids]
        ev = []
        if q:
            ev.append({"kind": "ad_text", "quote": f"Ad text: {q}"})
        else:
            noquote += 1
        ev.append(
            {
                "detail": f"{int(r.n_agree)} of the unit's {int(r.n_other)} other ads with a typed count "
                f"code {n} bedrooms.",
                "kind": "other_ad",
                "listings": agree,
            }
        )
        ev.append(
            {
                "detail": f"Sonnet read {r.read_id}, blind to the ask: {r.reason} The text "
                f"states {n} bedrooms for the unit and the row codes a studio.",
                "kind": "read",
            }
        )
        cand.append(
            {
                "change": "set",
                "decided": "2026-11-21",
                "evidence": ev,
                "listing_id": str(r.listing_id),
                "set": {"bedrooms": float(n)},
                "source": SOURCE,
                "when": {"bedrooms": 0.0, "period": str(r.first_day)[:7]},
            }
        )
    with open(HERE / "candidate_rows.ndjson", "w") as f:
        for c in cand:
            f.write(json.dumps(c, sort_keys=True) + "\n")
    print("drafted", len(cand), "without an ad_text quote", noquote)
    mine = {c["listing_id"] for c in cand}
    for name in ("commercial-sweep-2026-11-20", "building-level-read-2026-11-20"):
        other = {
            json.loads(x)["listing_id"]
            for x in (NOTES / name / "candidate_rows.ndjson").read_text().splitlines()
            if x.strip()
        }
        print("overlap with", name, len(mine & other))
    keep = [
        "read_id",
        "listing_id",
        "building",
        "half",
        "bed_text",
        "u2_min",
        "n_other",
        "n_agree",
        "majority",
        "text_count",
        "same_apartment",
        "best_count",
        "agree_text",
        "keep",
        "quote",
        "reason",
    ]
    D[keep].sort_values("read_id").to_csv(HERE / "full_reads.csv", index=False)
