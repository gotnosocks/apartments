MODEL (
    name city.pad_addresses,
    kind VIEW,
    description 'Each PAD release''s address ranges (bobaadr), a row for each range, with every value as text.'
);

-- steps/city.py writes the files, and config.py lists them. `release`, `published`, `file`,
-- `member` and `record` give each row's place in the city archive.
SELECT * FROM read_parquet(@VAR('city_pad_addresses'), union_by_name = true)
