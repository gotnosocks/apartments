MODEL (
    name ledger.unit_status,
    kind FULL,
    grain entry,
    audits (
        unique_values(columns := (entry)),
        not_null(columns := (entry, change, building, status, differs))
    ),
    description 'Each entry of the unit ledger, with its status against the ads and buildings.'
);

-- Each entry gets the first status that fits it, in this order:
--   retract     the entry undoes another.
--   retracted   a later entry undoes it.
--   absent      a join finds ads with a unit on fewer than two of its pages, a split finds none
--               of its ads, or a move finds no ad in its building.
--   stale       a split lists an ad with another page or with no unit, or a move's `to` matches
--               no building's slug, or more than one. `differs` gives the split's ads, or 'to'.
--               A split with an `into` is also stale, with 'into', when the split it points
--               into isn't live.
--   live        it applies, and ads.placed applies it.
-- ads.identity gives the ads' pages, units and buildings, before any entry applies.
WITH join_pages AS (
    SELECT entry, unnest(pages) AS page
    FROM ledger.unit_entries
    WHERE change = 'join_units'
),
joins AS (
    SELECT j.entry, count(DISTINCT i.page) >= 2 AS present, '' AS differs
    FROM join_pages j
    LEFT JOIN ads.identity i ON i.page = j.page AND i.unit_id IS NOT NULL
    GROUP BY j.entry
),
split_ads AS (
    SELECT entry, pages[1] AS page, unnest(listings) AS listing_id
    FROM ledger.unit_entries
    WHERE change = 'split_unit'
),
splits AS (
    SELECT s.entry, count(i.listing_id) > 0 AS present,
        coalesce(string_agg(
            CASE WHEN i.listing_id IS NOT NULL
                AND (i.page IS DISTINCT FROM s.page OR i.unit_id IS NULL) THEN s.listing_id END,
            ' ' ORDER BY s.listing_id
        ), '') AS differs
    FROM split_ads s
    LEFT JOIN ads.identity i USING (listing_id)
    GROUP BY s.entry
),
housed AS (
    SELECT DISTINCT building FROM ads.identity WHERE building IS NOT NULL
),
slugs AS (
    SELECT slug, count(*) AS buildings FROM buildings.details GROUP BY slug
),
moves AS (
    SELECT u.entry, h.building IS NOT NULL AS present,
        CASE WHEN s.buildings = 1 THEN '' ELSE 'to' END AS differs
    FROM ledger.unit_entries u
    LEFT JOIN housed h ON h.building = u.building
    LEFT JOIN slugs s ON s.slug = u.to_building
    WHERE u.change = 'move_building'
),
checked AS (
    SELECT u.entry, u.file, u.line, u.change, u.building,
        u.entry IN (
            SELECT retracts FROM ledger.unit_entries WHERE change = 'retract'
        ) AS retracted,
        coalesce(j.present, s.present, m.present) AS present,
        coalesce(j.differs, s.differs, m.differs, '') AS differs
    FROM ledger.unit_entries u
    LEFT JOIN joins j USING (entry)
    LEFT JOIN splits s USING (entry)
    LEFT JOIN moves m USING (entry)
),
statuses AS (
    SELECT entry, file, line, change, building,
        CASE
            WHEN change = 'retract' THEN 'retract'
            WHEN retracted THEN 'retracted'
            WHEN NOT present THEN 'absent'
            WHEN differs <> '' THEN 'stale'
            ELSE 'live'
        END AS status,
        CASE WHEN present THEN differs ELSE '' END AS differs
    FROM checked
),
-- read_units lets a split point only into a split with no `into` of its own, so one step
-- settles each split's status.
pointed AS (
    SELECT s.*, s.status = 'live' AND u.into_entry IS NOT NULL
        AND t.status IS DISTINCT FROM 'live' AS dangling
    FROM statuses s
    JOIN ledger.unit_entries u USING (entry)
    LEFT JOIN statuses t ON t.entry = u.into_entry
)
SELECT entry, file, line, change, building,
    CASE WHEN dangling THEN 'stale' ELSE status END AS status,
    CASE WHEN dangling THEN 'into' ELSE differs END AS differs
FROM pointed
