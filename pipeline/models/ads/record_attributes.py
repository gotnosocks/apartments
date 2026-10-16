"""ads.record_attributes: each distinct API record's attributes and rental flags.

The build reads each record with `steps.attributes.project`, a Python copy of the current
chain's reading, in worker processes. It keeps the results in Parquet files beside the DuckDB
database, under `attributes/<code version>/`, and a later build parses only records missing
from those files. A top-up then parses just its new records, and a change to the projection code
starts a new folder. `config.py` computes the code version as a SHA-256 over the projection's
source files and passes it in the variable `attributes_code`, so a change to that code also
gives the model a new fingerprint.

The model's table holds a row for each distinct record of `raw.ads`: its SHA-256, the `id` in
the record, whether the chain would parse it, and each value as canonical JSON or NULL.
`PIPELINE_WORKERS` sets the number of worker processes, 4 unless set.
"""

import importlib
import multiprocessing
import os
import sys
import uuid
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from sqlglot import exp
from sqlmesh import ExecutionContext, model

KEYS = (
    "bedrooms",
    "bathrooms",
    "square_feet",
    "advertised_floor",
    "physical_floor",
    "floors_above_ground",
    "elevator",
    "laundry_type",
    "doorman_type",
    "hvac_type",
    "pet_policy",
    "view_exposures",
    "window_exposures",
    "furnished",
    "short_term",
    "concession",
)
# The build sends records to the workers in batches of BATCH and writes a cache file every
# FLUSH rows. A build cut short then keeps most of its parsed records.
BATCH = 500
FLUSH = 50_000


def cache_folder(cursor, code):
    database = cursor.execute(
        "SELECT path FROM duckdb_databases() WHERE database_name = current_database()"
    ).fetchone()[0]
    folder = Path(database).parent / "attributes" / code
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def write_cache(folder, rows):
    schema = pa.schema(
        [("record_sha256", pa.string()), ("id", pa.string()), ("parsed", pa.bool_())]
        + [(key, pa.string()) for key in KEYS]
    )
    columns = list(zip(*rows))
    table = pa.Table.from_arrays(
        [pa.array(column, type=field.type) for column, field in zip(columns, schema)],
        schema=schema,
    )
    name = f"{uuid.uuid4().hex}.parquet"
    pq.write_table(table, folder / f"{name}.part")
    os.replace(folder / f"{name}.part", folder / name)


@model(
    "ads.record_attributes",
    kind="FULL",
    columns={
        "record_sha256": "VARCHAR",
        "id": "VARCHAR",
        "parsed": "BOOLEAN",
        **{key: "VARCHAR" for key in KEYS},
    },
    grain="record_sha256",
    # SQLMesh turns an audit's string arguments into SQL strings, so the columns go in as
    # expressions.
    audits=[
        ("unique_values", {"columns": [exp.column("record_sha256")]}),
        ("not_null", {"columns": [exp.column("record_sha256"), exp.column("parsed")]}),
    ],
    description="Each distinct API record's attributes and rental flags, as the current chain reads them.",
)
def execute(context: ExecutionContext, start, end, execution_time, **kwargs):
    ads = context.resolve_table("raw.ads")
    code = context.var("attributes_code")
    cursor = context.engine_adapter.connection.cursor()
    folder = cache_folder(cursor, code)
    cached = (
        f"read_parquet('{folder}/*.parquet')" if any(folder.glob("*.parquet")) else None
    )
    # An answer for each record missing from the cache. The semi join keeps the picks in its
    # hash table and streams the records past it, since the records of a full export run to
    # tens of gigabytes. Should a response hold a record twice, both copies pass, and the
    # final query keeps one row for each record.
    missing = f"""
        WITH picks AS (
            SELECT record_sha256, min(response_id) AS response_id
            FROM {ads} WHERE outcome = 'record'
            {f"AND record_sha256 NOT IN (SELECT record_sha256 FROM {cached})" if cached else ""}
            GROUP BY record_sha256
        )
        SELECT a.record_sha256, a.record
        FROM {ads} a SEMI JOIN picks p
            ON a.record_sha256 = p.record_sha256 AND a.response_id = p.response_id
        WHERE a.outcome = 'record'
    """
    # Worker processes start with the parent's sys.path.
    for path in context.var("pythonpath").split(os.pathsep):
        if path not in sys.path:
            sys.path.append(path)
    attributes = importlib.import_module("steps.attributes")
    if tuple(attributes.KEYS) != KEYS:
        raise ValueError("steps.attributes.KEYS differs from the model's columns")
    reader = cursor.execute(missing).to_arrow_reader(BATCH)
    workers = int(os.environ.get("PIPELINE_WORKERS", "4"))
    pending, rows = [], []
    with ProcessPoolExecutor(
        workers, mp_context=multiprocessing.get_context("spawn")
    ) as pool:
        for batch in reader:
            pairs = list(
                zip(
                    batch.column("record_sha256").to_pylist(),
                    batch.column("record").to_pylist(),
                )
            )
            pending.append(pool.submit(attributes.project_batch, pairs))
            # At most two batches per worker wait, to bound memory.
            while len(pending) > 2 * workers:
                rows.extend(pending.pop(0).result())
            if len(rows) >= FLUSH:
                write_cache(folder, rows)
                rows = []
        for future in pending:
            rows.extend(future.result())
    if rows:
        write_cache(folder, rows)
    if not any(folder.glob("*.parquet")):
        return
    out = cursor.execute(
        f"""SELECT DISTINCT ON (c.record_sha256) c.* FROM read_parquet('{folder}/*.parquet') c
        WHERE c.record_sha256 IN (SELECT record_sha256 FROM {ads} WHERE outcome = 'record')"""
    ).to_arrow_reader(FLUSH)
    for batch in out:
        yield batch.to_pandas()
