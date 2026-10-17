MODEL (
    name ads.kept_changes,
    kind CUSTOM (
        materialization 'merge',
        materialization_properties (changes = 'ads.touched', replace = 'listing_id')
    ),
    grain (listing_id, n),
    description 'Price changes left after the check for placeholder prices.'
);

-- A change counts as late when its ad is no longer active and the change falls on or after
-- the off-market day, other than on the on-market day. A late change is a placeholder when it
-- is more than twice or under half the last kept change, or when it raises the price by more
-- than 20% to exactly $10,000. The first change always counts. Each check compares with the
-- last kept change, so the step recurses, and only over ads with a late change after their
-- first. With the recursion limited that way, the step took 20 s instead of 72 s on runs 1 to 4.
--
-- The model reads the ads in ads.touched: every ad in a full build, and in a top-up build the ads
-- the new answers change. A top-up's materialization `merge` replaces those ads' rows in a copy of
-- the previous build's table.
WITH RECURSIVE c AS (
    SELECT p.*, NOT (a.active OR a.off_day IS NULL OR p.day < a.off_day OR p.day = coalesce(a.on_day, '')) AS late
    FROM ads.price_changes p JOIN ads.latest_record a USING (listing_id)
    WHERE listing_id IN (SELECT listing_id FROM ads.touched)
),
need AS (SELECT DISTINCT listing_id FROM c WHERE late AND n > 1),
c2 AS MATERIALIZED (SELECT * FROM c WHERE listing_id IN (SELECT listing_id FROM need)),
k AS (
    SELECT listing_id, n, day, price, true AS kept, price AS last FROM c2 WHERE n = 1
    UNION ALL
    SELECT c2.listing_id, c2.n, c2.day, c2.price,
        NOT (c2.late AND (c2.price / k.last > 2 OR c2.price / k.last < 0.5
            OR (c2.price = 10000 AND c2.price / k.last > 1.2))) AS kept,
        CASE WHEN NOT (c2.late AND (c2.price / k.last > 2 OR c2.price / k.last < 0.5
            OR (c2.price = 10000 AND c2.price / k.last > 1.2))) THEN c2.price ELSE k.last END AS last
    FROM k JOIN c2 ON c2.listing_id = k.listing_id AND c2.n = k.n + 1
)
SELECT listing_id, n, day, price FROM c WHERE listing_id NOT IN (SELECT listing_id FROM need)
UNION ALL
SELECT listing_id, n, day, price FROM k WHERE kept
