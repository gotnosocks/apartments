MODEL (
    name ads.exclusions,
    kind CUSTOM (
        materialization 'merge',
        materialization_properties (changes = 'ads.touched', replace = 'listing_id')
    ),
    grain listing_id,
    audits (unique_values(columns := (listing_id)), not_null(columns := (listing_id, reasons))),
    description 'Each ad with a record, with its first day, its first ask and the current chain''s reasons for dropping it.'
);

-- The reasons follow `project_advertisement`, which reads an ad's own ACTIVE events and its
-- captures, merged as in ads.attributes:
--   no_dated_own_active_event: the ad's own history lists no ACTIVE event for it, so it has
--     no first ask. The chain reads events only from the records it parses, so an ad without
--     such a record gets this reason too, while its first day and ask here come from the
--     event log. The event log reads every record of the ad, so for an ad with records of
--     both kinds, its first ask here may draw on a record the chain leaves out. Runs 1 to 5 of
--     the export hold no record the chain fails to parse.
--   future_own_active_event: an ACTIVE event in its own history falls after the day of its last
--     answer. The chain compares midnight UTC of the event's day with its as-of time instead.
--   outside_date_window: its first day comes before 2010.
--   conflicting_or_missing_initial_prices: its first day carries two prices, or an event
--     without one.
--   conflicting_layout_within_advertisement: its records give two values for the bedrooms,
--     bathrooms or size.
--   excluded_furnished, excluded_short_term, excluded_concession: a record sets the flag.
--   invalid_or_extreme_initial_ask: it lacks a single first ask from $750 to $50,000.
--   invalid_or_missing_layout: it lacks a whole bedroom count from 0 to 5 or a bathroom count
--     from 1 to 5 in halves.
-- The chain stops at no_dated_own_active_event, since the other checks need a first day. Three
-- of the chain's reasons are left out: ads.identity gives the reasons of the checks of the
-- unit's identity and of the canonical URL, and the check for two ads of one unit in one month
-- waits for the fit-ready rows. An unparseable event
-- date stops the build in ads.history_events, so `invalid_own_active_event_date` never
-- appears.
--
-- The model reads the ads in ads.touched: every ad in a full build, and in a top-up build the ads
-- the new answers change. A top-up's materialization `merge` replaces those ads' rows in a copy of
-- the previous build's table.
WITH ads AS (
    SELECT listing_id::VARCHAR AS listing_id,
        max((fetched AT TIME ZONE 'America/New_York')::DATE) AS last_day
    FROM ads.answers
    WHERE outcome = 'record' AND listing_id::VARCHAR IN (SELECT listing_id FROM ads.touched)
    GROUP BY listing_id
),
own_active AS (
    SELECT listing_id, max(day) AS last_active
    FROM ads.events
    WHERE source = 'history' AND kind = 'ACTIVE' AND own AND listing_id IN (SELECT listing_id FROM ads.touched)
    GROUP BY listing_id
),
checked AS (
    SELECT a.listing_id, f.first_day, f.prices, f.missing_price,
        CASE WHEN len(f.prices) = 1 THEN f.prices[1] END AS rent,
        t.records, t.bedrooms, t.bathrooms, t.conflicts, t.furnished, t.short_term, t.concession,
        o.last_active > a.last_day AS future
    FROM ads a
    LEFT JOIN ads.first_ask f USING (listing_id)
    LEFT JOIN own_active o USING (listing_id)
    LEFT JOIN ads.attributes t USING (listing_id)
)
SELECT listing_id, first_day, rent,
    CASE WHEN first_day IS NULL OR records IS NULL THEN ['no_dated_own_active_event']
    ELSE list_sort(list_filter([
        CASE WHEN future THEN 'future_own_active_event' END,
        CASE WHEN first_day < DATE '2010-01-01' THEN 'outside_date_window' END,
        CASE WHEN len(prices) <> 1 OR missing_price THEN 'conflicting_or_missing_initial_prices' END,
        CASE WHEN list_has_any(coalesce(conflicts, []), ['bedrooms', 'bathrooms', 'square_feet'])
            THEN 'conflicting_layout_within_advertisement' END,
        CASE WHEN furnished THEN 'excluded_furnished' END,
        CASE WHEN short_term THEN 'excluded_short_term' END,
        CASE WHEN concession THEN 'excluded_concession' END,
        CASE WHEN rent IS NULL OR NOT rent BETWEEN 750 AND 50000 THEN 'invalid_or_extreme_initial_ask' END,
        CASE WHEN bedrooms IS NULL OR NOT bedrooms BETWEEN 0 AND 5 OR bedrooms % 1 <> 0
            OR bathrooms IS NULL OR NOT bathrooms BETWEEN 1 AND 5 OR (bathrooms * 2) % 1 <> 0
            THEN 'invalid_or_missing_layout' END
    ], r -> r IS NOT NULL)) END AS reasons
FROM checked
