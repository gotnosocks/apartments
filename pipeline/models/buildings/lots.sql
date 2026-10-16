MODEL (
    name buildings.lots,
    kind FULL,
    grain building_id,
    audits (unique_values(columns := (building_id)), not_null(columns := (building_id, pluto_release))),
    description 'Each building with a record: its lot and BIN, the link they come from, and how well the city facts of its record fit MapPLUTO''s record of each candidate lot.'
);

-- Each building gets a lot from its address, in `buildings.pad_link`, and a lot from its map
-- point, in `buildings.footprint_link`. When the two differ, the city facts of the building's
-- record decide. StreetEasy shows the building class, the year built, the floor count and the
-- count of apartments mostly as city records give them for the lot it links, so its lot is
-- usually the one whose MapPLUTO record agrees with them most. A lot's fit counts the facts
-- its record in the latest MapPLUTO release shares with the building's record, from 0 to 4:
-- the class, the year, the floor count rounded down and the count of apartments. A fact
-- missing on either side counts as not shared, and so does a lot missing from MapPLUTO.
--
-- `link` says how the lot came about:
--
-- - `both`: the address and the map point give the same lot.
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
), pluto AS (
    SELECT try_cast(bbl AS DOUBLE)::BIGINT::VARCHAR AS bbl,
        nullif(trim(bldgclass), '') AS building_class,
        nullif(try_cast(yearbuilt AS INTEGER), 0) AS year_built,
        nullif(try_cast(numfloors AS DOUBLE), 0) AS floor_count,
        try_cast(unitsres AS INTEGER) AS residential_units
    FROM city.pluto
    WHERE release = (SELECT release FROM latest)
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
            AS footprint_fit
    FROM buildings.latest_record b
    LEFT JOIN buildings.pad_link a USING (building_id)
    LEFT JOIN buildings.footprint_link f USING (building_id)
    LEFT JOIN pluto pa ON pa.bbl = a.bbl
    LEFT JOIN pluto pf ON pf.bbl = f.bbl
), linked AS (
    SELECT *,
        CASE WHEN address_bbl IS NULL AND footprint_bbl IS NULL THEN NULL
            WHEN footprint_bbl IS NULL THEN 'address_only'
            WHEN address_bbl IS NULL THEN 'footprint_only'
            WHEN address_bbl = footprint_bbl THEN 'both'
            WHEN address_fit > footprint_fit THEN 'address'
            WHEN footprint_fit > address_fit THEN 'footprint'
            ELSE 'tie' END AS link
    FROM fits
)
SELECT building_id,
    CASE WHEN link IN ('footprint', 'footprint_only') THEN footprint_bbl ELSE address_bbl END
        AS bbl,
    CASE WHEN link IN ('footprint', 'footprint_only') THEN footprint_bin
        WHEN link = 'both' AND address_bin LIKE '_000000' THEN footprint_bin
        ELSE address_bin END AS bin,
    link, address_bbl, address_bin, address_rank, address_lots, address_fit,
    footprint_bbl, footprint_bin, footprint_inside, footprint_metres, footprint_fit,
    (SELECT release FROM latest) AS pluto_release
FROM linked
