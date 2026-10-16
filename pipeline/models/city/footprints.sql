MODEL (
    name city.footprints,
    kind VIEW,
    description 'Each copy of the building footprints (5zhs-2jue), a row for each footprint, with every value as text.'
);

-- steps/city.py writes the files, and config.py lists them. `release`, `published`, `file`,
-- `member` and `record` give each row's place in the city archive.
SELECT * FROM read_parquet(@VAR('city_footprints'), union_by_name = true)
