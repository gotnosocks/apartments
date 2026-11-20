import pyarrow.parquet as pq

f = pq.ParquetFile(
    "/data1/apartments/pipeline/datasets/records-941f4a6588cbd8cc.parquet"
)
print(f.metadata.num_rows, f.num_row_groups, f.schema_arrow.names)
