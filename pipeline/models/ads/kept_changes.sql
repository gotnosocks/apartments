MODEL (
    name ads.kept_changes,
    kind CUSTOM (
        materialization 'merge',
        materialization_properties (changes = 'ads.touched', replace = 'listing_id')
    ),
    grain (listing_id, n),
    description 'Price changes left after the check for placeholder prices.'
);

-- The step first drops every stale change, as rentfrontier.latest_ask does from latest-ask-v9.
-- A change is stale when its ad is no longer active and the change falls more than 7 days after
-- the off-market day, unless one of the record's status changes puts the ad back to ACTIVE after
-- that day. Brokers reuse an old ad's record for a later ad of the same apartment, so a stale
-- change carries the later ad's ask. Listing 2273410 ran for 5 days in December 2017, and its
-- record carries changes to $2,250 and $3,000 from March 2019. `m` numbers the changes left.
--
-- Of those, a change counts as late when its ad is no longer active and the change falls on or
-- after the off-market day, other than on the on-market day. A late change is a placeholder when
-- it is more than twice or under half the last kept change, or when it raises the price by more
-- than 20% to exactly $10,000. The first change left always counts. Each check compares with the
-- last kept change, so the step recurses, and only over ads with a late change after their
-- first. With the recursion limited that way, the step took 20 s instead of 72 s on runs 1 to 4.
--
-- The model reads the ads in ads.touched: every ad in a full build, and in a top-up build the ads
-- the new answers change. A top-up's materialization `merge` replaces those ads' rows in a copy of
-- the previous build's table.
WITH RECURSIVE back AS (
    -- The ads whose latest record goes ACTIVE again after its off-market day.
    SELECT DISTINCT e.listing_id
    FROM ads.events e
    JOIN ads.latest_record r ON r.listing_id = e.listing_id AND epoch(e.last_seen) = r.collected_at
    WHERE e.source = 'status' AND e.kind = 'ACTIVE' AND e.day > r.off_day::DATE
        AND e.listing_id IN (SELECT listing_id FROM ads.touched)
),
c AS (
    SELECT p.*, row_number() OVER (PARTITION BY p.listing_id ORDER BY p.n) AS m,
        NOT (a.active OR a.off_day IS NULL OR p.day < a.off_day OR p.day = coalesce(a.on_day, '')) AS late
    FROM ads.price_changes p JOIN ads.latest_record a USING (listing_id)
    WHERE listing_id IN (SELECT listing_id FROM ads.touched)
        AND NOT coalesce(NOT a.active AND p.day::DATE > a.off_day::DATE + 7
            AND listing_id NOT IN (SELECT listing_id FROM back), false)
),
need AS (SELECT DISTINCT listing_id FROM c WHERE late AND m > 1),
c2 AS MATERIALIZED (SELECT * FROM c WHERE listing_id IN (SELECT listing_id FROM need)),
k AS (
    SELECT listing_id, n, m, day, price, true AS kept, price AS last FROM c2 WHERE m = 1
    UNION ALL
    SELECT c2.listing_id, c2.n, c2.m, c2.day, c2.price,
        NOT (c2.late AND (c2.price / k.last > 2 OR c2.price / k.last < 0.5
            OR (c2.price = 10000 AND c2.price / k.last > 1.2))) AS kept,
        CASE WHEN NOT (c2.late AND (c2.price / k.last > 2 OR c2.price / k.last < 0.5
            OR (c2.price = 10000 AND c2.price / k.last > 1.2))) THEN c2.price ELSE k.last END AS last
    FROM k JOIN c2 ON c2.listing_id = k.listing_id AND c2.m = k.m + 1
)
SELECT listing_id, n, day, price FROM c WHERE listing_id NOT IN (SELECT listing_id FROM need)
UNION ALL
SELECT listing_id, n, day, price FROM k WHERE kept
