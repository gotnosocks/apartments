MODEL (
    name ads.reported,
    kind CUSTOM (
        materialization 'merge',
        materialization_properties (changes = 'ads.touched', replace = 'listing_id')
    ),
    grain listing_id,
    audits (unique_values(columns := (listing_id)), not_null(columns := (listing_id, records))),
    description 'Each ad with a record, with the floor its unit label reads and its full and half bathrooms, where all its records agree.'
);

-- `rentfrontier.cohort` reads three values from each of an ad's records: the unit label in
-- propertyDetails.address.displayUnit, fullBathroomCount and halfBathroomCount. This model
-- reads them from every record answer of the ad, as the chain does, so a record with another
-- ad's `id` counts here too.
--
-- `label_floor` is the floor all the ad's labels read, under `label_floor` of the chain. The
-- chain strips the label's whitespace, drops a leading '#', strips it again and puts it in upper
-- case. Then it tries five rules, each on the whole label:
--   1. one or two digits and a letter, as in 4D;
--   2. three or four digits, read as hundreds, as in 1205 for the 12th floor;
--   3. N or S, one or two digits and a letter, as in N3A;
--   4. one or two digits and a front or rear suffix, as in 5RE;
--   5. one or two digits, an ordinal suffix and FL or FLOOR, as in 3RDFL.
-- Each rule but the second reads the label's digits as the floor. An ad gets no floor when a
-- record has no label, when a label matches no rule, or when two labels read different floors.
-- The whitespace class below lists the characters Python's `str.isspace` accepts. The chain
-- puts a label in upper case with Python's `str.upper`. It differs from DuckDB's `upper` only
-- outside ASCII, and the labels of runs 1 to 5 hold only printable ASCII.
--
-- `full_baths` and `half_baths` follow `consensus` of the chain: a count stands when every record
-- gives the same whole number of zero or more, and a boolean doesn't count as a number.
--
-- The model reads the ads in ads.touched: every ad in a full build, and in a top-up build the ads
-- the new answers change. A top-up's materialization `merge` replaces those ads' rows in a copy of
-- the previous build's table.
WITH records AS (
    -- One parse of each record, for its three values as JSON.
    SELECT listing_id::VARCHAR AS listing_id,
        json_extract(record, [
            '$.propertyDetails.address.displayUnit',
            '$.propertyDetails.fullBathroomCount',
            '$.propertyDetails.halfBathroomCount'
        ]) AS f
    FROM raw.ads
    WHERE outcome = 'record' AND listing_id::VARCHAR IN (SELECT listing_id FROM ads.touched)
),
fields AS (
    SELECT listing_id,
        CASE WHEN json_type(f[1]) = 'VARCHAR'
            THEN upper(regexp_replace(
                f[1] ->> '$',
                '^[\x{09}-\x{0D}\x{1C}-\x{20}\x{85}\x{A0}\x{1680}\x{2000}-\x{200A}\x{2028}\x{2029}\x{202F}\x{205F}\x{3000}]*#?[\x{09}-\x{0D}\x{1C}-\x{20}\x{85}\x{A0}\x{1680}\x{2000}-\x{200A}\x{2028}\x{2029}\x{202F}\x{205F}\x{3000}]*|[\x{09}-\x{0D}\x{1C}-\x{20}\x{85}\x{A0}\x{1680}\x{2000}-\x{200A}\x{2028}\x{2029}\x{202F}\x{205F}\x{3000}]+$',
                '', 'g')) END AS label,
        CASE WHEN json_type(f[2]) IN ('UBIGINT', 'BIGINT', 'DOUBLE') THEN (f[2] ->> '$')::DOUBLE END AS full_baths,
        CASE WHEN json_type(f[3]) IN ('UBIGINT', 'BIGINT', 'DOUBLE') THEN (f[3] ->> '$')::DOUBLE END AS half_baths
    FROM records
),
read AS (
    SELECT listing_id,
        CASE
            WHEN regexp_full_match(label, '[1-9][0-9]{2,3}') THEN label::INTEGER // 100
            WHEN regexp_full_match(label, '[1-9][0-9]?[A-Z]')
                OR regexp_full_match(label, '[NS][1-9][0-9]?[A-Z]')
                OR regexp_full_match(label, '[1-9][0-9]?(FE|FW|RE|RW|FR|RR|FF|RF)')
                OR regexp_full_match(label, '[1-9][0-9]?(ST|ND|RD|TH)(FL|FLOOR)')
                THEN regexp_extract(label, '[0-9]+')::INTEGER
        END AS label_floor,
        CASE WHEN full_baths >= 0 AND full_baths % 1 = 0 THEN full_baths END AS full_baths,
        CASE WHEN half_baths >= 0 AND half_baths % 1 = 0 THEN half_baths END AS half_baths
    FROM fields
)
SELECT listing_id, count(*) AS records,
    CASE WHEN count(label_floor) = count(*) AND count(DISTINCT label_floor) = 1
        THEN min(label_floor) END AS label_floor,
    CASE WHEN count(full_baths) = count(*) AND count(DISTINCT full_baths) = 1
        THEN min(full_baths)::BIGINT END AS full_baths,
    CASE WHEN count(half_baths) = count(*) AND count(DISTINCT half_baths) = 1
        THEN min(half_baths)::BIGINT END AS half_baths
FROM read
GROUP BY listing_id
