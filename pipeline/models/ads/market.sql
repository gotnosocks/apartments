MODEL (
    name ads.market,
    kind FULL,
    grain listing_id,
    audits (
        unique_values(columns := (listing_id)),
        not_null(columns := (listing_id, as_of, active_days, active_spans))
    ),
    description 'Each ad''s time on the market and its ending, from the status changes in its event log.'
);

-- An ad's status changes come from its own records. The model puts them in order of time, and
-- in the record's order when two share an instant. Each change holds until the next one, and the
-- last holds until `as_of`, the New York date of the ad's latest answer with a record.
--   on_day:       the day of the first change to ACTIVE, as in the record's onMarketAt.
--   off_day:      the day of the last change from ACTIVE or IN_CONTRACT to another status,
--                 as in the record's offMarketAt. An ad whose last change is to ACTIVE or
--                 IN_CONTRACT is still on the market and has none.
--   active_days:  the days from each change to ACTIVE until the next change, summed.
--   active_spans: the number of changes to ACTIVE from another status, or from none. An ad
--                 put back on the market has two or more.
--   ending:       the last change, when it is RENTED, NO_LONGER_AVAILABLE or DELISTED, and
--                 `ending_day` its day. An ad still on the market, or paused, has none.
-- `status`, `record_days_on_market` and `rented_price` come from the latest record, as the API
-- wrote them. StreetEasy's daysOnMarket also leaves out days in contract or off the market,
-- and docs/data/pipeline.md compares it with `active_days`.
WITH latest AS (
    SELECT listing_id::VARCHAR AS listing_id,
        max((fetched AT TIME ZONE 'America/New_York')::DATE) AS as_of,
        arg_max_null(status, (fetched, response_id)) AS status,
        arg_max_null(days_on_market, (fetched, response_id)) AS record_days_on_market,
        arg_max_null(rented_price, (fetched, response_id)) AS rented_price
    FROM ads.answers
    WHERE outcome = 'record'
    GROUP BY listing_id
),
changes AS (
    SELECT listing_id, kind, day, "at", list_index,
        lag(kind) OVER (PARTITION BY listing_id ORDER BY "at", list_index) AS previous,
        lead(day) OVER (PARTITION BY listing_id ORDER BY "at", list_index) AS next_day
    FROM ads.events
    WHERE source = 'status'
),
spans AS (
    SELECT c.listing_id,
        min(c.day) FILTER (WHERE c.kind = 'ACTIVE') AS on_day,
        max(c.day) FILTER (
            WHERE c.previous IN ('ACTIVE', 'IN_CONTRACT') AND c.kind NOT IN ('ACTIVE', 'IN_CONTRACT')
        ) AS last_exit,
        sum(date_diff('day', c.day, coalesce(c.next_day, l.as_of))) FILTER (WHERE c.kind = 'ACTIVE') AS active_days,
        count(*) FILTER (WHERE c.kind = 'ACTIVE' AND c.previous IS DISTINCT FROM 'ACTIVE') AS active_spans,
        arg_max(c.kind, (c."at", c.list_index)) AS last_kind,
        arg_max(c.day, (c."at", c.list_index)) AS last_day
    FROM changes c
    JOIN latest l USING (listing_id)
    GROUP BY c.listing_id
)
SELECT l.listing_id, l.as_of, l.status, s.on_day,
    CASE WHEN s.last_kind NOT IN ('ACTIVE', 'IN_CONTRACT') THEN s.last_exit END AS off_day,
    coalesce(s.active_days, 0) AS active_days,
    coalesce(s.active_spans, 0) AS active_spans,
    CASE WHEN s.last_kind IN ('RENTED', 'NO_LONGER_AVAILABLE', 'DELISTED') THEN s.last_kind END AS ending,
    CASE WHEN s.last_kind IN ('RENTED', 'NO_LONGER_AVAILABLE', 'DELISTED') THEN s.last_day END AS ending_day,
    l.record_days_on_market, l.rented_price
FROM latest l LEFT JOIN spans s USING (listing_id)
