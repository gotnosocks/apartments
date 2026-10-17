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
    description 'Each API answer for an ad, with the fields the event log, the latest-ask steps and the ads file read, parsed once.'
);

-- A record's unit history repeats in the record of each ad of the unit, so a unit with n ads
-- holds about n² copies of its events. Instead of parsing each copy, the model keeps an MD5 of
-- the history's JSON text, and ads.history_events parses each distinct history once.
--
-- The model parses the answers in ads.changes: every answer in a full build, and the new ones in
-- a top-up build, which the materialization `merge` adds to a copy of the previous build's
-- table. ads.identity, ads.regions and ads.reported read the building, unit, region and
-- bathroom fields from here, so a top-up parses each record once.
SELECT listing_id, fetched, response_id, outcome, record_sha256, region,
    json_extract_string(j[1], '$') AS status,
    json_extract_string(j[2], '$')::DOUBLE AS page_price,
    from_json(
        json_extract_string(j[3], '$'), '[{"changedAt": "VARCHAR", "status": "VARCHAR"}]'
    ) AS status_changes,
    from_json(
        json_extract_string(j[4], '$'), '[{"changedAt": "VARCHAR", "price": "DOUBLE"}]'
    ) AS price_changes,
    md5_number(json_extract_string(j[5], '$')) AS history,
    json_extract_string(j[6], '$')::INTEGER AS days_on_market,
    nullif(json_extract_string(j[7], '$')::DOUBLE, 0) AS rented_price,
    json_extract_string(j[8], '$') AS on_market_at,
    json_extract_string(j[9], '$') AS created_at,
    json_extract_string(j[10], '$') AS off_market_at,
    list_transform(
        from_json(json_extract_string(j[11], '$'), '[{"key": "VARCHAR"}]'), p -> p.key
    ) AS floor_plans,
    json_extract_string(j[12], '$') AS building_id,
    json_extract_string(j[13], '$') AS unit_slug,
    j[14] AS display_unit,
    j[15] AS full_bathroom_count,
    j[16] AS half_bathroom_count
FROM (
    -- The query parses each record once, with json_extract, since a second parse for the text
    -- values ran out of 1 GB on the sample. json_extract_string of each of the first 13 values
    -- gives the text a json_extract_string of the record would give, and ads.reported reads
    -- the last three values as JSON.
    SELECT r.*,
        json_extract(r.record, ['$.status', '$.pricing.price', '$.statusChanges', '$.pricing.priceChanges', '$.propertyHistory', '$.daysOnMarket', '$.pricing.rentedPrice', '$.onMarketAt', '$.createdAt', '$.offMarketAt', '$.media.floorPlans', '$.buildingId', '$.slug', '$.propertyDetails.address.displayUnit', '$.propertyDetails.fullBathroomCount', '$.propertyDetails.halfBathroomCount']) AS j
    FROM raw.ads r
    SEMI JOIN ads.changes c USING (listing_id, response_id)
)
