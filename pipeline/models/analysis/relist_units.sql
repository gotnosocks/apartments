MODEL (
    name analysis.relist_units,
    kind FULL,
    grain unit_id,
    audits (unique_values(columns := (unit_id)), not_null(columns := (unit_id, relist_unit, pages))),
    description 'Each unit page the relist step joins with another, with its relist unit and the count of unit pages in it.'
);

-- analysis.relist_links gives the relist unit of both pages of each pair, as it stands after the
-- step has taken every pair. A page whose pairs all clash or meet a mixed layout stays on its
-- own and drops out here.
-- analysis.rows gives each row the relist unit of its unit page, or the unit page itself.
SELECT unit_id, relist_unit, pages
FROM (
    SELECT unit_id, relist_unit, count(*) OVER (PARTITION BY relist_unit) AS pages
    FROM (
        SELECT unit_id, relist_unit FROM analysis.relist_links
        UNION
        SELECT next_unit_id, next_relist_unit FROM analysis.relist_links
    )
)
WHERE pages > 1
