"""Compare the staged Deals files with the live ones: order, scores and cautions.

python dry_compare.py STAGING LIVE
"""

import json
import sys
from pathlib import Path

CODE = "new_counts"


def rest(row: dict) -> list:
    return [c for c in row["cautions"] if c != CODE]


def bare(row: dict) -> dict:
    return {k: v for k, v in row.items() if k != "cautions"}


if __name__ == "__main__":
    new_dir, old_dir = Path(sys.argv[1]), Path(sys.argv[2])
    new = json.loads((new_dir / "deals.json").read_text())
    old = json.loads((old_dir / "deals.json").read_text())
    metas = [json.loads((d / "meta.json").read_text()) for d in (new_dir, old_dir)]
    checks = [
        json.loads((d / "validation.json").read_text()) for d in (new_dir, old_dir)
    ]
    print("ads", len(new), len(old), "runs", metas[0]["run"], metas[1]["run"])
    ids = [r["listing_id"] for r in new]
    print("same order", ids == [r["listing_id"] for r in old])
    print(
        "same rows but for cautions", [bare(r) for r in new] == [bare(r) for r in old]
    )
    same = [rest(r) for r in new] == [r["cautions"] for r in old]
    print("other cautions unchanged", same)
    marked = [i for i, r in enumerate(new) if CODE in r["cautions"]]
    print(
        CODE, "ads", len(marked), "buildings", len({new[i]["building"] for i in marked})
    )
    for top in (100, 300):
        print(f"in the first {top} of all ads", sum(i < top for i in marked))
    print("with another caution", sum(bool(rest(new[i])) for i in marked))
    others: dict = {}
    for i in marked:
        for c in rest(new[i]):
            others[c] = others.get(c, 0) + 1
    print("their other cautions", others)
    plain = [i for i, r in enumerate(old) if not r["cautions"]]
    print(
        "uncautioned before", len(plain), "after", sum(not r["cautions"] for r in new)
    )
    for top in (100, 300):
        print(
            f"in the first {top} uncautioned before",
            len(set(marked) & set(plain[:top])),
        )
    for i in marked:
        if i in set(plain[:300]):
            r = new[i]
            print(
                i + 1,
                plain.index(i) + 1,
                r["listing_id"],
                r["below_share"],
                r["bedrooms"],
            )
    drop = ("cautions", "validation_sha256", "published_at", "written_at")
    for key in sorted(set(metas[0]) | set(metas[1])):
        if metas[0].get(key) != metas[1].get(key):
            print(
                "meta differs:",
                key,
                "" if key in drop else (metas[0].get(key), metas[1].get(key)),
            )
    print("meta cautions new", metas[0]["cautions"])
    print("meta cautions old", metas[1]["cautions"])
    for key in sorted(set(checks[0]) | set(checks[1])):
        if checks[0].get(key) != checks[1].get(key):
            print("validation differs:", key)
    for name, v in zip(("new", "old"), checks):
        u = v["uncautioned"]
        print(name, "backtest uncautioned", u["ads"], u["cautioned_ads"])
        print(name, "lowest tenth", u["by_first_ask_place"][0])
