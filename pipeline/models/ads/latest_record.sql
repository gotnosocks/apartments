MODEL (
    name ads.latest_record,
    kind CUSTOM (
        materialization 'merge',
        materialization_properties (changes = 'ads.touched', replace = 'listing_id')
    ),
    grain listing_id,
    audits (
        unique_values(columns := (listing_id)),
        not_null(columns := (listing_id, collected_at, response_id))
    ),
    description 'Each ad''s latest record, cut down to the fields the latest-ask steps, the concession step and the ads file read.'
);

-- Only answers with a record take part. When the API answered an ad's latest request with
-- nothing, the ad keeps its last record, as in rentfrontier.latest_ask, which reads only
-- stored records.
--
-- `months_free`, `lease_term` and `net_effective_rent` give the concession the record's
-- `pricing` states: the months free, the lease term in months and StreetEasy's net effective
-- rent. analysis.concessions reads them.
--
-- The model reads the ads in ads.touched: every ad in a full build, and in a top-up build the ads
-- the new answers change. A top-up's materialization `merge` replaces those ads' rows in a copy of
-- the previous build's table.
SELECT listing_id::VARCHAR AS listing_id,
    fetched,
    epoch(fetched) AS collected_at,
    response_id,
    coalesce(status = 'ACTIVE', false) AS active,
    left(coalesce(nullif(on_market_at, ''), nullif(created_at, '')), 10) AS on_day,
    left(nullif(off_market_at, ''), 10) AS off_day,
    nullif(page_price, 0) AS page_price,
    floor_plans,
    months_free,
    lease_term,
    net_effective_rent
FROM ads.answers
WHERE outcome = 'record' AND listing_id::VARCHAR IN (SELECT listing_id FROM ads.touched)
QUALIFY row_number() OVER (PARTITION BY listing_id ORDER BY fetched DESC, response_id DESC) = 1
