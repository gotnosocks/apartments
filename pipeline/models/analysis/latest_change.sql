MODEL (
    name analysis.latest_change,
    kind FULL,
    grain ordinal,
    audits (unique_values(columns := (ordinal))),
    description 'For each analysis row, the price its ad last asked while the row stood, and the ad''s page price.'
);

-- A row stands from its own day up to the day of its ad's next row. The row takes the last
-- kept change in that span. Failing that, when the ad's record was collected after the row,
-- the row takes the change in effect on its day.
WITH r AS (
    SELECT ordinal, source_listing_id AS listing_id, price_at, strftime(price_at, '%Y-%m-%d') AS day
    FROM raw.analysis_rows
),
r2 AS (
    SELECT *, coalesce(lead(day) OVER (PARTITION BY listing_id ORDER BY day, ordinal), '9999-99-99') AS nxt FROM r
),
hit AS (
    SELECT r2.ordinal,
        arg_max(k.price, k.n) FILTER (WHERE k.day >= r2.day AND k.day < r2.nxt) AS live,
        arg_max(k.price, k.n) FILTER (WHERE k.day < r2.day) AS before
    FROM r2 JOIN ads.kept_changes k USING (listing_id) GROUP BY r2.ordinal
)
SELECT
    r2.ordinal,
    a.listing_id IS NOT NULL AS captured,
    coalesce(to_timestamp(a.collected_at) > r2.price_at, false) AS after,
    CASE WHEN hit.live IS NULL AND to_timestamp(a.collected_at) > r2.price_at THEN hit.before ELSE hit.live END AS live,
    r2.nxt = '9999-99-99' AND coalesce(to_timestamp(a.collected_at) > r2.price_at, false) AS last,
    CASE WHEN NOT EXISTS (SELECT 1 FROM ads.price_changes p WHERE p.listing_id = a.listing_id AND p.price = a.page_price)
        THEN a.page_price END AS page_price
FROM r2 LEFT JOIN hit USING (ordinal) LEFT JOIN ads.latest_record a USING (listing_id)
