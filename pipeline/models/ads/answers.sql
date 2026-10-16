MODEL (
    name ads.answers,
    kind FULL,
    audits (
        unique_combination_of_columns(columns := (listing_id, response_id)),
        not_null(columns := (listing_id, fetched, response_id, outcome))
    ),
    description 'Each API answer for an ad, with the fields the event log reads, parsed once.'
);

-- A record's unit history repeats in the record of each ad of the unit, so a unit with n ads
-- holds about n² copies of its events. Instead of parsing each copy, the model keeps an MD5 of
-- the history's JSON text, and ads.history_events parses each distinct history once.
SELECT listing_id, fetched, response_id, outcome, record_sha256,
    f[1] AS status,
    f[2]::DOUBLE AS page_price,
    from_json(f[3], '[{"changedAt": "VARCHAR", "status": "VARCHAR"}]') AS status_changes,
    from_json(f[4], '[{"changedAt": "VARCHAR", "price": "DOUBLE"}]') AS price_changes,
    md5_number(f[5]) AS history,
    f[6]::INTEGER AS days_on_market,
    nullif(f[7]::DOUBLE, 0) AS rented_price
FROM (
    SELECT *,
        json_extract_string(record, ['$.status', '$.pricing.price', '$.statusChanges', '$.pricing.priceChanges', '$.propertyHistory', '$.daysOnMarket', '$.pricing.rentedPrice']) AS f
    FROM raw.ads
)
