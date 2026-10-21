Scripts for `../residual-screen-2026-10-21.md`, run in this order from `/data1/apartments/tmp/resid`
with the bridge-frontier venv and `PYTHONPATH=frontier/src`:

1. `resid.py` writes each training row's error, building effect and map value from the frontage run.
2. `pipefields.py`, `extra.py`, `extract.py` then `raw2.py`, `bldfields.py`, `extract_text.py`,
   `traffic.py` then `traffic_rows.py` write the candidate fields, one row per ad.
3. `screen2.py FIELD_FILES...` scores each field alone and writes `joined.parquet`.
4. `joint.py all` and `joint.py physical` fit the joint OLS on a 600,000-row sample.
