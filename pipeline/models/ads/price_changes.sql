MODEL (
    name ads.price_changes,
    kind FULL,
    grain (listing_id, n),
    audits (unique_combination_of_columns(columns := (listing_id, n))),
    description 'Price changes with a nonzero price, numbered in date order within each ad.'
);

-- Changes at the same time keep their order in the record.
WITH c AS (
    SELECT listing_id, unnest(changes) AS c, generate_subscripts(changes, 1) AS i FROM ads.latest_record
)
SELECT
    listing_id,
    row_number() OVER (PARTITION BY listing_id ORDER BY c.changedAt, i) AS n,
    left(c.changedAt, 10) AS day,
    c.price
FROM c
WHERE c.price IS NOT NULL AND c.price <> 0
