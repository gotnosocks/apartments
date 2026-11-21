import sys

sys.path.insert(0, "/data1/apartments/tmp/pi-review/wt-commercial-sweep/pipeline")
from pathlib import Path
from models.ledger import entries

r = entries.read(
    [
        Path(
            "/data1/apartments/tmp/pi-review/wt-commercial-sweep/docs/notes/commercial-sweep-2026-11-20/candidate_rows.ndjson"
        )
    ]
)
print("read ok", len(r))
