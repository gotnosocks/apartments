MODEL (
    name analysis.rows,
    kind VIEW,
    grain listing_id,
    audits (unique_values(columns := (listing_id))),
    description 'The fit-ready rows: the kept rows less the ads the corrections ledger excludes and the rows analysis.ask_check lists, with the values the ledger''s live sets give.'
);

-- ledger.status leaves at most one live set for each field of a row. A bath set gives the full
-- and half bathrooms and leaves `bathrooms` as recorded, as the current chain's bath rules do.
WITH live AS (
    SELECT s.listing_id, s.change, s.field, e.bedrooms, e.full_baths, e.half_baths, e.square_feet
    FROM ledger.status s JOIN ledger.entries e USING (entry)
    WHERE s.status = 'live'
),
sets AS (
    SELECT listing_id,
        max(bedrooms) FILTER (WHERE field = 'bedrooms') AS bedrooms,
        max(full_baths) FILTER (WHERE field = 'baths') AS full_baths,
        max(half_baths) FILTER (WHERE field = 'baths') AS half_baths,
        max(square_feet) FILTER (WHERE field = 'square_feet') AS square_feet
    FROM live
    WHERE change = 'set'
    GROUP BY listing_id
)
SELECT k.* REPLACE (
    coalesce(s.bedrooms, k.bedrooms) AS bedrooms,
    coalesce(s.full_baths, k.full_baths) AS full_baths,
    coalesce(s.half_baths, k.half_baths) AS half_baths,
    coalesce(s.square_feet, k.square_feet) AS square_feet
)
FROM analysis.kept k
LEFT JOIN sets s USING (listing_id)
WHERE k.listing_id NOT IN (SELECT listing_id FROM live WHERE change = 'exclude')
    AND k.listing_id NOT IN (SELECT listing_id FROM analysis.ask_check)
