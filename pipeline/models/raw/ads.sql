MODEL (
    name raw.ads,
    kind VIEW,
    description 'API answers for ads, as the scraper exported them: a row for each stored answer.'
);

-- The file list and the version come from export/manifest.ndjson by way of config.py. A new
-- file changes both, so SQLMesh rebuilds every model below this view.
SELECT *, @VAR('ads_version') AS export_version
FROM read_parquet(@VAR('ads'))
