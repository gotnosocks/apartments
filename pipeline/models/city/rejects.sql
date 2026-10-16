MODEL (
    name city.rejects,
    kind VIEW,
    description 'Each row of the city archive that DuckDB refused as it read the CSV, with its line in the member, the reason and the row''s text.'
);

-- steps/city.py writes a file of these rows for each file of the archive, and config.py lists
-- them. DuckDB gives a row here for each missing or extra value, so a refused row with two
-- missing values appears twice.
SELECT * FROM read_parquet(@VAR('city_rejects'), union_by_name = true)
