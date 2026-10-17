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
--      The building slug comes from the latest record for the record's buildingId, as
--      buildings.details gives it. The collector instead stores each ad's record with the slug
--      its building had in the same generation when it stored the ad. The two agree on runs 1
--      to 5, which answer each building once. A record gives no page when either slug is
--      missing or empty, or holds a '/', '?' or '#'.
--   2. An ad takes a page when each of its records gives that page.
--   3. The ad's unit ID is 'unit:' and the version 5 UUID of its page in the URL namespace, as
--      Python's uuid.uuid5(uuid.NAMESPACE_URL, page) gives it. An ad gets no unit when it has
--      no page, or when its page also comes from a record of an ad without a page. The chain
--      leaves such a page unresolved rather than join two ads through it.
-- An ad without a unit carries the chain's two reasons for dropping it.
-- The chain's unit_page cleans the unit slug before it builds the page: it drops a trailing
-- '/', '?', '#' or ';' and removes tabs and line breaks. This rule gives no page for a slug with
-- one of the first three characters and keeps the others as they are. Each unit slug in runs 1
-- to 5 holds only lowercase letters, digits, '-' and '_'.
-- The ad's building is the building of its latest record. Answers without a record take no part,
-- as the chain reads only stored records.
WITH records AS (
    SELECT listing_id::VARCHAR AS listing_id, fetched, response_id, [building_id, unit_slug] AS f
    FROM ads.answers
    WHERE outcome = 'record'
),
captures AS (
    SELECT r.listing_id, r.fetched, r.response_id, r.f[1] AS building_id, b.slug AS building,
        CASE WHEN b.slug <> '' AND r.f[2] <> '' AND NOT regexp_matches(b.slug || r.f[2], '[/?#]')
            THEN 'https://streeteasy.com/building/' || b.slug || '/' || r.f[2] END AS page
    FROM records r
    LEFT JOIN buildings.details b ON b.building_id = r.f[1]
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
