MODEL (
    name analysis.building_check,
    kind FULL,
    grain listing_id,
    audits (
        unique_values(columns := (listing_id)),
        not_null(columns := (listing_id, reasons, bbl, pluto_release))
    ),
    description 'Each fit-ready row whose lot''s MapPLUTO record rules out the ad''s building: a floor more than one floor and 30% above the lot''s floor count, or a lot with no apartments and a land use from industrial to vacant, for review.'
);

-- The city check in docs/data/pipeline.md read a sample of rows whose lot disagreed with the ad,
-- and in some of them the matcher had put the ad on the wrong building. This model lists the
-- rows where the lot's record leaves no room for the ad, so that a reader can move the ad through
-- the unit ledger, or exclude it or take its lot away through the corrections ledger.
--
-- The model reads each row's lot from analysis.lot_facts, with its facts as of the ad's first
-- day, and the same lot's record in the latest release from buildings.lot_releases. A reason
-- needs both records to agree, since a lot can gain floors or apartments between releases.
--
--   floor_above_lot:  the ad's floor, from its advertised floor, its physical floor or its unit
--       label in that order, lies more than one floor and more than 30% above the lot's floor
--       count. The floor of slack covers a basement, a penthouse or a mezzanine that MapPLUTO
--       counts differently. The 30% covers towers that number their floors past their story
--       count, skipping the 13th floor and the mechanical floors. On whole floors it changes the
--       cut only on lots of seven floors or more. The lot holds a single building, since
--       MapPLUTO counts the floors of the tallest one, and StreetEasy's own floor count for the
--       building, when it gives one, also lies below the floor. A latest record with a floor
--       count of 0 leaves the dated count to decide.
--   zero_unit_lot:  both records give the lot no apartments and a land use from industrial to
--       vacant, codes 06 to 11. Codes 01 to 05 are the residential uses, mixed residential and
--       commercial use, and commercial and office buildings. The ads place at most three units
--       in the building, DOB has issued no certificate of occupancy with apartments on its BIN
--       by the ad's first day, and no certificate of a new building. A lot with a new building
--       or a conversion gains apartments in DOB's records before MapPLUTO's. A row without a
--       BIN has no certificates to read, so only the lot's records and the ads decide.
--
-- When the latest release has no record of the lot, the dated record decides alone.
--
-- A reader's labels of the listed lots found a floor misread from the ad or its unit label, or a
-- lot record behind its building, in about a fifth of them. Those rows belong to the right
-- building, so analysis.rows keeps every row the model lists, and analysis.ads gives the reasons
-- in its building_check column.
WITH units AS (
    SELECT building_id, count(DISTINCT unit_id) AS ad_units
    FROM ads.placed
    GROUP BY building_id
),
facts AS (
    SELECT r.listing_id, f.bbl, f.pluto_release,
        coalesce(r.advertised_floor, r.physical_floor, r.label_derived_floor) AS floor,
        r.building_floor_count, u.ad_units,
        f.numfloors, f.numbldgs, f.unitsres, f.landuse, f.bldgclass,
        t.numfloors AS latest_numfloors, t.numbldgs AS latest_numbldgs,
        t.unitsres AS latest_unitsres, t.landuse AS latest_landuse,
        c.units AS certificate_units, c.new_building
    FROM analysis.rows r
    JOIN analysis.lot_facts f USING (listing_id)
    JOIN buildings.lots l ON l.building_id = r.building_id
    LEFT JOIN buildings.lot_releases t ON t.bbl = f.bbl AND t.release = l.pluto_release
    LEFT JOIN units u ON u.building_id = r.building_id
    LEFT JOIN analysis.building_certificates c USING (listing_id)
),
reasons AS (
    SELECT *,
        list_filter(
            [
                CASE WHEN floor > greatest(numfloors + 1, 1.3 * numfloors) AND numfloors > 0
                    AND floor > greatest(
                        coalesce(nullif(latest_numfloors, 0), numfloors) + 1,
                        1.3 * coalesce(nullif(latest_numfloors, 0), numfloors)
                    )
                    AND numbldgs = 1 AND coalesce(latest_numbldgs, 1) = 1
                    AND floor > coalesce(building_floor_count, 0)
                    THEN 'floor_above_lot' END,
                CASE WHEN unitsres = 0 AND coalesce(latest_unitsres, 0) = 0
                    AND landuse BETWEEN 6 AND 11
                    AND coalesce(latest_landuse BETWEEN 6 AND 11, true)
                    AND ad_units <= 3
                    AND NOT coalesce(certificate_units > 0, false)
                    AND NOT coalesce(new_building, false)
                    THEN 'zero_unit_lot' END
            ],
            x -> x IS NOT NULL
        ) AS reasons
    FROM facts
)
SELECT listing_id, reasons, bbl, pluto_release, floor, building_floor_count, numfloors,
    latest_numfloors, unitsres, latest_unitsres, landuse, bldgclass, ad_units
FROM reasons
WHERE len(reasons) > 0
