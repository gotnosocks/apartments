MODEL (
    name buildings.lots,
    kind FULL,
    grain building_id,
    audits (unique_values(columns := (building_id)), not_null(columns := (building_id, pluto_release))),
    description 'Each building with a record: its lot and BIN, the link they come from, and how well the city facts of its record fit MapPLUTO''s record of each candidate lot.'
);

-- Each building gets a lot from its address, in `buildings.pad_link`, and a lot from its map
-- point, in `buildings.footprint_link`. When the two differ, and the latest MapPLUTO release gives
-- one of them apartments and the other a count of 0, the step takes the one with apartments:
-- StreetEasy lists apartments, and HPD's register of residential buildings agreed with the lot
-- with apartments in 114 of the 118 buildings where it named one of the two lots, as
-- docs/data/pipeline.md describes under Building identity. The step keeps the address's lot
-- instead when the building on it came down: the map point then often falls next door. It
-- checks for that in MapPLUTO's last record of the address's lot with apartments, from an earlier
-- release. When that record fits the building's record better than the footprint's lot does,
-- and the map point lies outside the footprint, the step keeps the address's lot. On a tie, as
-- for twin row houses, it takes the standing building.
-- Otherwise, as for a lot missing from
-- MapPLUTO or one without a count, the city facts of the building's record decide. StreetEasy
-- shows the building class, the year built, the floor count and the count of apartments mostly as
-- city records give them for the lot it links, so its lot is usually the one whose MapPLUTO record
-- agrees with them most. A lot's fit counts the facts its record in the latest MapPLUTO release
-- shares with the building's record, from 0 to 4: the class, the year, the floor count rounded
-- down and the count of apartments. A fact missing on either side counts as not shared, and so
-- does a lot missing from MapPLUTO.
--
-- `link` says how the lot came about:
--
-- - `both`: the address and the map point give the same lot.
-- - `address_apartments`, `footprint_apartments`: they give different lots, the named one has
--   apartments, and the other has a count of 0.
-- - `address_demolished`: the address's lot has a count of 0 and the footprint's lot apartments,
--   but the address's last record with apartments fits better than the footprint's lot, and the
--   map point lies outside the footprint.
-- - `address`, `footprint`: they give different lots, and the named one fits better.
-- - `tie`: they give different lots that fit equally well, and the step takes the address's.
-- - `address_only`: the map point falls in no footprint and lies more than 10 m from any.
-- - `footprint_only`: the address finds no PAD range.
--
-- A building with neither has no lot and no `link`. Reviewers judged a sample of each class
-- against MapPLUTO's records, as docs/data/pipeline.md describes under Building identity,
-- and the rate of wrong lots differs a lot between classes.
--
-- The BIN comes with the lot. Where the lot comes from the address, the BIN is PAD's for the
-- address range, unless PAD gives the lot a BIN such as 1000000, which stands for no numbered
-- building, and the footprint on the same lot gives a numbered one.
WITH latest AS (
    SELECT arg_max(release, published) AS release FROM city.pluto
), records AS (
    SELECT try_cast(bbl AS DOUBLE)::BIGINT::VARCHAR AS bbl, release, published,
        nullif(trim(bldgclass), '') AS building_class,
        nullif(try_cast(yearbuilt AS INTEGER), 0) AS year_built,
        nullif(try_cast(numfloors AS DOUBLE), 0) AS floor_count,
        try_cast(unitsres AS INTEGER) AS residential_units
    FROM city.pluto
), pluto AS (
    SELECT * FROM records WHERE release = (SELECT release FROM latest)
), earlier AS (
    SELECT bbl, arg_max({'building_class': building_class, 'year_built': year_built,
        'floor_count': floor_count, 'residential_units': residential_units}, published) AS facts
    FROM records
    WHERE residential_units > 0
    GROUP BY bbl
), fits AS (
    SELECT b.building_id,
        a.bbl AS address_bbl, a.bin AS address_bin, a.rank AS address_rank,
        a.lots AS address_lots, f.bbl AS footprint_bbl, f.bin AS footprint_bin,
        f.inside AS footprint_inside, f.metres AS footprint_metres,
        CASE WHEN a.bbl IS NOT NULL THEN
            coalesce((pa.building_class = b.building_class)::INTEGER, 0)
            + coalesce((pa.year_built = b.year_built)::INTEGER, 0)
            + coalesce((floor(pa.floor_count) = floor(b.floor_count))::INTEGER, 0)
            + coalesce((pa.residential_units = b.residential_units)::INTEGER, 0) END AS address_fit,
        CASE WHEN f.bbl IS NOT NULL THEN
            coalesce((pf.building_class = b.building_class)::INTEGER, 0)
            + coalesce((pf.year_built = b.year_built)::INTEGER, 0)
            + coalesce((floor(pf.floor_count) = floor(b.floor_count))::INTEGER, 0)
            + coalesce((pf.residential_units = b.residential_units)::INTEGER, 0) END
            AS footprint_fit,
        CASE WHEN ea.bbl IS NOT NULL THEN
            coalesce((ea.facts.building_class = b.building_class)::INTEGER, 0)
            + coalesce((ea.facts.year_built = b.year_built)::INTEGER, 0)
            + coalesce((floor(ea.facts.floor_count) = floor(b.floor_count))::INTEGER, 0)
            + coalesce((ea.facts.residential_units = b.residential_units)::INTEGER, 0) END
            AS address_earlier_fit,
        pa.residential_units AS address_units, pf.residential_units AS footprint_units
    FROM buildings.latest_record b
    LEFT JOIN buildings.pad_link a USING (building_id)
    LEFT JOIN buildings.footprint_link f USING (building_id)
    LEFT JOIN pluto pa ON pa.bbl = a.bbl
    LEFT JOIN pluto pf ON pf.bbl = f.bbl
    LEFT JOIN earlier ea ON ea.bbl = a.bbl
), linked AS (
    SELECT *,
        CASE WHEN address_bbl IS NULL AND footprint_bbl IS NULL THEN NULL
            WHEN footprint_bbl IS NULL THEN 'address_only'
            WHEN address_bbl IS NULL THEN 'footprint_only'
            WHEN address_bbl = footprint_bbl THEN 'both'
            WHEN address_units > 0 AND footprint_units = 0 THEN 'address_apartments'
            WHEN footprint_units > 0 AND address_units = 0 AND address_earlier_fit > footprint_fit
                AND NOT footprint_inside THEN 'address_demolished'
            WHEN footprint_units > 0 AND address_units = 0 THEN 'footprint_apartments'
            WHEN address_fit > footprint_fit THEN 'address'
            WHEN footprint_fit > address_fit THEN 'footprint'
            ELSE 'tie' END AS link
    FROM fits
)
SELECT building_id,
    CASE WHEN link IN ('footprint', 'footprint_apartments', 'footprint_only') THEN footprint_bbl
        ELSE address_bbl END AS bbl,
    CASE WHEN link IN ('footprint', 'footprint_apartments', 'footprint_only') THEN footprint_bin
        WHEN link = 'both' AND address_bin LIKE '_000000' THEN footprint_bin
        ELSE address_bin END AS bin,
    link, address_bbl, address_bin, address_rank, address_lots, address_fit,
    footprint_bbl, footprint_bin, footprint_inside, footprint_metres, footprint_fit,
    (SELECT release FROM latest) AS pluto_release
FROM linked
