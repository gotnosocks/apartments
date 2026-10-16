MODEL (
    name analysis.lot_landmarks,
    kind FULL,
    grain listing_id,
    audits (unique_values(columns := (listing_id)), not_null(columns := (listing_id))),
    description 'Each candidate ad''s lot, with the landmark and historic district designations the LPC had made on it by the ad''s first day.'
);

-- The step reads the latest copy of LPC's designations in `city.landmarks`, a row for each
-- building of each designation, and keeps the rows with the status DESIGNATED. A row of a historic
-- district marks a lot in the district. A row of an individual, interior or scenic landmark
-- marks the lot as a landmark, as the served model's `lpc_as_of` reads them. These values stop
-- the build, so a change in the copy's spelling shows up here rather than as a missing
-- designation:
--
-- - a type other than those four,
-- - a designation date that is blank or isn't written as month/day/year with a four-digit
--   year.
--
-- For each candidate ad it takes the lot of its building from `buildings.lots` and dates the ad
-- by its first day in UTC, as the served model does. It then keeps the lot's designations made
-- on or before that day: the earliest landmark and the earliest district, each with its date
-- and LP number. `landmark` and `historic_district` say whether the lot had one, and stay
-- missing for an ad without a lot. Designations after the ad stay off its row, so a fit can
-- read every column.
--
-- The copy gives the designations as of its release, so a designation the LPC later withdrew is missing
-- from every ad, and an ad after the copy's release misses designations made since.
-- `landmarks_release` gives the copy each row read. With no copy in the archive, `city.landmarks`
-- has only the archive's columns, so the step adds the others with no rows, and every ad reads
-- `landmark` and `historic_district` as missing.
WITH latest AS (
    SELECT arg_max(release, published) AS release FROM city.landmarks
), copy AS (
    SELECT c.* FROM (
        SELECT * FROM (
            SELECT NULL::TEXT AS bbl, NULL::TEXT AS lp_number, NULL::TEXT AS lm_type,
                NULL::TEXT AS desdate, NULL::TEXT AS status
            WHERE false
        ) UNION ALL BY NAME (SELECT * FROM city.landmarks)
    ) c
    JOIN latest USING (release)
    WHERE trim(c.status) = 'DESIGNATED'
), designations AS (
    SELECT trim(bbl) AS bbl, trim(lp_number) AS lp_number,
        CASE trim(lm_type)
            WHEN 'Historic District' THEN true
            WHEN 'Individual Landmark' THEN false
            WHEN 'Interior Landmark' THEN false
            WHEN 'Scenic Landmark' THEN false
            ELSE error(concat('lm_type ', lm_type, ' of ', lp_number, ' on lot ', bbl))::BOOLEAN
            END AS district,
        CASE WHEN nullif(trim(desdate), '') IS NULL
            THEN error(concat('no designation date for ', lp_number, ' on lot ', bbl))::DATE
            WHEN NOT regexp_full_match(trim(desdate), '[0-9]{1,2}/[0-9]{1,2}/[0-9]{4}')
            THEN error(
                concat('designation date ', desdate, ' of ', lp_number, ' on lot ', bbl)
            )::DATE
            ELSE strptime(trim(desdate), '%m/%d/%Y')::DATE
            END AS designated
    FROM copy
), ads AS (
    SELECT c.listing_id, c.building_id, (c.price_at AT TIME ZONE 'UTC')::DATE AS first_day, l.bbl
    FROM analysis.candidates c
    LEFT JOIN buildings.lots l USING (building_id)
), held AS (
    SELECT a.listing_id,
        min(d.designated) FILTER (WHERE NOT d.district) AS landmark_since,
        arg_min(d.lp_number, (d.designated, d.lp_number)) FILTER (WHERE NOT d.district)
            AS landmark_lp,
        min(d.designated) FILTER (WHERE d.district) AS district_since,
        arg_min(d.lp_number, (d.designated, d.lp_number)) FILTER (WHERE d.district)
            AS district_lp
    FROM ads a
    JOIN designations d ON d.bbl = a.bbl AND d.designated <= a.first_day
    GROUP BY a.listing_id
)
SELECT a.listing_id, a.building_id, a.bbl, a.first_day, latest.release AS landmarks_release,
    CASE WHEN a.bbl IS NOT NULL AND latest.release IS NOT NULL
        THEN h.landmark_since IS NOT NULL END AS landmark,
    CASE WHEN a.bbl IS NOT NULL AND latest.release IS NOT NULL
        THEN h.district_since IS NOT NULL END AS historic_district,
    h.landmark_since, h.landmark_lp, h.district_since, h.district_lp
FROM ads a
CROSS JOIN latest
LEFT JOIN held h USING (listing_id)
