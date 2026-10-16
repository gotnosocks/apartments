MODEL (
    name analysis.lot_facts,
    kind FULL,
    grain listing_id,
    audits (unique_values(columns := (listing_id)), not_null(columns := (listing_id))),
    description 'Each candidate ad''s lot and BIN, with the lot''s MapPLUTO facts as the latest release published at least 7 days before the ad''s first day gives them.'
);

-- The facts each ad reads from its own release. The rest come from the latest release.
@DEF(
    dated,
    [
        yearalter1, yearalter2, numfloors, numbldgs, unitsres, unitstotal, lotarea, bldgarea,
        resarea, comarea, retailarea, lotfront, lotdepth, bldgfront, bldgdepth, bldgclass,
        landuse, landmark, histdist, zonedist1, builtfar, residfar, proxcode, irrlotcode, lottype,
        bsmtcode, pfirm15_flag, firm07_flag, schooldist, policeprct
    ]
);

-- The ad's record in its release gives its facts: the lot is in the release, and the release
-- came out no earlier than the year of the building on the lot.
@DEF(
    record,
    t.bbl IS NOT NULL AND NOT coalesce(n.yearbuilt > year(k.published AT TIME ZONE 'UTC'), false)
);

-- For each candidate ad, the step takes its building's lot and BIN from `buildings.lots`. For an
-- ad with a lot, it picks a MapPLUTO release: the latest one published at least 7 days before
-- the ad's first day, or the first release for an ad before that. It skips releases without a
-- published date. It then reads the lot's facts from that release's record, as the served
-- model's `plutoasof-v3` does, with these exceptions:
--
-- 1. The address, the year built and the coordinates come from the latest release. They place
--    the lot rather than describe it, and older releases often give a round guess for the year.
-- 2. When the release has no record of the lot, which happens to a lot numbered after the
--    release, every fact comes from the latest release, and `pluto_fallback` says `lot_missing`.
-- 3. When the release came out in a year before the latest release's year built, its record
--    describes the lot before the building, so every fact comes from the latest release, and
--    `pluto_fallback` says `before_built`.
-- 4. When no lot in the city has a value in a field of the release, as in the flood zone flags
--    before 2017, that field comes from the latest release. `city.pluto_releases` records the
--    fields each release carries, and `latest_fields` lists those the ad takes from the latest
--    release. Here the step differs from the served model, which looks only at the registry's
--    lots in Data improvements' releases file and counts a value of spaces as a value.
--
-- The release, its published date and the fallback stay on each row, so each value traces to a
-- record of `buildings.lot_releases`. The step dates ads in UTC, the zone of the published
-- dates in the archive's manifest.
WITH releases AS (
    SELECT * FROM city.pluto_releases WHERE published IS NOT NULL
), missing AS (
    SELECT release,
        coalesce(list(field ORDER BY field) FILTER (WHERE NOT carried), []) AS fields
    FROM (
        UNPIVOT (SELECT release, @EACH(@dated, f -> @f) FROM releases)
        ON COLUMNS(* EXCLUDE (release)) INTO NAME field VALUE carried
    )
    GROUP BY release
), latest AS (
    SELECT * FROM buildings.lot_releases
    WHERE release = (SELECT arg_max(release, published) FROM releases)
), ads AS (
    SELECT c.listing_id, c.building_id, (c.price_at AT TIME ZONE 'UTC')::DATE AS first_day,
        l.bbl, l.bin, l.link
    FROM analysis.candidates c
    LEFT JOIN buildings.lots l USING (building_id)
), dated AS (
    SELECT a.*,
        CASE WHEN a.bbl IS NOT NULL
            THEN coalesce(r.release, (SELECT arg_min(release, published) FROM releases))
            END AS release
    FROM ads a
    ASOF LEFT JOIN releases r ON a.first_day >= r.usable_from
)
SELECT d.listing_id, d.building_id, d.bbl, d.bin, d.link, d.release AS pluto_release,
    k.published AS pluto_published,
    CASE WHEN d.bbl IS NULL THEN NULL
        WHEN t.bbl IS NULL THEN 'lot_missing'
        WHEN n.yearbuilt > year(k.published AT TIME ZONE 'UTC') THEN 'before_built'
        END AS pluto_fallback,
    CASE WHEN @record THEN m.fields END AS latest_fields,
    n.address, n.yearbuilt, n.latitude, n.longitude,
    @EACH(@dated, f -> CASE WHEN @record AND k.@f THEN t.@f ELSE n.@f END AS @f)
FROM dated d
LEFT JOIN releases k USING (release)
LEFT JOIN missing m USING (release)
LEFT JOIN buildings.lot_releases t ON t.bbl = d.bbl AND t.release = d.release
LEFT JOIN latest n ON n.bbl = d.bbl
