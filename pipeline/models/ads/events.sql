MODEL (
    name ads.events,
    kind FULL,
    audits (
        unique_combination_of_columns(columns := (listing_id, source, kind, day, at, price)),
        not_null(columns := (listing_id, source, kind, day, own, first_seen, last_seen, first_response_id, answers))
    ),
    description 'Every event the API reported for an ad, once, with the answers that reported it.'
);

-- The events come from four places in an answer:
--   fetch:   the answer itself. Its kind is the ad's status when fetched, or MISSING for an
--            empty answer, its price the page price, and its day the New York date of the fetch.
--   status:  the record's statusChanges, timestamped.
--   price:   the record's pricing.priceChanges, timestamped.
--   history: the events of ads.history_events. The history lists the unit's other ads too, so
--            a record reports events of other ads, filed under the ad they belong to.
-- The day of a status or price change is its date as the API wrote it, in New York time.
-- An event reported by several answers, or by the records of several ads of one unit, appears
-- once. `answers` counts the answers that reported it, from any ad, and `first_seen` and
-- `first_response_id` give the first of them. `own` says whether an answer of the ad itself
-- reported it, and `own_first_seen` and `own_first_response_id` give the first such answer.
-- `list_index` gives a status or price change's place in its list, counting from 1, in the
-- latest answer that reported it. Two changes can share an instant, and the index keeps the
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
histories AS (
    SELECT history,
        min(fetched) AS first_seen,
        max(fetched) AS last_seen,
        arg_min(response_id, (fetched, response_id)) AS first_response_id,
        min((fetched, response_id)) AS first_report,
        count(*) AS answers
    FROM ads.answers
    WHERE history IS NOT NULL
    GROUP BY history
),
own_histories AS (
    SELECT history, listing_id,
        min(fetched) AS first_seen,
        arg_min(response_id, (fetched, response_id)) AS first_response_id,
        min((fetched, response_id)) AS first_report
    FROM ads.answers
    WHERE history IS NOT NULL
    GROUP BY history, listing_id
),
events AS (
    SELECT listing_id, source, kind, day, at, price,
        min(fetched) AS first_seen,
        max(fetched) AS last_seen,
        arg_min(response_id, (fetched, response_id)) AS first_response_id,
        count(*) AS answers,
        min(fetched) AS own_first_seen,
        arg_min(response_id, (fetched, response_id)) AS own_first_response_id,
        arg_max(list_index, (fetched, response_id)) AS list_index
    FROM reports
    GROUP BY listing_id, source, kind, day, at, price
    UNION ALL
    SELECT e.listing_id, 'history', e.kind, e.day, NULL::TIMESTAMPTZ, e.price,
        min(h.first_seen),
        max(h.last_seen),
        arg_min(h.first_response_id, h.first_report),
        sum(h.answers)::BIGINT,
        min(o.first_seen),
        arg_min(o.first_response_id, o.first_report),
        NULL::BIGINT
    FROM ads.history_events e
    JOIN histories h USING (history)
    LEFT JOIN own_histories o ON o.history = e.history AND o.listing_id = e.listing_id
    GROUP BY e.listing_id, e.kind, e.day, e.price
)
SELECT listing_id::VARCHAR AS listing_id, source, kind, day, at, price,
    own_first_seen IS NOT NULL AS own, first_seen, last_seen, first_response_id, answers,
    own_first_seen, own_first_response_id, list_index
FROM events
