MODEL (
    name ads.identity,
    kind FULL,
    grain listing_id,
    audits (unique_values(columns := (listing_id)), not_null(columns := (listing_id, records, reasons))),
    description 'Each ad with a record, with its building, its unit page and its unit under rule canonical-url-v1.'
);

-- The rule follows `canonical_units.memberships` and `graphql_listing.canonical_link` of the
-- current chain:
--   1. Each record gives the page https://streeteasy.com/building/{building slug}/{unit slug}.
--      The building slug comes from the latest answer for the record's buildingId in the
--      export's buildings table. A record gives no page when either slug is missing or empty,
--      or holds a '/', '?' or '#'.
--   2. An ad takes a page when each of its records gives that page.
--   3. The ad's unit ID is 'unit:' and the version 5 UUID of its page in the URL namespace, as
--      Python's uuid.uuid5(uuid.NAMESPACE_URL, page) gives it. An ad gets no unit when it has
--      no page, or when its page also comes from a record of an ad without a page. The chain
--      leaves such a page unresolved rather than join two ads through it.
-- An ad without a unit carries the chain's two reasons for dropping it.
-- When a unit slug ends in '/', '?' or '#', the chain's unit_page drops that character and
-- keeps the page, while this rule gives none. No slug in runs 1 to 5 of the export holds any of
-- the three characters.
-- The ad's building is the building of its latest record. Answers without a record take no part,
-- as the chain reads only stored records.
WITH buildings AS (
    SELECT building_id, json_extract_string(record, '$.slug') AS slug
    FROM raw.buildings
    WHERE outcome = 'record'
    QUALIFY row_number() OVER (PARTITION BY building_id ORDER BY fetched DESC, response_id DESC) = 1
),
records AS (
    SELECT listing_id::VARCHAR AS listing_id, fetched, response_id,
        json_extract_string(record, ['$.buildingId', '$.slug']) AS f
    FROM raw.ads
    WHERE outcome = 'record'
),
captures AS (
    SELECT r.listing_id, r.fetched, r.response_id, r.f[1] AS building_id, b.slug AS building,
        CASE WHEN b.slug <> '' AND r.f[2] <> '' AND NOT regexp_matches(b.slug || r.f[2], '[/?#]')
            THEN 'https://streeteasy.com/building/' || b.slug || '/' || r.f[2] END AS page
    FROM records r
    LEFT JOIN buildings b ON b.building_id = r.f[1]
),
ads AS (
    SELECT listing_id, count(*) AS records,
        CASE WHEN count(page) = count(*) AND count(DISTINCT page) = 1 THEN min(page) END AS page,
        arg_max_null(building_id, (fetched, response_id)) AS building_id,
        arg_max_null(building, (fetched, response_id)) AS building
    FROM captures
    GROUP BY listing_id
),
contested AS (
    SELECT DISTINCT c.page
    FROM captures c
    JOIN ads a USING (listing_id)
    WHERE a.page IS NULL AND c.page IS NOT NULL
),
hashed AS (
    -- The SHA-1 of the URL namespace's 16 bytes followed by the page, in hex.
    SELECT a.*,
        CASE WHEN a.page IS NOT NULL AND c.page IS NULL
            THEN sha1(unhex('6ba7b8119dad11d180b400c04fd430c8') || encode(a.page)) END AS h
    FROM ads a
    LEFT JOIN contested c ON c.page = a.page
)
SELECT listing_id, building_id, building, records, page,
    -- The first 32 hex digits, with the version digit set to 5 and the top two bits of the
    -- variant digit set to 10.
    'unit:' || substr(h, 1, 8) || '-' || substr(h, 9, 4) || '-5' || substr(h, 14, 3) || '-'
        || substr('89ab', ((strpos('0123456789abcdef', substr(h, 17, 1)) - 1) & 3) + 1, 1)
        || substr(h, 18, 3) || '-' || substr(h, 21, 12) AS unit_id,
    CASE WHEN h IS NULL
        THEN ['unresolved_or_conflicting_identity', 'unresolved_or_conflicting_canonical_url']
        ELSE []::VARCHAR[] END AS reasons
FROM hashed
