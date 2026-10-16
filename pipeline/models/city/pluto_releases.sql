MODEL (
    name city.pluto_releases,
    kind FULL,
    grain release,
    audits (unique_values(columns := (release)), not_null(columns := (release))),
    description 'Each MapPLUTO release: its published date, the first day an ad reads it, and for each field whether any lot in the city has a value in it.'
);

-- A release becomes usable 7 days after its published date, in UTC, the zone of the dates in
-- the archive's manifest, as in the served model's `plutoasof-v3`. Release 22v2 has no published
-- date, so it has no first day either.
--
-- The step looks at every lot of the city, since a field such as a flood zone flag holds a value
-- only for lots in the zone. A release with no value in a field for any lot lacks the field, and
-- `analysis.lot_facts` takes that field from the latest release. Across the 44 releases the step
-- scans 37 million records, so it leaves out `geom`, the lot's outline in releases 18v2 to 20v1.
-- It picks the fields with a list rather than `EXCLUDE`, which fails on files without `geom`.
SELECT release, any_value(published) AS published,
    (any_value(published) AT TIME ZONE 'UTC')::DATE + 7 AS usable_from,
    bool_or(
        nullif(
            trim(
                COLUMNS(
                    c -> c NOT IN (
                        'release', 'published', 'file', 'member', 'record', 'encoding', 'geom'
                    )
                )
            ),
            ''
        ) IS NOT NULL
    )
FROM city.pluto
GROUP BY release
