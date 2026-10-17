MODEL (
    name analysis.relist_pairs,
    kind FULL,
    grain (listing_id, next_listing_id),
    audits (
        unique_combination_of_columns(columns := (listing_id, next_listing_id)),
        not_null(columns := (bbl, listing_id, next_listing_id, unit_id, next_unit_id, gap, photos))
    ),
    description 'Pairs of kept ads on two unit pages of a lot, where the second ad looks like the first listed again: same layout, a start soon after the first ad ended, a close ask and shared photos.'
);

-- A broker who lists an apartment again often starts a new unit page under another label, and
-- the lot then shows more unit pages than it has apartments. The step looks for these relists
-- only in lots over their count: lots where the unit pages with an ad on the market in the 12
-- months to the build's as-of day outnumber the apartments of the latest MapPLUTO release.
-- Within such a lot, it pairs a kept ad with a kept ad of another unit page when
--
-- 1. the second ad comes on the market between 3 days before and 7 days after the first goes
--    off,
-- 2. both give the same bedrooms and bathrooms,
-- 3. neither the listed floor, the advertised floor nor the floor of the unit labels differs,
--    where both ads give one,
-- 4. the second ad's first or latest ask lies within 3% of the first ad's latest ask, and
-- 5. the two unit pages share a rare photo.
--
-- A photo counts as rare when its key appears on 2 or 3 unit pages, all in the same lot. A key on
-- more pages usually shows the building's lobby, roof or gym. The step takes the keys an ad of a
-- lot over its count shows, and counts each key's pages over every placed ad, kept or not.
-- On ads runs 1 to 16, starting from those keys took 6 s in a build, against 44 s for counting
-- every key.
-- `gap` gives the days from the first ad's end to the second ad's start, and `photos` the rare
-- keys the two unit pages share.
--
-- Readers judged a sample of these pairs from the ads alone, without the photos, as
-- docs/data/pipeline.md describes under Relist units. analysis.relist_links decides which pairs
-- join their unit pages.
WITH as_of AS (
    SELECT max(as_of) AS day FROM ads.market
), apartments AS (
    SELECT try_cast(bbl AS DOUBLE)::BIGINT::VARCHAR AS bbl,
        any_value(try_cast(unitsres AS DOUBLE)::INTEGER) AS apartments
    FROM city.pluto
    WHERE release = (SELECT any_value(pluto_release) FROM buildings.lots)
        AND try_cast(bbl AS DOUBLE) IS NOT NULL
    GROUP BY 1
), placed AS (
    SELECT p.listing_id, p.unit_id, l.bbl
    FROM ads.placed p
    JOIN buildings.lots l USING (building_id)
    WHERE p.unit_id IS NOT NULL AND l.bbl IS NOT NULL
), over AS (
    SELECT p.bbl
    FROM placed p
    JOIN ads.market m USING (listing_id)
    JOIN apartments a USING (bbl)
    WHERE coalesce(m.off_day, m.as_of) > (SELECT day FROM as_of) - INTERVAL 12 MONTH
    GROUP BY p.bbl, a.apartments
    HAVING count(DISTINCT p.unit_id) > a.apartments
), candidate_keys AS (
    SELECT DISTINCT f.key
    FROM ads.photos f
    JOIN placed p USING (listing_id)
    WHERE p.bbl IN (SELECT bbl FROM over)
), shown AS (
    SELECT DISTINCT p.bbl, p.unit_id, f.key
    FROM ads.photos f
    SEMI JOIN candidate_keys USING (key)
    JOIN placed p USING (listing_id)
), rare AS (
    SELECT s.*
    FROM shown s
    SEMI JOIN (
        SELECT key FROM shown GROUP BY key
        HAVING count(DISTINCT bbl) = 1 AND count(DISTINCT unit_id) BETWEEN 2 AND 3
    ) USING (key)
), shared AS (
    SELECT x.unit_id, y.unit_id AS next_unit_id, count(*) AS photos
    FROM rare x
    JOIN rare y ON x.key = y.key AND x.unit_id <> y.unit_id
    GROUP BY ALL
), kept AS (
    SELECT k.listing_id, k.unit_id, l.bbl, k.bedrooms, k.bathrooms, k.listed_floor,
        k.advertised_floor, r.label_floor, m.on_day, m.off_day, a.first_ask, a.latest_ask
    FROM analysis.kept k
    JOIN analysis.latest_ask a USING (listing_id)
    JOIN ads.market m USING (listing_id)
    LEFT JOIN ads.reported r USING (listing_id)
    JOIN buildings.lots l USING (building_id)
    WHERE k.unit_id IS NOT NULL AND l.bbl IN (SELECT bbl FROM over)
)
SELECT x.bbl, x.listing_id, y.listing_id AS next_listing_id, x.unit_id, y.unit_id AS next_unit_id,
    y.on_day - x.off_day AS gap, s.photos
FROM kept x
JOIN kept y ON x.bbl = y.bbl
    AND x.unit_id <> y.unit_id
    AND x.bedrooms = y.bedrooms
    AND x.bathrooms IS NOT DISTINCT FROM y.bathrooms
    AND NOT coalesce(x.listed_floor <> y.listed_floor, false)
    AND NOT coalesce(x.advertised_floor <> y.advertised_floor, false)
    AND NOT coalesce(x.label_floor <> y.label_floor, false)
    AND y.on_day - x.off_day BETWEEN -3 AND 7
    AND (abs(y.first_ask - x.latest_ask) < 0.03 * x.latest_ask
        OR abs(y.latest_ask - x.latest_ask) < 0.03 * x.latest_ask)
JOIN shared s ON s.unit_id = x.unit_id AND s.next_unit_id = y.unit_id
