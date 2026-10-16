MODEL (
    name ads.events,
    kind VIEW,
    description 'Every event the API reported for an ad, once, with the answers that reported it.'
);

-- The view lists the events of ads.answer_events, read from the fetch, status changes and price
-- changes of the ad's own answers, followed by those of ads.history_reports, read from the unit
-- histories. The two parts give different values of `source`, so each event appears once. Each
-- part builds as a table of its own. Run as one query, their aggregates spill at the 3 GB of
-- memory build-latest gives DuckDB, and they can run out of it.
SELECT listing_id, source, kind, day, at, price, own, first_seen, last_seen,
    first_response_id, answers, own_first_seen, own_first_response_id, list_index
FROM ads.answer_events
UNION ALL
SELECT listing_id, source, kind, day, at, price, own, first_seen, last_seen,
    first_response_id, answers, own_first_seen, own_first_response_id, list_index
FROM ads.history_reports
