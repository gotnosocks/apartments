import json, sys
from pathlib import Path
import pyarrow.parquet as pq
from rentfrontier import run as R, drift_score

for n in ["6cd1f12b-range-m3", "d9028c57-range-j"]:
    d = [p for p in R.RUNS.iterdir() if n in p.name and (p / "posterior.npz").exists()][
        0
    ]
    ds = drift_score.dataset_dir(d)
    rec = json.loads((d / "result.json").read_text())
    print(d, ds)
    print(
        {
            k: (v if not isinstance(v, (dict, list)) else type(v).__name__)
            for k, v in rec.items()
        }
    )
    s = pq.read_schema(ds / "rows.parquet")
    print(pq.ParquetFile(ds / "rows.parquet").metadata.num_rows, s.names)
    print(open(ds / "manifest.json").read()[:1500])
