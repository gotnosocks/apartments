MODEL (
    name ads.photos,
    kind CUSTOM (
        materialization 'merge',
        materialization_properties (changes = 'ads.changes', add = 'listing_id, key')
    ),
    grain (listing_id, key),
    audits (
        unique_combination_of_columns(columns := (listing_id, key)),
        not_null(columns := (listing_id, key))
    ),
    description 'Each photo an ad shows in any of its API answers, by the key StreetEasy gives it.'
);

-- StreetEasy names each photo of an ad by a key of 32 hex digits, under `$.media.photos`. A
-- broker who lists an apartment again usually shows the same photos, so analysis.relist_pairs
-- reads the keys two unit pages share. Over runs 1 to 10, 2,184,597 answers give 20,105,782
-- distinct pairs of ad and key.
--
-- The model reads the answers in ads.changes: every answer in a full build, and the new ones in
-- a top-up build. The materialization `merge` then adds the pairs the previous build's table
-- lacks, and an ad keeps a photo after a later answer drops it.
SELECT DISTINCT listing_id, key
FROM (
    SELECT r.listing_id::VARCHAR AS listing_id,
        unnest(json_extract_string(r.record, '$.media.photos[*].key')) AS key
    FROM raw.ads r
    SEMI JOIN ads.changes c USING (listing_id, response_id)
)
WHERE key IS NOT NULL
