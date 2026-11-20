"""Scan the records file: per listing, the description of its ACTIVE record fetched last (else its
latest record), as descriptions.record_descriptions picks it. Writes per listing: stripped length,
word flags, and the text itself (cut at 1500 chars) when short or when it has commercial wording."""

import json, re, sys
import pyarrow.parquet as pq, pandas as pd

REC = "/data1/apartments/pipeline/datasets/records-941f4a6588cbd8cc.parquet"
TAG = re.compile(r"<[^>]+>")
WS = re.compile(r"\s+")
STRONG = re.compile(
    r"office space|retail|store ?front|commercial (space|unit|lease|use|property|building|tenant)|medical (office|space|use)|doctor'?s? office|dental office|professional (office|space|use)|restaurant|warehouse|gallery|triple net|\bnnn\b|per (sf|sq\.? ?ft\.?|square foot)|/ ?r?sf\b|rentable square|build to suit|signage|foot traffic|white ?box|community facility|(store|shop|space|office|offices) for (rent|lease)|salon|co-?working|land lease|any use|all uses"
)
ANY = re.compile(r"\b(office|offices|commercial|medical|business|store|shop)\b")
RES = {
    "bed": r"\bbed(room)?s?\b|\b\d ?brs?\b|\bbr\b",
    "apt": r"\bapartments?\b|\bapt\b",
    "kitchen": r"\bkitchen",
    "living": r"living (room|area|space)",
    "bath": r"\bbath(room)?s?\b",
    "closet": r"\bclosets?\b",
    "studio": r"\bstudio\b",
    "home": r"\bhome\b|\bresiden",
    "laundry": r"laundry|washer|dishwasher",
    "live": r"live[ /-]?work",
}
RES = {k: re.compile(v) for k, v in RES.items()}
f = pq.ParquetFile(REC)
latest = {}
active = {}
for g in range(f.num_row_groups):
    t = f.read_row_group(
        g,
        columns=[
            "listing_id",
            "listing_type",
            "collected_at",
            "response_id",
            "raw_listing_json",
        ],
    ).to_pylist()
    for r in t:
        if r["listing_type"] != "rental" or not r["raw_listing_json"]:
            continue
        i = str(r["listing_id"])
        key = (r["collected_at"], r["response_id"] or "")
        la = latest.get(i)
        ac = active.get(i)
        if la is not None and key < la[0] and ac is not None and key < ac[0]:
            continue
        ad = json.loads(r["raw_listing_json"]) or {}
        d = ad.get("description")
        st = ad.get("status")
        if d is None:
            e = (key, -1, 0, 0, 0, None)
        else:
            s = WS.sub(" ", TAG.sub(" ", d)).strip()
            low = s.lower()
            strong = bool(STRONG.search(low))
            anyc = bool(ANY.search(low))
            bits = sum(1 << k for k, (n, p) in enumerate(RES.items()) if p.search(low))
            keep = len(s) < 40 or strong or (anyc and not (bits & 1))
            e = (key, len(s), int(strong), int(anyc), bits, s[:1500] if keep else None)
        if la is None or key >= la[0]:
            latest[i] = e
        if st == "ACTIVE" and (ac is None or key >= ac[0]):
            active[i] = e
    del t
    if g % 20 == 0:
        print(g, len(latest), flush=True)
rows = [
    (
        i,
        *(active[i][1:] if i in active else e[1:]),
        "last_active" if i in active else "latest",
    )
    for i, e in latest.items()
]
out = pd.DataFrame(
    rows, columns=["listing_id", "n", "strong", "anyc", "bits", "text", "record"]
)
out.to_parquet("texts_flags.parquet")
print(
    len(out),
    out.n.describe(),
    (out.n < 0).sum(),
    (out.n == 0).sum(),
    out.strong.sum(),
    out.text.notna().sum(),
)
print("bits order", list(RES))
