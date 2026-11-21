"""Every stored API record of the 120 picked ads (picks.csv in scratch), from the export the
ads file was built from, written to scratch records.parquet for blocks.py."""

import glob
import sys
from pathlib import Path

import pandas as pd
import pyarrow.compute as pc
import pyarrow.dataset as ds

S = Path(sys.argv[1])
ids = pd.read_csv(S / "picks.csv").listing_id.astype("int64").tolist()
files = sorted(
    glob.glob("/data1/apartments/archive/crawls/api/export/ads/run-*/*.parquet")
)
t = ds.dataset(files, format="parquet").to_table(
    filter=pc.field("listing_id").isin(ids)
)
df = t.to_pandas()
print(df.shape, df.listing_id.nunique())
df.to_parquet(S / "records.parquet")
