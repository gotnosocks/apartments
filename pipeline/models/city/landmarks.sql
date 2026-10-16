MODEL (
    name city.landmarks,
    kind VIEW,
    description 'Each copy of LPC''s individual landmarks and historic district buildings (ncre-qhxs), a row for each, with every value as text.'
);

-- steps/city.py writes the files, and config.py lists them. `release`, `published`, `file`,
-- `member` and `record` give each row's place in the city archive.
SELECT * FROM read_parquet(@VAR('city_landmarks'), union_by_name = true)
