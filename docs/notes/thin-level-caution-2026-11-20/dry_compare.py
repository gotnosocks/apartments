"""Compare the dry-run Deals files with the live ones: order, scores and cautions."""

import json
import sys

new_dir, old_dir = sys.argv[1], sys.argv[2]
new = json.load(open(f"{new_dir}/deals.json"))
old = json.load(open(f"{old_dir}/deals.json"))
print(
    "ads",
    len(new),
    len(old),
    "live run",
    json.load(open(f"{old_dir}/meta.json"))["run"],
)
print("same order", [r["listing_id"] for r in new] == [r["listing_id"] for r in old])
print(
    "same below_share",
    [r["below_share"] for r in new] == [r["below_share"] for r in old],
)
strip = lambda rows: [{k: v for k, v in r.items() if k != "cautions"} for r in rows]  # noqa: E731
print("same rows but for cautions", strip(new) == strip(old))
rest = lambda r: [c for c in r["cautions"] if c != "thin_level"]  # noqa: E731
print(
    "other cautions unchanged", [rest(r) for r in new] == [r["cautions"] for r in old]
)
marked = [i for i, r in enumerate(new) if "thin_level" in r["cautions"]]
print(
    "thin_level ads",
    len(marked),
    "buildings",
    len({new[i]["building"] for i in marked}),
)
print("in the first 300", sum(i < 300 for i in marked))
print("with another caution", sum(bool(rest(new[i])) for i in marked))
plain = [i for i, r in enumerate(old) if not r["cautions"]]
print("uncautioned before", len(plain), "after", sum(not r["cautions"] for r in new))
print("in the first 300 uncautioned before", len(set(marked) & set(plain[:300])))
for i in marked:
    r = new[i]
    print(i + 1, r["listing_id"], r.get("address"), r["below_share"], r["cautions"])
for name in ("new", "old"):
    d = new_dir if name == "new" else old_dir
    m, v = json.load(open(f"{d}/meta.json")), json.load(open(f"{d}/validation.json"))
    u = v["uncautioned"]
    low = u["by_first_ask_place"][0]
    print(
        name, m["cautions"], "backtest uncautioned", u["ads"], u["cautioned_ads"], low
    )
