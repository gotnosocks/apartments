MODEL (
    name city.pluto,
    kind VIEW,
    description 'Each MapPLUTO release, a row for each lot, with every value as text.'
);

-- steps/city.py writes the files, and config.py lists them. `release`, `published`, `file`,
-- `member` and `record` give each row's place in the city archive.
SELECT * FROM read_parquet(@VAR('city_pluto'), union_by_name = true)
