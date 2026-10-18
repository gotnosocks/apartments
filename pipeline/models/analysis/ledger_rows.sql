MODEL (
    name analysis.ledger_rows,
    kind VIEW,
    grain listing_id,
    audits (unique_values(columns := (listing_id))),
    description 'The kept rows less the ads the corrections ledger excludes, with each row''s latest ask, the values the ledger''s live sets give and the relist unit of its unit page.'
);

-- ledger.status leaves at most one live set for each field of a row. A bath set gives the full
-- and half bathrooms and leaves `bathrooms` as recorded, as the current chain's bath rules do.
-- `asking_rent` stays the ad's first ask, as in the chain's dataset. The column `latest_ask`
-- takes the ask analysis.latest_ask chooses, or the ask a live ask set gives. The last column,
-- `relist_unit`, takes the relist unit analysis.relist_units gives the row's unit page, or the
-- unit page itself.
WITH live AS (
    SELECT s.listing_id, s.change, s.field, e.bedrooms, e.full_baths, e.half_baths, e.square_feet,
        e.latest_ask
    FROM ledger.status s JOIN ledger.entries e USING (entry)
    WHERE s.status = 'live'
),
sets AS (
    SELECT listing_id,
        max(bedrooms) FILTER (WHERE field = 'bedrooms') AS bedrooms,
        max(full_baths) FILTER (WHERE field = 'baths') AS full_baths,
        max(half_baths) FILTER (WHERE field = 'baths') AS half_baths,
        max(square_feet) FILTER (WHERE field = 'square_feet') AS square_feet,
        max(latest_ask) FILTER (WHERE field = 'latest_ask') AS latest_ask
    FROM live
    WHERE change = 'set'
    GROUP BY listing_id
)
SELECT k.* REPLACE (
    coalesce(s.bedrooms, k.bedrooms) AS bedrooms,
    coalesce(s.full_baths, k.full_baths) AS full_baths,
    coalesce(s.half_baths, k.half_baths) AS half_baths,
    coalesce(s.square_feet, k.square_feet) AS square_feet
), coalesce(s.latest_ask, a.latest_ask) AS latest_ask,
    coalesce(u.relist_unit, k.unit_id) AS relist_unit
FROM analysis.kept k
LEFT JOIN analysis.latest_ask a USING (listing_id)
LEFT JOIN sets s USING (listing_id)
LEFT JOIN analysis.relist_units u ON u.unit_id = k.unit_id
WHERE k.listing_id NOT IN (SELECT listing_id FROM live WHERE change = 'exclude')
