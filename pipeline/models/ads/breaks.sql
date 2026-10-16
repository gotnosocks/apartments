MODEL (
    name ads.breaks,
    kind FULL,
    grain listing_id,
    audits (
        unique_values(columns := (listing_id)),
        not_null(columns := (listing_id, last_change))
    ),
    description 'Each ad''s last status change since its latest record''s first day on the market, and its latest break when it is back on the market.'
);

-- The model reads the status changes the ad's latest record lists, from ads.events, from that
-- record's `on_day` to `as_of` in ads.market, the New York day of the latest fetch. StreetEasy
-- rewrites an ad's list between answers: answers of 2026-10-15 listed changes off the market at
-- 03:11 on 10-14 and 10-15, and answers of 10-16 listed the same ads back on the market without
-- them. The model puts the changes in the order of their times and places in the record. It
-- keeps the six statuses the unit's history lists and leaves out the rest: drafts, reviews and
-- UNKNOWN, found on a few ads of 2014 and 2015. A change from review to ACTIVE thus isn't a
-- break. An ad without a change in that span has no row.
--   last_change:  the latest change.
--   break_status, break_day:  when the record's status and its latest change are ACTIVE and the
--       ad had left the market since `on_day`, the status and day of the change before the
--       latest return. A record can list a return after its ad's ending, as a few NO_LONGER_
--       AVAILABLE ads do, and such an ad gets no break.
--   back_day:  the day of that return.
-- The website's ad dates read the same from the history on the ad's page, which dates each
-- change to the day.
WITH changes AS (
    SELECT e.listing_id, e.kind, e.day,
        lag(e.kind) OVER (PARTITION BY e.listing_id ORDER BY e."at", e.list_index) AS previous,
        lag(e.day) OVER (PARTITION BY e.listing_id ORDER BY e."at", e.list_index) AS previous_day,
        e."at", e.list_index, m.status
    FROM ads.events e
    JOIN ads.market m USING (listing_id)
    JOIN ads.latest_record l USING (listing_id)
    WHERE e.source = 'status' AND e.last_seen = l.fetched
        AND e.day BETWEEN l.on_day::DATE AND m.as_of
        AND e.kind IN (
            'ACTIVE', 'TEMPORARILY_OFF_MARKET', 'IN_CONTRACT', 'RENTED', 'NO_LONGER_AVAILABLE',
            'DELISTED'
        )
),
breaks AS (
    SELECT listing_id, any_value(status) = 'ACTIVE' AS active,
        arg_max(kind, ("at", list_index)) AS last_change,
        arg_max(previous, ("at", list_index)) FILTER (
            WHERE kind = 'ACTIVE' AND previous <> 'ACTIVE'
        ) AS break_status,
        arg_max(previous_day, ("at", list_index)) FILTER (
            WHERE kind = 'ACTIVE' AND previous <> 'ACTIVE'
        ) AS break_day,
        arg_max(day, ("at", list_index)) FILTER (
            WHERE kind = 'ACTIVE' AND previous <> 'ACTIVE'
        ) AS back_day
    FROM changes
    GROUP BY listing_id
)
SELECT listing_id, last_change,
    CASE WHEN active AND last_change = 'ACTIVE' THEN break_status END AS break_status,
    CASE WHEN active AND last_change = 'ACTIVE' THEN break_day END AS break_day,
    CASE WHEN active AND last_change = 'ACTIVE' THEN back_day END AS back_day
FROM breaks
