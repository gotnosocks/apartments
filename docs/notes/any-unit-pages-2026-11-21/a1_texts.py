"""Every record's text and unit label from the records file of the pipeline dataset.

The dataset `ads-14f9e88d75290a0f.parquet` was built with `records-0d20eb92b9f08c7d.parquet`
(its catalog entry). This pass writes one row per record (listing id, collection time,
status, displayed unit label, description) to scratch, row group by row group. `a2_ads.py`
keeps one text per listing, the last ACTIVE record's, as `descriptions.record_descriptions`
does. No ask is read.
"""

import json

import pyarrow as pa
import pyarrow.parquet as pq

REC = "/data1/apartments/pipeline/datasets/records-0d20eb92b9f08c7d.parquet"
OUT = "/data1/apartments/tmp/any-unit/rec_texts.parquet"
SCHEMA = pa.schema(
    [
        ("listing_id", pa.string()),
        ("collected_at", pa.float64()),
        ("status", pa.string()),
        ("label", pa.string()),
        ("description", pa.string()),
    ]
)

f = pq.ParquetFile(REC)
w = pq.ParquetWriter(OUT, SCHEMA, compression="zstd")
n = 0
for g in range(f.metadata.num_row_groups):
    t = f.read_row_group(g, columns=["listing_id", "collected_at", "raw_listing_json"])
    st, lab, desc = [], [], []
    for s in t.column("raw_listing_json").to_pylist():
        j = (json.loads(s) or {}) if s else {}
        st.append(j.get("status"))
        ad = (j.get("propertyDetails") or {}).get("address") or {}
        lab.append(ad.get("displayUnit") or ad.get("unit"))
        desc.append(j.get("description"))
    ca = t.column("collected_at").cast(pa.float64())
    out = pa.table(
        [
            t.column("listing_id").cast(pa.string()),
            ca,
            pa.array(st, pa.string()),
            pa.array(lab, pa.string()),
            pa.array(desc, pa.string()),
        ],
        schema=SCHEMA,
    )
    w.write_table(out)
    n += out.num_rows
    if g % 20 == 0:
        print("group", g, n, flush=True)
w.close()
print("records", n)
