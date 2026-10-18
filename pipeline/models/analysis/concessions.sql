MODEL (
    name analysis.concessions,
    kind FULL,
    grain listing_id,
    audits (
        unique_values(columns := (listing_id)),
        not_null(columns := (listing_id, months_free, lease_term, factor, start, gross_prices, net_prices))
    ),
    description 'Each kept row whose ad''s latest record offers free months: the terms, the share of the gross ask a tenant pays over the lease, and the ad''s prices before and from the price the concession began with.'
);

-- StreetEasy shows a concession ad's gross ask as its price, and its `pricing` gives the months
-- free, the lease term and a net effective rent. The step reads the terms from the ad's latest
-- record, ads.latest_record, and takes them when the months free lie above 0 and below the
-- term. `factor` is the share of the gross a tenant pays: (term - months free) / term.
--
-- An ad can gain its concession after a few asks. The step lists the ad's prices: the row's
-- first ask (n = 0), then the changes ads.kept_changes keeps, by n. `start` is the n of the first
-- price whose net, price × factor, comes within $1 of the net effective rent. Failing that, it
-- is the n of the last price, since StreetEasy can leave the net effective rent of an earlier
-- price in place. `gross_prices` lists the prices before `start`, and `net_prices` the prices
-- from `start` on. analysis.ledger_rows takes the factor off the row's latest ask unless the ask
-- matches a price of `gross_prices` alone.
--
-- On the lane state of Oct 18, 166,870 ads offered free months below the term. The net effective
-- rent matched the first price on 111,816, a later price on 53,834 (the last price alone on
-- 51,301) and no price on 1,220.
WITH terms AS (
    SELECT k.listing_id, k.asking_rent, r.months_free, r.lease_term, r.net_effective_rent,
        (r.lease_term - r.months_free) / r.lease_term AS factor
    FROM analysis.kept k JOIN ads.latest_record r USING (listing_id)
    WHERE r.months_free > 0 AND r.lease_term > r.months_free
),
prices AS (
    SELECT listing_id, 0 AS n, asking_rent AS price FROM terms
    UNION ALL
    SELECT k.listing_id, k.n, k.price FROM ads.kept_changes k SEMI JOIN terms USING (listing_id)
),
starts AS (
    SELECT p.listing_id,
        coalesce(min(p.n) FILTER (WHERE abs(p.price * t.factor - t.net_effective_rent) <= 1), max(p.n)) AS start
    FROM prices p JOIN terms t USING (listing_id)
    GROUP BY p.listing_id
)
SELECT t.listing_id, t.months_free, t.lease_term, t.net_effective_rent, t.factor, s.start,
    coalesce(list(p.price ORDER BY p.n) FILTER (WHERE p.n < s.start), []) AS gross_prices,
    list(p.price ORDER BY p.n) FILTER (WHERE p.n >= s.start) AS net_prices
FROM terms t
JOIN starts s USING (listing_id)
JOIN prices p USING (listing_id)
GROUP BY ALL
