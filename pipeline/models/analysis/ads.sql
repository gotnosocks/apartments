MODEL (
    name analysis.ads,
    kind VIEW,
    grain listing_id,
    description 'Each ad with a record, kept or dropped: its unit, its latest record''s status, dates, ask, text and floor plans, its merged values, and the reasons the chain or the ledger dropped it.'
);

-- The build writes this view to ads-<hash>.parquet beside the rows file, for readers that need
-- every ad rather than the fit-ready rows: the website's current listings and Data improvements'
-- reads of a unit's other ads. Each value traces to the latest answer with a record,
-- `response_id`, or to the step named below.
--
-- The view starts from ads.identity and adds the other per-ad steps by listing_id. Each of them
-- has at most one row per ad, so the view keeps one row per ad without an audit, which would
-- read every record a second time.
--
--   unit_id, building_id, building, page, identity_reasons:  ads.identity. `page` is the unit's
--       canonical page URL.
--   regions, neighbourhood:  the export regions of the ad's answers, and the area of its
--       building in buildings.details, as in analysis.candidates.
--   response_id, fetched, status, page_price, on_day, off_day:  the latest record, as in
--       ads.latest_record. `on_day` is the record's onMarketAt, or its createdAt without one.
--   days_on_market:  the record's daysOnMarket, from ads.market.
--   description, floor_plans:  the latest record's description and the keys of its floor plan
--       images.
--   last_change, break_status, break_day, back_day:  the ad's status changes from its records,
--       from `on_day` to the New York day of the latest fetch, in the order of their times and
--       places in the record. The view leaves out the draft and review statuses, which the
--       unit's history leaves out too, so a change from review to ACTIVE isn't a break.
--       `last_change` is the latest change. When it is ACTIVE and the ad had left the market
--       since `on_day`, `break_status` and `break_day` give the change before the latest
--       return, and `back_day` the return. The website's ad dates read the same from the
--       history on the ad's page, which dates each change to the day.
--   first_day, first_ask, exclusion_reasons:  ads.exclusions.
--   latest_ask:  analysis.latest_ask, for the kept rows.
--   bedrooms to concession, conflicts, records:  ads.attributes, the values merged over the
--       ad's records before any correction. `full_baths`, `half_baths` and `label_floor` come
--       from ads.reported.
--   fate:  the unit-month check's verdict in analysis.candidates, missing for an ad the chain
--       drops before that check.
--   ledger_entries:  the live entries of the corrections ledger for the ad.
--   in_rows:  whether the ad has a fit-ready row in analysis.rows.
WITH latest AS (
    SELECT l.listing_id, l.response_id, r.fetched, l.active, l.on_day, l.off_day, l.page_price,
        json_extract_string(r.record, ['$.description', '$.media.floorPlans']) AS f
    FROM ads.latest_record l
    JOIN raw.ads r ON r.listing_id = l.listing_id::BIGINT AND r.response_id = l.response_id
),
regions AS (
    SELECT listing_id::VARCHAR AS listing_id, list_sort(list(DISTINCT region)) AS regions
    FROM raw.ads
    GROUP BY listing_id
),
changes AS (
    SELECT e.listing_id, e.kind, e.day,
        lag(e.kind) OVER (PARTITION BY e.listing_id ORDER BY e."at", e.list_index) AS previous,
        lag(e.day) OVER (PARTITION BY e.listing_id ORDER BY e."at", e.list_index) AS previous_day,
        e."at", e.list_index
    FROM ads.events e
    JOIN ads.market m USING (listing_id)
    JOIN ads.latest_record l USING (listing_id)
    WHERE e.source = 'status' AND e.day BETWEEN l.on_day::DATE AND m.as_of
        AND e.kind NOT IN ('DRAFT', 'IN_STREETEASY_REVIEW', 'IN_BROKERAGE_REVIEW')
),
breaks AS (
    SELECT listing_id,
        arg_max(kind, ("at", list_index)) AS last_change,
        arg_max(previous, ("at", list_index)) FILTER (
            WHERE kind = 'ACTIVE' AND previous <> 'ACTIVE'
        ) AS break_status,
        arg_max(previous_day, ("at", list_index)) FILTER (
            WHERE kind = 'ACTIVE' AND previous <> 'ACTIVE'
        ) AS break_day,
        arg_max(day, ("at", list_index)) FILTER (
            WHERE kind = 'ACTIVE' AND previous <> 'ACTIVE'
        ) AS back_day
    FROM changes
    GROUP BY listing_id
),
ledger AS (
    SELECT listing_id, list_sort(list(entry)) AS ledger_entries
    FROM ledger.status
    WHERE status = 'live'
    GROUP BY listing_id
)
SELECT i.listing_id, i.unit_id, i.building_id, i.building, i.page, g.regions,
    b.area AS neighbourhood,
    l.response_id, l.fetched, m.status, l.page_price, l.on_day::DATE AS on_day,
    l.off_day::DATE AS off_day, m.record_days_on_market AS days_on_market,
    k.last_change,
    CASE WHEN k.last_change = 'ACTIVE' THEN k.break_status END AS break_status,
    CASE WHEN k.last_change = 'ACTIVE' THEN k.break_day END AS break_day,
    CASE WHEN k.last_change = 'ACTIVE' THEN k.back_day END AS back_day,
    e.first_day, e.rent AS first_ask, a.latest_ask,
    t.bedrooms, t.bathrooms, r.full_baths, r.half_baths, t.square_feet, t.advertised_floor,
    t.physical_floor, r.label_floor, t.floors_above_ground, t.elevator, t.laundry_type,
    t.doorman_type, t.hvac_type, t.pet_policy, t.view_exposures, t.window_exposures,
    t.furnished, t.short_term, t.concession, t.conflicts, t.records,
    l.f[1] AS description,
    list_transform(
        from_json(l.f[2], '[{"key": "VARCHAR"}]'), p -> p.key
    ) AS floor_plans,
    i.reasons AS identity_reasons, e.reasons AS exclusion_reasons, c.fate,
    coalesce(d.ledger_entries, []) AS ledger_entries,
    i.listing_id IN (SELECT listing_id FROM analysis.rows) AS in_rows
FROM ads.identity i
JOIN latest l USING (listing_id)
JOIN ads.market m USING (listing_id)
JOIN ads.exclusions e USING (listing_id)
JOIN ads.reported r USING (listing_id)
LEFT JOIN ads.attributes t USING (listing_id)
LEFT JOIN regions g USING (listing_id)
LEFT JOIN buildings.details b ON b.building_id = i.building_id
LEFT JOIN breaks k USING (listing_id)
LEFT JOIN analysis.latest_ask a USING (listing_id)
LEFT JOIN analysis.candidates c USING (listing_id)
LEFT JOIN ledger d USING (listing_id)
