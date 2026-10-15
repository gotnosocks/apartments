MODEL (
    name ads.first_ask,
    kind FULL,
    grain listing_id,
    audits (
        unique_values(columns := (listing_id)),
        not_null(columns := (listing_id, first_day, prices, missing_price, first_seen, first_response_id))
    ),
    description 'Each ad''s first day on the market and its asks that day, from its own record''s history.'
);

-- The first day is the earliest ACTIVE status change the ad's own record lists for it. The
-- prices are the distinct prices of the ACTIVE changes on that day, and `missing_price` says
-- whether one of those changes came without a price. The current chain takes the day at
-- midnight UTC as the row's price_at and a single price as its asking rent, and it drops an ad
-- with a missing price or with two. `first_seen` and `first_response_id` give the ad's own
-- earliest answer that reported the first day.
SELECT listing_id, first_day,
    coalesce(list_sort(list(DISTINCT price) FILTER (WHERE price IS NOT NULL)), []) AS prices,
    bool_or(price IS NULL) AS missing_price,
    min(own_first_seen) AS first_seen,
    arg_min(own_first_response_id, (own_first_seen, own_first_response_id)) AS first_response_id
FROM (
    SELECT *, min(day) OVER (PARTITION BY listing_id) AS first_day
    FROM ads.events WHERE source = 'history' AND kind = 'ACTIVE' AND own
)
WHERE day = first_day
GROUP BY listing_id, first_day
