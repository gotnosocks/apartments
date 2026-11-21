import pyarrow.parquet as pq

for p in [
    "/data1/apartments/tmp/commercial-sweep/marks.parquet",
    "/data1/apartments/tmp/po-thinlevel/l2_ads.parquet",
    "/data1/apartments/tmp/po-thinlevel/l2_rows_slim.parquet",
    "/data1/apartments/tmp/po-bldmodes/levels_live.parquet",
]:
    f = pq.ParquetFile(p)
    print(p.split("/")[-1], f.metadata.num_rows, f.schema_arrow.names)
