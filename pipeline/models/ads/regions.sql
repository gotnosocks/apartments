MODEL (
    name ads.regions,
    kind FULL,
    grain listing_id,
    audits (
        unique_values(columns := (listing_id)),
        not_null(columns := (listing_id, regions))
    ),
    description 'Each ad with an answer, with the export regions of its answers.'
);

-- analysis.candidates gives each fit-ready row these regions, so a fit can choose the regions it
-- reads, and the ads file gives them for every ad.
SELECT listing_id::VARCHAR AS listing_id, list_sort(list(DISTINCT region)) AS regions
FROM raw.ads
GROUP BY listing_id
