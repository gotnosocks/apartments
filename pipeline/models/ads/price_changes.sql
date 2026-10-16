MODEL (
    name ads.price_changes,
    kind FULL,
    grain (listing_id, n),
    audits (unique_combination_of_columns(columns := (listing_id, n))),
    description 'The nonzero price changes of each ad''s latest record, from the event log, numbered in order of time.'
);

-- The event log holds each price change once, and `last_seen` gives the fetch of the latest
-- answer to report it. So the changes of an ad's latest record are its price events whose
-- `last_seen` equals that record's fetch. Changes at the same instant keep the record's order through
-- `list_index`. `day` stays the text of the date, as the steps below compare it with the
-- record's on-market and off-market days.
SELECT e.listing_id,
    row_number() OVER (PARTITION BY e.listing_id ORDER BY e."at", e.list_index) AS n,
    strftime(e.day, '%Y-%m-%d') AS day,
    e.price
FROM ads.events e
JOIN ads.latest_record r ON r.listing_id = e.listing_id AND epoch(e.last_seen) = r.collected_at
WHERE e.source = 'price' AND e.price <> 0
