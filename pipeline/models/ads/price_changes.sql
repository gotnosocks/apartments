MODEL (
    name ads.price_changes,
    kind CUSTOM (
        materialization 'merge',
        materialization_properties (changes = 'ads.touched', replace = 'listing_id')
    ),
    grain (listing_id, n),
    audits (unique_combination_of_columns(columns := (listing_id, n))),
    description 'The nonzero price changes of each ad''s latest record, from the event log, numbered in order of time.'
);

-- The event log holds each price change once, and `last_seen` gives the fetch of the latest
-- answer to report it. This model takes an ad's price events and keeps those with `last_seen`
-- at the fetch of the ad's latest record. Changes at the same instant keep the record's order
-- through `list_index`. `day` stays the text of the date, as the steps below compare it with the
-- record's on-market and off-market days.
--
-- The model reads the ads in ads.touched: every ad in a full build, and in a top-up build the ads
-- the new answers change. A top-up's materialization `merge` replaces those ads' rows in a copy of
-- the previous build's table.
SELECT e.listing_id,
    row_number() OVER (PARTITION BY e.listing_id ORDER BY e."at", e.list_index) AS n,
    strftime(e.day, '%Y-%m-%d') AS day,
    e.price
FROM ads.events e
JOIN ads.latest_record r ON r.listing_id = e.listing_id AND epoch(e.last_seen) = r.collected_at
WHERE e.source = 'price' AND e.price <> 0 AND e.listing_id IN (SELECT listing_id FROM ads.touched)
