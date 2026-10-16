MODEL (
    name raw.buildings,
    kind VIEW,
    description 'API answers for buildings, as the scraper exported them: a row for each stored answer.'
);

-- The file list and the version come from export/manifest.ndjson by way of config.py, as for
-- raw.ads.
SELECT *, @VAR('buildings_version') AS export_version
FROM read_parquet(@VAR('buildings'))
