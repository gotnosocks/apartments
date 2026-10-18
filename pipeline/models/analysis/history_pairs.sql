MODEL (
    name analysis.history_pairs,
    kind FULL,
    grain (unit_id, other_unit_id),
    audits (
        unique_combination_of_columns(columns := (unit_id, other_unit_id)),
        not_null(columns := (unit_id, other_unit_id, links, listing_id, listed_id))
    ),
    description 'Each pair of units an ad''s unit history joins: the history of an ad on one unit lists an ad the identity step put on the other.'
);

-- An ad's answer carries the history of its unit page, and the history lists every ad StreetEasy
-- files under that page. Where a listed ad has another unit in ads.placed, the two units hold ads
-- for one apartment under two spellings of its label, or a broker filed an ad on the wrong page.
-- The pair puts the lesser unit ID first and counts the (ad, listed ad) links behind it. Its
-- `listing_id` and `listed_id` give the first link: an ad and an ad its history lists.
-- analysis.label_units joins a pair's units when their bedroom counts agree.
WITH reports AS (
    SELECT DISTINCT listing_id::VARCHAR AS listing_id, history
    FROM ads.answers
    WHERE history IS NOT NULL
),
listed AS (
    SELECT DISTINCT history, listing_id::VARCHAR AS listed_id FROM ads.history_events
),
joined AS (
    SELECT r.listing_id, l.listed_id, p.unit_id AS unit, q.unit_id AS listed_unit
    FROM reports r
    JOIN listed l USING (history)
    JOIN ads.placed p ON p.listing_id = r.listing_id
    JOIN ads.placed q ON q.listing_id = l.listed_id
    WHERE p.unit_id IS NOT NULL AND q.unit_id IS NOT NULL AND p.unit_id <> q.unit_id
)
SELECT least(unit, listed_unit) AS unit_id, greatest(unit, listed_unit) AS other_unit_id,
    count(DISTINCT (listing_id, listed_id)) AS links,
    first(listing_id ORDER BY listing_id, listed_id) AS listing_id,
    first(listed_id ORDER BY listing_id, listed_id) AS listed_id
FROM joined
GROUP BY 1, 2
