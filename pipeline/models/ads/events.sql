MODEL (
    name ads.events,
    kind FULL,
    audits (
        unique_combination_of_columns(columns := (listing_id, source, kind, day, at, price)),
        not_null(columns := (listing_id, source, kind, day, own, first_seen, first_response_id, answers))
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
-- once. `own` says whether the ad's own record reported it, `answers` counts the answers that
-- reported it, and `first_response_id` names the answer that reported it first.
WITH reports AS (
    SELECT listing_id, 'fetch' AS source,
        CASE WHEN outcome = 'record' THEN status ELSE 'MISSING' END AS kind,
        (fetched AT TIME ZONE 'America/New_York')::DATE AS day, fetched AS at,
        page_price AS price, fetched, response_id
    FROM ads.answers
    UNION ALL
    SELECT DISTINCT listing_id, 'status', c.status, left(c.changedAt, 10)::DATE,
        c.changedAt::TIMESTAMPTZ, NULL::DOUBLE, fetched, response_id
    FROM (SELECT *, unnest(status_changes) AS c FROM ads.answers)
    UNION ALL
    SELECT DISTINCT listing_id, 'price', 'PRICE', left(c.changedAt, 10)::DATE,
        c.changedAt::TIMESTAMPTZ, c.price, fetched, response_id
    FROM (SELECT *, unnest(price_changes) AS c FROM ads.answers)
),
histories AS (
    SELECT history,
        min(fetched) AS first_seen,
        max(fetched) AS last_seen,
        arg_min(response_id, (fetched, response_id)) AS first_response_id,
        min((fetched, response_id)) AS first_report,
        count(*) AS answers,
        list(DISTINCT listing_id) AS reporters
    FROM ads.answers
    WHERE history IS NOT NULL
    GROUP BY history
),
events AS (
    SELECT listing_id, source, kind, day, at, price,
        true AS own,
        min(fetched) AS first_seen,
        max(fetched) AS last_seen,
        arg_min(response_id, (fetched, response_id)) AS first_response_id,
        count(*) AS answers
    FROM reports
    GROUP BY listing_id, source, kind, day, at, price
    UNION ALL
    SELECT e.listing_id, 'history', e.kind, e.day, NULL::TIMESTAMPTZ, e.price,
        bool_or(list_contains(h.reporters, e.listing_id)),
        min(h.first_seen),
        max(h.last_seen),
        arg_min(h.first_response_id, h.first_report),
        sum(h.answers)::BIGINT
    FROM ads.history_events e JOIN histories h USING (history)
    GROUP BY e.listing_id, e.kind, e.day, e.price
)
SELECT listing_id::VARCHAR AS listing_id, source, kind, day, at, price, own, first_seen,
    last_seen, first_response_id, answers
FROM events
