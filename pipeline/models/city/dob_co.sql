MODEL (
    name city.dob_co,
    kind VIEW,
    description 'Each copy of the earlier DOB certificates of occupancy (bs8b-p36w), a row for each certificate, with every value as text.'
);

-- steps/city.py writes the files, and config.py lists them. `release`, `published`, `file`,
-- `member` and `record` give each row's place in the city archive.
SELECT * FROM read_parquet(@VAR('city_dob_co'), union_by_name = true)
