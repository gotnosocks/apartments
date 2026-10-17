MODEL (
    name ads.history_reports,
    kind CUSTOM (
        materialization 'merge',
        materialization_properties (changes = 'ads.touched', replace = 'listing_id')
    ),
    audits (
        unique_combination_of_columns(columns := (listing_id, kind, day, price)),
        not_null(columns := (listing_id, source, kind, day, own, first_seen, last_seen, first_response_id, answers))
    ),
    description 'Every event of the unit histories, once for each ad, with the answers that held a history listing it.'
);

-- The model reads the events of `ads.events` from the unit histories in ads.history_events. A
-- history lists the unit's other ads too, so a record reports events of other ads, filed under
-- the ad they belong to. An event listed by several histories, from the records of one ad or of
-- several ads of the unit, appears once. `answers` counts the answers holding those histories,
-- from any ad, and `first_seen` and `first_response_id` give the first of them. `own` says
-- whether an answer of the ad itself held one of them, and `own_first_seen` and
-- `own_first_response_id` give the first such answer. A history dates its events to the day,
-- so `at` and `list_index` stay empty.
--
-- The model reads the ads in ads.touched: every ad in a full build, and in a top-up build the ads
-- the new answers change. A top-up's materialization `merge` replaces those ads' rows in a copy of
-- the previous build's table.
WITH touched_events AS (
    SELECT * FROM ads.history_events WHERE listing_id::VARCHAR IN (SELECT listing_id FROM ads.touched)
),
histories AS (
    SELECT history,
        min(fetched) AS first_seen,
        max(fetched) AS last_seen,
        arg_min(response_id, (fetched, response_id)) AS first_response_id,
        min((fetched, response_id)) AS first_report,
        count(*) AS answers
    FROM ads.answers
    WHERE history IN (SELECT history FROM touched_events)
    GROUP BY history
),
own_histories AS (
    SELECT history, listing_id,
        min(fetched) AS first_seen,
        arg_min(response_id, (fetched, response_id)) AS first_response_id,
        min((fetched, response_id)) AS first_report
    FROM ads.answers
    WHERE history IN (SELECT history FROM touched_events)
    GROUP BY history, listing_id
),
events AS (
    SELECT e.listing_id, e.kind, e.day, e.price,
        min(h.first_seen) AS first_seen,
        max(h.last_seen) AS last_seen,
        arg_min(h.first_response_id, h.first_report) AS first_response_id,
        sum(h.answers)::BIGINT AS answers,
        min(o.first_seen) AS own_first_seen,
        arg_min(o.first_response_id, o.first_report) AS own_first_response_id
    FROM touched_events e
    JOIN histories h USING (history)
    LEFT JOIN own_histories o ON o.history = e.history AND o.listing_id = e.listing_id
    GROUP BY e.listing_id, e.kind, e.day, e.price
)
SELECT listing_id::VARCHAR AS listing_id, 'history' AS source, kind, day,
    NULL::TIMESTAMPTZ AS at, price, own_first_seen IS NOT NULL AS own, first_seen, last_seen,
    first_response_id, answers, own_first_seen, own_first_response_id, NULL::BIGINT AS list_index
FROM events
