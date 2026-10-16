MODEL (
    name ads.answer_events,
    kind FULL,
    audits (
        unique_combination_of_columns(columns := (listing_id, source, kind, day, at, price)),
        not_null(columns := (listing_id, source, kind, day, own, first_seen, last_seen, first_response_id, answers))
    ),
    description 'Every event an ad''s own answers reported in their fetch, status changes and price changes, once, with the answers that reported it.'
);

-- The model reads the events of `ads.events` from three places in an answer:
--   fetch:   the answer itself. Its kind is the ad's status when fetched, or MISSING for an
--            empty answer, its price the page price, and its day the New York date of the fetch.
--   status:  the record's statusChanges, timestamped.
--   price:   the record's pricing.priceChanges, timestamped.
-- The day of a status or price change is its date as the API wrote it, in New York time. An
-- event reported by several answers of the ad appears once. `answers` counts them, and
-- `first_seen` and `first_response_id` give the first of them. Every answer here belongs to the
-- ad, so `own` is true, and `own_first_seen` and `own_first_response_id` repeat the first
-- answer. `list_index` gives a status or price change's place in its list, counting from 1, in
-- the latest answer that reported it. Two changes can share an instant, and the index keeps the
-- record's order between them.
WITH reports AS (
    SELECT listing_id, 'fetch' AS source,
        CASE WHEN outcome = 'record' THEN status ELSE 'MISSING' END AS kind,
        (fetched AT TIME ZONE 'America/New_York')::DATE AS day, fetched AS at,
        page_price AS price, fetched, response_id, NULL::BIGINT AS list_index
    FROM ads.answers
    UNION ALL
    -- A change listed twice in one record counts once for the answer, at its last place.
    SELECT listing_id, 'status', c.status, left(c.changedAt, 10)::DATE,
        c.changedAt::TIMESTAMPTZ, NULL::DOUBLE, fetched, response_id, max(i)
    FROM (
        SELECT listing_id, fetched, response_id,
            unnest(status_changes) AS c, generate_subscripts(status_changes, 1) AS i
        FROM ads.answers
    )
    GROUP BY ALL
    UNION ALL
    SELECT listing_id, 'price', 'PRICE', left(c.changedAt, 10)::DATE,
        c.changedAt::TIMESTAMPTZ, c.price, fetched, response_id, max(i)
    FROM (
        SELECT listing_id, fetched, response_id,
            unnest(price_changes) AS c, generate_subscripts(price_changes, 1) AS i
        FROM ads.answers
    )
    GROUP BY ALL
),
-- `answer_order` puts an ad's answers in order of fetch time, then of response_id, as one
-- HUGEINT with the microseconds of the fetch above bit 64. A struct of the two would sort the
-- same way, but arg_min and arg_max keep a struct key as a blob of variable size in each state,
-- and over millions of events the query then spills at a 2 GB memory limit.
events AS (
    SELECT listing_id, source, kind, day, at, price,
        min(fetched) AS first_seen,
        max(fetched) AS last_seen,
        arg_min(response_id, answer_order) AS first_response_id,
        count(*) AS answers,
        arg_max(list_index, answer_order) AS list_index
    FROM (SELECT *, (epoch_us(fetched)::HUGEINT << 64) + response_id AS answer_order FROM reports)
    GROUP BY listing_id, source, kind, day, at, price
)
SELECT listing_id::VARCHAR AS listing_id, source, kind, day, at, price, true AS own,
    first_seen, last_seen, first_response_id, answers, first_seen AS own_first_seen,
    first_response_id AS own_first_response_id, list_index
FROM events
