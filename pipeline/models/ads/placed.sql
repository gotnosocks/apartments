MODEL (
    name ads.placed,
    kind FULL,
    grain listing_id,
    audits (
        unique_values(columns := (listing_id)),
        not_null(columns := (listing_id, records, reasons, placements))
    ),
    description 'Each ad with a record, with its building and unit after the live entries of the unit ledger.'
);

-- The model starts from ads.identity and applies each live entry of ledger.unit_status:
--   join_units     each ad with a unit on one of the join's pages takes the least unit ID of
--                  those ads.
--   split_unit     each listed ad takes its unit ID, after any join, with '~review-' and the
--                  split's first listed ad after it, as the chain's `review_units` does. A
--                  split with an `into` gives its ads the unit of the split it points into,
--                  read from that split's ads with a record, since its `into` ad may have none.
--   move_building  each ad of the building takes the building's new slug and the ID of the
--                  building with that slug in buildings.details. Its page and unit stay as
--                  they are.
--   split_building after the moves, each ad of the building with a page ending in a label
--                  the entry's `labels` match, in lower case, takes the wing's slug. It keeps
--                  its building ID, so it keeps the building's lot. Its page and unit stay as
--                  they are.
-- An ad without a unit keeps none. `placements` lists the entries applied to the ad.
-- read_units, the parser behind ledger.unit_entries, lets a page take part in one live join, an
-- ad in one live split and a building in one live move and one live split_building, so each ad
-- meets at most one entry of each change.
WITH live AS (
    SELECT u.*
    FROM ledger.unit_entries u
    JOIN ledger.unit_status s USING (entry)
    WHERE s.status = 'live'
),
join_pages AS (
    SELECT entry, unnest(pages) AS page FROM live WHERE change = 'join_units'
),
joins AS (
    SELECT j.entry, i.listing_id, min(i.unit_id) OVER (PARTITION BY j.entry) AS unit_id
    FROM join_pages j
    JOIN ads.identity i ON i.page = j.page
    WHERE i.unit_id IS NOT NULL
),
splits AS (
    SELECT entry, listings[1] AS first, into_entry, unnest(listings) AS listing_id
    FROM live
    WHERE change = 'split_unit'
),
moves AS (
    SELECT l.entry, l.building, l.to_building, b.building_id AS to_id
    FROM live l
    JOIN buildings.details b ON b.slug = l.to_building
    WHERE l.change = 'move_building'
),
wings AS (
    SELECT entry, building, labels, to_building FROM live WHERE change = 'split_building'
),
placed AS (
    SELECT i.listing_id,
        coalesce(m.to_id, i.building_id) AS building_id,
        coalesce(w.to_building, m.to_building, i.building) AS building,
        i.records, i.page,
        CASE WHEN i.unit_id IS NOT NULL THEN coalesce(j.unit_id, i.unit_id)
            || CASE WHEN s.entry IS NOT NULL THEN '~review-' || s.first ELSE '' END END AS unit_id,
        i.reasons,
        -- list_distinct leaves out the NULLs of the changes the ad meets no entry of.
        list_sort(list_distinct([j.entry, s.entry, m.entry, w.entry])) AS placements,
        s.entry AS split,
        s.into_entry
    FROM ads.identity i
    LEFT JOIN joins j USING (listing_id)
    LEFT JOIN splits s USING (listing_id)
    LEFT JOIN moves m ON m.building = i.building
    LEFT JOIN wings w ON w.building = coalesce(m.to_building, i.building)
        AND regexp_full_match(lower(regexp_extract(i.page, '[^/]+$')), w.labels)
),
-- ledger.unit_status keeps a split with an `into` live only while the split it points into is
-- live, and a live split's ads with a record share its page, so they share a unit. read_units
-- lets a split point only into a split with no `into` of its own.
targets AS (
    SELECT split, min(unit_id) AS unit_id FROM placed WHERE split IS NOT NULL GROUP BY split
)
SELECT p.listing_id, p.building_id, p.building, p.records, p.page,
    CASE WHEN p.into_entry IS NOT NULL THEN t.unit_id ELSE p.unit_id END AS unit_id,
    p.reasons, p.placements
FROM placed p
LEFT JOIN targets t ON t.split = p.into_entry
