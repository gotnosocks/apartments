MODEL (
    name ads.history_events,
    kind CUSTOM (
        materialization 'merge',
        materialization_properties (changes = 'ads.changes', add = 'history')
    ),
    audits (not_null(columns := (history, listing_id, kind, day))),
    description 'Each event in each distinct unit history, filed under the ad it belongs to.'
);

-- Each distinct history is read from the earliest answer that holds it. A history lists the
-- rentalEventsOfInterest of every ad of the unit, dated to the day. A status change keeps its
-- status as the kind, and a price change gets PRICE. An event listed twice in one history
-- appears once. An episode without a listingId is filed under its id. The current parser
-- would fall back to the reporting ad's own id after that, but one history can come from
-- several ads, so an episode with neither id stops the build at the audit.
-- The model reads the histories of the answers in ads.changes: every answer in a full build, and
-- the new ones in a top-up build. A history's events depend only on its text, so the
-- materialization `merge` adds the events of each history the previous build's table lacks, and
-- a top-up build parses each new history from its earliest new answer.
WITH firsts AS (
    SELECT history,
        arg_min(listing_id, (fetched, response_id)) AS listing_id,
        arg_min(response_id, (fetched, response_id)) AS response_id
    FROM ads.answers
    SEMI JOIN ads.changes USING (listing_id, response_id)
    WHERE history IS NOT NULL
    GROUP BY history
),
episodes AS (
    SELECT f.history,
        unnest(from_json(r.record -> '$.propertyHistory', '[{"id": "VARCHAR", "listingId": "VARCHAR", "rentalEventsOfInterest": [{"__typename": "VARCHAR", "date": "VARCHAR", "price": "DOUBLE", "status": "VARCHAR"}]}]')) AS e
    FROM raw.ads r JOIN firsts f USING (listing_id, response_id)
)
SELECT DISTINCT history, ad::BIGINT AS listing_id,
    CASE v.__typename WHEN 'RentalStatusChangeOfInterest' THEN v.status
        WHEN 'PriceChangeOfInterest' THEN 'PRICE' ELSE v.__typename END AS kind,
    v.date::DATE AS day,
    v.price
FROM (
    SELECT history, coalesce(e.listingId, e.id) AS ad, unnest(e.rentalEventsOfInterest) AS v
    FROM episodes
)
