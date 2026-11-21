import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "pipeline"))
from models.ledger import entries  # noqa: E402

r = entries.read([HERE / "candidate_rows.ndjson"])
print("read ok", len(r))
