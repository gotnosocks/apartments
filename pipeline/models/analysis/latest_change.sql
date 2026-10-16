MODEL (
    name analysis.latest_change,
    kind FULL,
    grain listing_id,
    audits (unique_values(columns := (listing_id))),
    description 'For each kept row, the price its ad last asked, and the ad''s page price.'
);

-- An ad has one kept row, priced on its first day. The row takes the ad's last kept change
-- dated on or after that day. Failing that, when the ad's record was collected after the row,
-- the row takes the change in effect on its day. The row is its ad's last, so the page price of
-- the ad's latest record counts for the row when the record was collected after it.
WITH r AS (
    SELECT listing_id, price_at, strftime(price_at, '%Y-%m-%d') AS day FROM analysis.kept
),
hit AS (
    SELECT r.listing_id,
        arg_max(k.price, k.n) FILTER (WHERE k.day >= r.day) AS live,
        arg_max(k.price, k.n) FILTER (WHERE k.day < r.day) AS before
    FROM r JOIN ads.kept_changes k USING (listing_id) GROUP BY r.listing_id
)
SELECT
    r.listing_id,
    coalesce(to_timestamp(a.collected_at) > r.price_at, false) AS last,
    CASE WHEN hit.live IS NULL AND to_timestamp(a.collected_at) > r.price_at THEN hit.before ELSE hit.live END AS live,
    CASE WHEN NOT EXISTS (SELECT 1 FROM ads.price_changes p WHERE p.listing_id = a.listing_id AND p.price = a.page_price)
        THEN a.page_price END AS page_price
FROM r LEFT JOIN hit USING (listing_id) LEFT JOIN ads.latest_record a USING (listing_id)
