MODEL (
    name analysis.ledger_rows,
    kind VIEW,
    grain listing_id,
    audits (unique_values(columns := (listing_id))),
    description 'The kept rows less the ads the corrections ledger excludes, with each row''s latest ask net of any concession, its gross latest ask and concession terms, the values the ledger''s live sets give and the relist unit of its unit page.'
);

-- ledger.status leaves at most one live set for each field of a row. A bath set gives the full
-- and half bathrooms and leaves `bathrooms` as recorded, as the current chain's bath rules do.
-- `asking_rent` stays the ad's first ask, as in the chain's dataset. `latest_gross` takes the
-- ask analysis.latest_ask chooses, or the ask a live ask set gives. For a row with a concession
-- in analysis.concessions, `latest_ask` takes `latest_gross` times the concession's factor,
-- rounded to the cent. A latest ask equal to a price before the concession began, and to none
-- from it on, stays gross, as when analysis.latest_ask falls back to the first ask. So does an
-- ask within $1 of the net effective rent, which StreetEasy shows already net. Otherwise a page
-- price or an ask set counts as current and takes the factor. `months_free` and `lease_term` give the
-- terms, and a row without a concession has neither. When no live square_feet set applies and a
-- coded square_feet of 2,000 or more equals the latest gross ask, the net latest ask, or a first
-- ask within 30% of the latest gross ask (rent pasted into the size box), square_feet is nulled.
-- The last column, `relist_unit`, takes the relist unit analysis.relist_units gives the row's
-- unit page, or the unit page itself.
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
),
priced AS (
    SELECT k.*,
        s.bedrooms AS set_bedrooms,
        s.full_baths AS set_full_baths,
        s.half_baths AS set_half_baths,
        s.square_feet AS set_square_feet,
        CASE
            WHEN c.listing_id IS NOT NULL
                AND NOT coalesce(abs(coalesce(s.latest_ask, a.latest_ask) - c.net_effective_rent) <= 1, false)
                AND (s.latest_ask IS NOT NULL OR a.how LIKE 'page price%'
                    OR NOT list_contains(c.gross_prices, a.latest_ask) OR list_contains(c.net_prices, a.latest_ask))
                THEN round(coalesce(s.latest_ask, a.latest_ask) * c.factor, 2)
            ELSE coalesce(s.latest_ask, a.latest_ask)
        END AS latest_ask,
        coalesce(s.latest_ask, a.latest_ask) AS latest_gross,
        c.months_free,
        c.lease_term,
        coalesce(u.relist_unit, k.unit_id) AS relist_unit
    FROM analysis.kept k
    LEFT JOIN analysis.latest_ask a USING (listing_id)
    LEFT JOIN sets s USING (listing_id)
    LEFT JOIN analysis.concessions c USING (listing_id)
    LEFT JOIN analysis.relist_units u ON u.unit_id = k.unit_id
    WHERE k.listing_id NOT IN (SELECT listing_id FROM live WHERE change = 'exclude')
)
SELECT p.* EXCLUDE (set_bedrooms, set_full_baths, set_half_baths, set_square_feet) REPLACE (
    coalesce(p.set_bedrooms, p.bedrooms) AS bedrooms,
    coalesce(p.set_full_baths, p.full_baths) AS full_baths,
    coalesce(p.set_half_baths, p.half_baths) AS half_baths,
    CASE
        WHEN p.set_square_feet IS NOT NULL THEN p.set_square_feet
        WHEN p.square_feet >= 2000
            AND (
                p.square_feet = p.latest_gross
                OR p.square_feet = p.latest_ask
                OR (p.square_feet = p.asking_rent AND p.square_feet >= 0.7 * p.latest_gross)
            )
            THEN NULL
        ELSE p.square_feet
    END AS square_feet
)
FROM priced p
