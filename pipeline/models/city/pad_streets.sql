MODEL (
    name city.pad_streets,
    kind VIEW,
    description 'Each PAD release''s street names (the street name dictionary, SND), a row for each of a street''s names, with every value as text.'
);

-- steps/city.py keeps each record of the dictionary whole, as `line`, and the view cuts it into
-- the fields of SND_metadata.pdf in PAD's zip, keeping their spaces. `b10sc` codes the street:
-- the borough, the 5-digit street code `sc5`, the local group `lgc` and the spelling `spv`.
-- PAD's address ranges carry the same codes. P in `primary_flag` marks a street's primary name,
-- and F in `principal_flag` its principal spelling.
--
-- The view leaves out the header record and the records of type S. A type S record gives a
-- name without its first word, such as `15 STREET` for both `EAST 15 STREET` and
-- `WEST 15 STREET`, and has fields of its own.
SELECT
    substr(line, 2, 1) AS boro,
    substr(line, 3, 32) AS stname,
    substr(line, 35, 1) AS primary_flag,
    substr(line, 36, 1) AS principal_flag,
    substr(line, 37, 11) AS b10sc,
    substr(line, 38, 5) AS sc5,
    substr(line, 43, 2) AS lgc,
    substr(line, 45, 3) AS spv,
    substr(line, 50, 1) AS numeric_ind,
    substr(line, 51, 1) AS gft,
    substr(line, 52, 2) AS len_full_name,
    substr(line, 54, 32) AS full_stname,
    substr(line, 88, 20) AS stn20,
    substr(line, 108, 1) AS ht_name_type_code,
    release, published, file, member, record, encoding
FROM read_parquet(@VAR('city_pad_streets'), union_by_name = true)
WHERE starts_with(line, '1') AND substr(line, 51, 1) <> 'S'
