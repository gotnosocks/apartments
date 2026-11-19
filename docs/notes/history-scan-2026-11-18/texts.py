import numpy as np
from rentfrontier import api_records, descriptions

s = np.load(
    "/data1/apartments/frontier/runs/drift-building-b0-latest-67d14e17-b9/pred_scores.npz"
)
ids = set(str(x) for x in s["listing"])
records = api_records.records_file()
print("records", records["path"], "wanted", len(ids), flush=True)
t = descriptions.record_descriptions(records, ids)
t.rename_axis("listing_id").reset_index().to_parquet(
    "/data1/apartments/tmp/history-scan/texts-b9.parquet"
)
print(
    "wrote",
    len(t),
    "with text",
    t.description.notna().sum(),
    t.record.value_counts().to_dict(),
)
