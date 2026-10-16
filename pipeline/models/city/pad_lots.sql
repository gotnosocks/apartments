MODEL (
    name city.pad_lots,
    kind VIEW,
    description 'Each PAD release''s lots (bobabbl), a row for each lot, with every value as text.'
);

-- steps/city.py writes the files, and config.py lists them. `release`, `published`, `file`,
-- `member` and `record` give each row's place in the city archive.
SELECT * FROM read_parquet(@VAR('city_pad_lots'), union_by_name = true)
