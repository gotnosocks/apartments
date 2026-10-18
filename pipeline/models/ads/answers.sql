MODEL (
    name ads.answers,
    kind CUSTOM (
        materialization 'merge',
        materialization_properties (changes = 'ads.changes', add = 'listing_id, response_id')
    ),
    audits (
        unique_combination_of_columns(columns := (listing_id, response_id)),
        not_null(columns := (listing_id, fetched, response_id, outcome))
    ),
    description 'Each API answer for an ad, with the fields the event log, the latest-ask steps, the concession terms and the ads file read, parsed once.'
);

-- A record's unit history repeats in the record of each ad of the unit, so a unit with n ads
-- holds about n² copies of its events. Instead of parsing each copy, the model keeps an MD5 of
-- the history's JSON text, and ads.history_events parses each distinct history once.
--
-- The model parses the answers in ads.changes: every answer in a full build, and the new ones in
-- a top-up build, which the materialization `merge` adds to a copy of the previous build's
-- table. ads.identity and ads.regions read the building, unit and region fields from here.
--
-- The query takes each value's text with one json_extract_string of the record. A json_extract
-- of the record keeps the unit history as a JSON value, and the history's MD5 then writes its
-- text out again for each row. On the 238,532 answers of run 2, with 12 threads, that form ran
-- out of DuckDB's 2 GB limit, and this one ran within 1.75 GB.
SELECT listing_id, fetched, response_id, outcome, record_sha256, region,
    f[1] AS status,
    f[2]::DOUBLE AS page_price,
    from_json(f[3], '[{"changedAt": "VARCHAR", "status": "VARCHAR"}]') AS status_changes,
    from_json(f[4], '[{"changedAt": "VARCHAR", "price": "DOUBLE"}]') AS price_changes,
    md5_number(f[5]) AS history,
    f[6]::INTEGER AS days_on_market,
    nullif(f[7]::DOUBLE, 0) AS rented_price,
    f[8] AS on_market_at,
    f[9] AS created_at,
    f[10] AS off_market_at,
    list_transform(from_json(f[11], '[{"key": "VARCHAR"}]'), p -> p.key) AS floor_plans,
    f[12] AS building_id,
    f[13] AS unit_slug,
    f[14]::DOUBLE AS months_free,
    f[15]::DOUBLE AS lease_term,
    f[16]::DOUBLE AS net_effective_rent
FROM (
    SELECT r.*,
        json_extract_string(r.record, ['$.status', '$.pricing.price', '$.statusChanges', '$.pricing.priceChanges', '$.propertyHistory', '$.daysOnMarket', '$.pricing.rentedPrice', '$.onMarketAt', '$.createdAt', '$.offMarketAt', '$.media.floorPlans', '$.buildingId', '$.slug', '$.pricing.monthsFree', '$.pricing.leaseTermMonths', '$.pricing.netEffectiveRent']) AS f
    FROM raw.ads r
    SEMI JOIN ads.changes c USING (listing_id, response_id)
)
