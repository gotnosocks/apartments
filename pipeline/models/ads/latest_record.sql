MODEL (
    name ads.latest_record,
    kind FULL,
    grain listing_id,
    audits (unique_values(columns := (listing_id)), not_null(columns := (listing_id, collected_at))),
    description 'Each ad''s latest record, cut down to the fields the latest-ask steps read.'
);

-- Only answers with a record take part. When the API answered an ad's latest request with
-- nothing, the ad keeps its last record, as in rentfrontier.latest_ask, which reads only
-- stored records.
-- The fields come out of each record in one parse before the pick, so the pick only holds
-- small rows. With whole records in the pick, DuckDB ran out of a 5 GB limit.
WITH fields AS (
    SELECT listing_id, fetched, response_id,
        json_extract_string(record, ['$.status', '$.onMarketAt', '$.createdAt', '$.offMarketAt', '$.pricing.price', '$.pricing.priceChanges']) AS f
    FROM raw.ads WHERE outcome = 'record'
),
latest AS (
    SELECT * FROM fields
    QUALIFY row_number() OVER (PARTITION BY listing_id ORDER BY fetched DESC, response_id DESC) = 1
)
SELECT
    listing_id::VARCHAR AS listing_id,
    epoch(fetched) AS collected_at,
    coalesce(f[1] = 'ACTIVE', false) AS active,
    left(coalesce(nullif(f[2], ''), nullif(f[3], '')), 10) AS on_day,
    left(nullif(f[4], ''), 10) AS off_day,
    nullif(f[5]::DOUBLE, 0) AS page_price,
    from_json(f[6], '[{"changedAt": "VARCHAR", "price": "DOUBLE"}]') AS changes
FROM latest
