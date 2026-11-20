"""Check every `Ad text:` quote of candidate_rows.ndjson against the stored ad texts.

Reads candidate_rows.ndjson beside this script and `texts.txt` from the read's working directory
(/data1/apartments/tmp/po-bldmodes; not committed, it holds full ad texts). Ads with identical
text are printed once in texts.txt ("same text as"), so a quote is looked up on the first of them.
Prints the quotes that do not occur, ignoring case, spacing, HTML entities and the "..." gaps.
"""

import html
import json
import re
from pathlib import Path

HERE = Path(__file__).parent
text = Path("/data1/apartments/tmp/po-bldmodes/texts.txt").read_text()
per, same = {}, {}
last = None
for line in text.splitlines():
    m = re.match(r"- (\d+) .*?(?:\[same text as (\d+)\])?$", line)
    if line.startswith("- ") and m:
        last = int(m.group(1))
        s = re.search(r"\[same text as (\d+)\]", line)
        if s:
            same[last] = int(s.group(1))
    elif line.startswith("  TEXT: ") and last is not None:
        per[last] = line[8:]
    elif last in per and not line.startswith("## "):
        per[last] += " " + line
per = {
    k: re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", v))).lower()
    for k, v in per.items()
}
rows = [
    json.loads(line)
    for line in (HERE / "candidate_rows.ndjson").read_text().splitlines()
]
bad = 0
for r in rows:
    for e in r["evidence"]:
        if e["kind"] != "ad_text":
            continue
        i = int(r["listing_id"])
        t = per.get(same.get(i, i))
        for part in e["quote"].removeprefix("Ad text: ").split("..."):
            part = re.sub(r"\s+", " ", part.strip()).lower()
            if t is None or part not in t:
                bad += 1
                print("MISSING", i, repr(part))
print(len(rows), "rows,", bad, "quotes not found")
