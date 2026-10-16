MODEL (
    name buildings.lot_releases,
    kind FULL,
    grain (bbl, release),
    audits (
        unique_combination_of_columns(columns := (bbl, release)),
        not_null(columns := (bbl, release))
    ),
    description 'Each lot of buildings.lots in each MapPLUTO release, with its facts as the release gives them, typed.'
);

-- A whole number from its text, or missing for a blank.
@DEF(
    whole,
    v -> CAST(
        CASE WHEN nullif(trim(v), '')::DOUBLE % 1 = 0 THEN nullif(trim(v), '')::DOUBLE
            WHEN nullif(trim(v), '') IS NOT NULL
                THEN error('fraction ' || v || ' on lot ' || r.bbl || ' in ' || r.release)
            END AS INTEGER
    )
);

-- The step reads every MapPLUTO release in `city.pluto` and keeps the records of the buildings'
-- lots, as `buildings.lots` gives them. Releases spell the same value in several ways, such as
-- `01` and `1` for a land use code, `2.50` and `2.5` for a ratio, and a lot number with or
-- without decimals. The step casts each fact to its type, so a fact compares equal across
-- releases when the city recorded the same value:
--
-- - whole numbers for the years, the counts and the codes,
-- - decimals for the areas, the floor count, the lot and building sizes, the floor area ratios
--   and the coordinates, since a few lot and building areas carry fractions,
-- - true or false for `irrlotcode`, which releases write as Y or N,
-- - text for the address, the building class, the zoning district and the landmark and historic
--   district names.
--
-- A blank reads as missing. A zero stays a zero, as the city writes it: MapPLUTO gives 0 for an
-- unknown year built and for a lot without an alteration. The flood zone flags are 1 for a lot
-- in the zone and blank otherwise. These values stop the build, so a change in a release's
-- spelling shows up here rather than as a missing fact:
--
-- - a value that isn't a number where the field holds numbers,
-- - a fraction where the field holds whole numbers,
-- - an `irrlotcode` other than Y or N.
--
-- Older releases leave fields out. Releases 09v1 to 12v2 have no `residfar`, no flood zone flags
-- and no coordinates, 13v1 to 16v2 have no flags and no coordinates, and 17v1 to 19v2 have no
-- coordinates. Their records give those fields as missing. `city.pluto_releases` lists the
-- fields each release carries, and `analysis.lot_facts` takes the others from the latest
-- release. Release 22v2 has no published date in the archive's manifest, and
-- `analysis.lot_facts` never reads it.
WITH lots AS (
    SELECT DISTINCT bbl FROM buildings.lots WHERE bbl IS NOT NULL
), records AS (
    SELECT p.* REPLACE (try_cast(p.bbl AS DOUBLE)::BIGINT::VARCHAR AS bbl)
    FROM city.pluto p
)
SELECT r.bbl, r.release, r.published,
    nullif(trim(r.address), '') AS address,
    @whole(r.yearbuilt) AS yearbuilt,
    @whole(r.yearalter1) AS yearalter1,
    @whole(r.yearalter2) AS yearalter2,
    nullif(trim(r.numfloors), '')::DOUBLE AS numfloors,
    @whole(r.numbldgs) AS numbldgs,
    @whole(r.unitsres) AS unitsres,
    @whole(r.unitstotal) AS unitstotal,
    nullif(trim(r.lotarea), '')::DOUBLE AS lotarea,
    nullif(trim(r.bldgarea), '')::DOUBLE AS bldgarea,
    nullif(trim(r.resarea), '')::DOUBLE AS resarea,
    nullif(trim(r.comarea), '')::DOUBLE AS comarea,
    nullif(trim(r.retailarea), '')::DOUBLE AS retailarea,
    nullif(trim(r.lotfront), '')::DOUBLE AS lotfront,
    nullif(trim(r.lotdepth), '')::DOUBLE AS lotdepth,
    nullif(trim(r.bldgfront), '')::DOUBLE AS bldgfront,
    nullif(trim(r.bldgdepth), '')::DOUBLE AS bldgdepth,
    nullif(trim(r.bldgclass), '') AS bldgclass,
    @whole(r.landuse) AS landuse,
    nullif(trim(r.landmark), '') AS landmark,
    nullif(trim(r.histdist), '') AS histdist,
    nullif(trim(r.zonedist1), '') AS zonedist1,
    nullif(trim(r.builtfar), '')::DOUBLE AS builtfar,
    nullif(trim(r.residfar), '')::DOUBLE AS residfar,
    @whole(r.proxcode) AS proxcode,
    CASE WHEN nullif(trim(r.irrlotcode), '') IS NULL THEN NULL
        WHEN upper(trim(r.irrlotcode)) = 'Y' THEN true
        WHEN upper(trim(r.irrlotcode)) = 'N' THEN false
        ELSE error(
            'irrlotcode ' || r.irrlotcode || ' on lot ' || r.bbl || ' in ' || r.release
        )::BOOLEAN
        END AS irrlotcode,
    @whole(r.lottype) AS lottype,
    @whole(r.bsmtcode) AS bsmtcode,
    @whole(r.pfirm15_flag) AS pfirm15_flag,
    @whole(r.firm07_flag) AS firm07_flag,
    @whole(r.schooldist) AS schooldist,
    @whole(r.policeprct) AS policeprct,
    nullif(trim(r.latitude), '')::DOUBLE AS latitude,
    nullif(trim(r.longitude), '')::DOUBLE AS longitude
FROM records r
JOIN lots l ON l.bbl = r.bbl
