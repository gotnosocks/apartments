MODEL (
    name ads.regions,
    kind CUSTOM (
        materialization 'merge',
        materialization_properties (changes = 'ads.touched', replace = 'listing_id')
    ),
    grain listing_id,
    audits (
        unique_values(columns := (listing_id)),
        not_null(columns := (listing_id, regions))
    ),
    description 'Each ad with an answer, with the export regions of its answers.'
);

-- analysis.candidates gives each fit-ready row these regions, so a fit can choose the regions it
-- reads, and the ads file gives them for every ad.
--
-- The model reads the ads in ads.touched: every ad in a full build, and in a top-up build the ads
-- the new answers change. A top-up's materialization `merge` replaces those ads' rows in a copy of
-- the previous build's table.
SELECT listing_id::VARCHAR AS listing_id, list_sort(list(DISTINCT region)) AS regions
FROM ads.answers
WHERE listing_id::VARCHAR IN (SELECT listing_id FROM ads.touched)
GROUP BY listing_id
