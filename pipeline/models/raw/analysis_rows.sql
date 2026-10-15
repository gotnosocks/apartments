MODEL (
    name raw.analysis_rows,
    kind VIEW,
    description 'Analysis rows of the current chain, a row for each advertised price, numbered in rentfrontier.latest_ask''s reading order.'
);

SELECT *, @VAR('rows_version') AS rows_version
FROM read_parquet(@VAR('rows'))
