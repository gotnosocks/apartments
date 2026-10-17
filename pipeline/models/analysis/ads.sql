MODEL (
    name analysis.ads,
    kind VIEW,
    grain listing_id,
    description 'Each ad with a record, kept or dropped: its unit, its latest record''s status, dates, ask and floor plans, its merged values, and the reasons the chain or the ledger dropped it.'
);

-- The build writes this view to ads-<hash>.parquet beside the rows file, for readers that need
-- every ad rather than the fit-ready rows: the website's current listings and Data improvements'
-- reads of a unit's other ads. Each value traces to the latest answer with a record,
-- `response_id`, or to the step named below. The file leaves out the ad's text, which a reader
-- takes from that answer in the export.
--
-- The view starts from ads.placed and adds the other per-ad steps by listing_id. Each of them
-- has at most one row per ad, so the view keeps one row per ad without an audit. The breaks and
-- the regions are tables of their own: worked out inside the view, they took the build's sorted
-- copy of it past 3 GB of memory.
--
--   unit_id, building_id, building, page, identity_reasons, placements:  ads.placed, after the
--       unit ledger. `page` is the unit's canonical page URL, and `placements` lists the unit
--       ledger's entries applied to the ad.
--   regions:  ads.regions, the export regions of the ad's answers.
--   neighbourhood:  the area of its building in buildings.details, as in analysis.candidates.
--   response_id, fetched, page_price, on_day, off_day, floor_plans:  the latest record, as in
--       ads.latest_record. `on_day` is the record's onMarketAt, or its createdAt without one,
--       and `floor_plans` lists the keys of its floor plan images.
--   status, days_on_market:  the record's status and daysOnMarket, from ads.market.
--   last_change, break_status, break_day, back_day:  ads.breaks, the last status change the
--       latest record lists from `on_day` on, and the ad's latest break when its status is ACTIVE
--       and it is back on the market.
--   first_day, first_ask, exclusion_reasons:  ads.exclusions.
--   latest_ask:  analysis.latest_ask, for the kept rows, before the corrections ledger. The
--       rows file's `latest_ask` gives the ask a live ask set corrects.
--   bedrooms to concession, conflicts, records:  ads.attributes, the values merged over the
--       ad's records up to its last ACTIVE one, before any correction. `full_baths`,
--       `half_baths` and `label_floor` come from ads.reported.
--   fate:  the unit-month check's verdict in analysis.candidates, missing for an ad the chain
--       drops before that check.
--   ledger_entries:  the live entries of the corrections ledger for the ad.
--   ask_check:  for a row analysis.ask_check lists for review, the median latest ask of the
--       building's other rows with the same bedroom count, their number and the row's ratio to
--       the median.
--   building_check:  for a row analysis.building_check lists for review, its reasons, the lot
--       and release it read, the ad's floor and the lot's floor count, apartments and land use.
--   in_rows:  whether the ad has a fit-ready row in analysis.rows.
WITH ledger AS (
    SELECT listing_id, list_sort(list(entry)) AS ledger_entries
    FROM ledger.status
    WHERE status = 'live'
    GROUP BY listing_id
)
SELECT i.listing_id, i.unit_id, i.building_id, i.building, i.page, g.regions,
    b.area AS neighbourhood,
    l.response_id, l.fetched, m.status, l.page_price, l.on_day::DATE AS on_day,
    l.off_day::DATE AS off_day, m.record_days_on_market AS days_on_market,
    k.last_change, k.break_status, k.break_day, k.back_day,
    e.first_day, e.rent AS first_ask, a.latest_ask,
    t.bedrooms, t.bathrooms, r.full_baths, r.half_baths, t.square_feet, t.advertised_floor,
    t.physical_floor, r.label_floor, t.floors_above_ground, t.elevator, t.laundry_type,
    t.doorman_type, t.hvac_type, t.pet_policy, t.view_exposures, t.window_exposures,
    t.furnished, t.short_term, t.concession, t.conflicts, t.records,
    l.floor_plans,
    i.reasons AS identity_reasons, e.reasons AS exclusion_reasons, c.fate,
    coalesce(d.ledger_entries, []) AS ledger_entries, i.placements,
    CASE WHEN q.listing_id IS NOT NULL
        THEN {'peer_ask': q.peer_ask, 'peer_rows': q.peer_rows, 'ratio': q.ratio} END AS ask_check,
    CASE WHEN h.listing_id IS NOT NULL
        THEN {
            'reasons': h.reasons, 'bbl': h.bbl, 'pluto_release': h.pluto_release,
            'floor': h.floor, 'numfloors': h.numfloors, 'unitsres': h.unitsres,
            'landuse': h.landuse
        } END AS building_check,
    i.listing_id IN (SELECT listing_id FROM analysis.rows) AS in_rows
FROM ads.placed i
JOIN ads.latest_record l USING (listing_id)
JOIN ads.market m USING (listing_id)
JOIN ads.exclusions e USING (listing_id)
JOIN ads.reported r USING (listing_id)
LEFT JOIN ads.attributes t USING (listing_id)
LEFT JOIN ads.regions g USING (listing_id)
LEFT JOIN buildings.details b ON b.building_id = i.building_id
LEFT JOIN ads.breaks k USING (listing_id)
LEFT JOIN analysis.latest_ask a USING (listing_id)
LEFT JOIN analysis.candidates c USING (listing_id)
LEFT JOIN ledger d USING (listing_id)
LEFT JOIN analysis.ask_check q USING (listing_id)
LEFT JOIN analysis.building_check h USING (listing_id)
