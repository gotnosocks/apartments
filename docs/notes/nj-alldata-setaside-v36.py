"""Copy a B0 dataset, setting aside the rows quarantine-v36 adds over v35 (the read NJ ads)."""

import hashlib, json, shutil, sys
from pathlib import Path
import pandas as pd

src, out, rule = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
out.mkdir()
lines = [json.loads(l) for l in rule.read_text().splitlines() if l.strip()]
v35 = {
    json.loads(l)["source_listing_id"]
    for l in Path(sys.argv[4]).read_text().splitlines()
    if l.strip()
}
ids = {r["source_listing_id"] for r in lines} - v35
rows = pd.read_parquet(src / "rows.parquet")
drop = rows.audit_id.astype(str).isin(ids)
rows[~drop].to_parquet(out / "rows.parquet", index=False)
rows[drop].to_parquet(out / "set_aside.parquet", index=False)
m = json.loads((src / "manifest.json").read_text())
m["rows"] = int((~drop).sum())
m["rows_sha256"] = hashlib.sha256((out / "rows.parquet").read_bytes()).hexdigest()
m["latest_day_how"] = (
    rows[~drop].latest_day_how.value_counts().to_dict()
    if "latest_day_how" in rows
    else m.get("latest_day_how")
)
m["quarantine"] = {
    "source": str(src),
    "source_rows_sha256": json.loads((src / "manifest.json").read_text())[
        "rows_sha256"
    ],
    "rule": str(rule),
    "rule_sha256": hashlib.sha256(rule.read_bytes()).hexdigest(),
    "listings_in_rule_not_v35": len(ids),
    "set_aside": int(drop.sum()),
}
(out / "manifest.json").write_text(json.dumps(m, indent=2) + "\n")
print(json.dumps(m["quarantine"], indent=2))
