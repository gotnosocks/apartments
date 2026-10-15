MODEL (
    name ads.history_events,
    kind FULL,
    audits (not_null(columns := (history, listing_id, kind, day))),
    description 'Each event in each distinct unit history, filed under the ad it belongs to.'
);

-- Each distinct history is read from the earliest answer that holds it. A history lists the
-- rentalEventsOfInterest of every ad of the unit, dated to the day. A status change keeps its
-- status as the kind, and a price change gets PRICE. An event listed twice in one history
-- appears once.
WITH firsts AS (
    SELECT history,
        arg_min(listing_id, (fetched, response_id)) AS listing_id,
        arg_min(response_id, (fetched, response_id)) AS response_id
    FROM ads.answers
    WHERE history IS NOT NULL
    GROUP BY history
),
episodes AS (
    SELECT f.history,
        unnest(from_json(r.record -> '$.propertyHistory', '[{"listingId": "VARCHAR", "rentalEventsOfInterest": [{"__typename": "VARCHAR", "date": "VARCHAR", "price": "DOUBLE", "status": "VARCHAR"}]}]')) AS e
    FROM raw.ads r JOIN firsts f USING (listing_id, response_id)
)
SELECT DISTINCT history, ad::BIGINT AS listing_id,
    CASE v.__typename WHEN 'RentalStatusChangeOfInterest' THEN v.status
        WHEN 'PriceChangeOfInterest' THEN 'PRICE' ELSE v.__typename END AS kind,
    v.date::DATE AS day,
    v.price
FROM (SELECT history, e.listingId AS ad, unnest(e.rentalEventsOfInterest) AS v FROM episodes)
